"""Admin knowledge points CRUD + LLM generate key points."""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas.common import PaginatedResponse
from app.api.v1.pagination import paginate
from app.api.v1.schemas.knowledge_point import (
    AutoAssociateResult,
    GenerateKeyPointsResponse,
    KPBridgeItem,
    KPBridgeReplaceRequest,
    KPCreate,
    KPDetail,
    KPListItem,
    KPUpdate,
    KeyPointCreate,
    KeyPointItem,
    KeyPointReorderRequest,
    KeyPointUpdate,
)
from app.core.database import get_db
from app.models import Bridge, Chunk, Flashcard, KnowledgePoint, KnowledgePointKeyPoint, TaxonomyNode
from app.models.current_user import CurrentUser
from app.providers import ChatMessage, get_provider
from app.services.audit_service import AuditService
from app.services.flashcard_generator import FlashcardBatchGenerator
from app.services.kp_bridge_service import KnowledgePointBridgeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-points", tags=["knowledge-points"])


def _build_detail(kp: KnowledgePoint, key_points: list[KnowledgePointKeyPoint]) -> KPDetail:
    """Build KPDetail response from model instances."""
    return KPDetail(
        id=kp.id,
        taxonomy_node_id=kp.taxonomy_node_id,
        lvl1=kp.lvl1,
        lvl2=kp.lvl2,
        name=kp.name,
        aliases=kp.aliases,
        difficulty=kp.difficulty,
        summary=kp.summary,
        l2_content=kp.l2_content,
        key_points=[
            KeyPointItem(
                id=kpkp.id,
                summary=kpkp.summary,
                explanation=kpkp.explanation,
                order_index=kpkp.order_index,
                chunk_ids=[str(cid) for cid in (kpkp.chunk_ids or [])],
            )
            for kpkp in key_points
        ],
    )


@router.get("", response_model=PaginatedResponse[KPListItem])
def list_knowledge_points(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    taxonomy_node_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[KPListItem]:
    """List knowledge points with optional taxonomy filter."""
    query = db.query(KnowledgePoint)

    if taxonomy_node_id is not None:
        query = query.filter(KnowledgePoint.taxonomy_node_id == taxonomy_node_id)

    return paginate(
        query.order_by(KnowledgePoint.name),
        page,
        page_size,
        lambda kp: KPListItem(
            id=kp.id,
            name=kp.name,
            taxonomy_node_id=kp.taxonomy_node_id,
            lvl1=kp.lvl1,
            lvl2=kp.lvl2,
            difficulty=kp.difficulty,
            summary=kp.summary,
        ),
    )


@router.post("", response_model=KPDetail, status_code=201)
def create_knowledge_point(
    body: KPCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> KPDetail:
    """Create a new knowledge point."""
    kp = KnowledgePoint(**body.model_dump())
    db.add(kp)
    db.flush()  # get the kp.id

    AuditService.log(
        db,
        action=AuditService.CREATE,
        resource_type="knowledge_point",
        user_id=current_user.id,
        resource_id=str(kp.id),
        ip_address=get_client_ip(request),
    )
    db.commit()  # single atomic commit
    db.refresh(kp)

    return _build_detail(kp, [])


@router.post(
    "/{kp_id}/auto-associate-chunks",
    response_model=AutoAssociateResult,
    summary="LLM-match unassigned chunks under the KP's (lvl1, lvl2) and set the FK",
)
async def auto_associate_chunks(
    kp_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AutoAssociateResult:
    """Let the LLM decide which same-(lvl1, lvl2) chunks belong to this KP.

    Scope: chunks where lvl1 / lvl2 match the KP and knowledge_point_id IS NULL.
    Never touches chunks already attached to another KP.
    """
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")
    if not kp.lvl1 or not kp.lvl2:
        raise HTTPException(
            status_code=422,
            detail="KnowledgePoint is missing lvl1 / lvl2 — cannot scope candidate chunks",
        )

    candidates = (
        db.query(Chunk)
        .filter(
            Chunk.lvl1 == kp.lvl1,
            Chunk.lvl2 == kp.lvl2,
            Chunk.knowledge_point_id.is_(None),
        )
        .order_by(Chunk.created_at)
        .limit(50)
        .all()
    )
    if not candidates:
        return AutoAssociateResult(candidate_count=0, matched_chunk_ids=[])

    evidence_lines = [f"[{i}] {c.content}" for i, c in enumerate(candidates, 1)]
    prompt = (
        f"你是桥梁知识专家。以下是分类「{kp.lvl1} / {kp.lvl2}」下的一批知识块，"
        f"请逐条判断它是否属于知识点「{kp.name}」。\n\n"
        f"知识点定义：{kp.summary or kp.name}\n\n"
        "判断标准：该知识块的内容是否直接讨论、阐明、举例或涉及此知识点的某一方面。"
        "宁漏勿错——只把明显相关的标 yes；边缘/仅提到名字的标 no。\n\n"
        "候选知识块：\n"
        + "\n".join(evidence_lines)
        + "\n\n"
        '输出严格的 JSON（不要输出任何其他内容）：\n'
        '{"matches": {"1": "yes", "2": "no", ...}}'
    )

    provider = get_provider()
    try:
        response = await provider.chat([ChatMessage(role="user", content=prompt)])
    except Exception as e:
        logger.error("LLM call failed for auto-associate KP %s: %s", kp_id, e)
        raise HTTPException(
            status_code=502, detail="LLM service unavailable. Please try again later."
        )

    try:
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        parsed = json.loads(text)
        matches = parsed.get("matches", {})
        if not isinstance(matches, dict):
            raise TypeError("matches is not an object")
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error("Failed to parse auto-associate LLM response: %s\nResponse: %s",
                     e, response.content)
        raise HTTPException(
            status_code=502, detail="Failed to parse LLM response as JSON"
        )

    matched_ids: list[UUID] = []
    for idx, chunk in enumerate(candidates, 1):
        verdict = matches.get(str(idx), "")
        if isinstance(verdict, str) and verdict.strip().lower() == "yes":
            chunk.knowledge_point_id = kp.id
            chunk.lvl3 = kp.name
            matched_ids.append(chunk.id)

    AuditService.log(
        db,
        action="auto_associate_chunks",
        resource_type="knowledge_point",
        user_id=current_user.id,
        resource_id=str(kp_id),
        detail={
            "candidate_count": len(candidates),
            "matched_count": len(matched_ids),
        },
        ip_address=get_client_ip(request),
    )
    db.commit()

    return AutoAssociateResult(
        candidate_count=len(candidates),
        matched_chunk_ids=matched_ids,
    )


@router.post("/{kp_id}/sync-bridges", response_model=list[KPBridgeItem])
async def sync_bridges(
    kp_id: UUID,
    request: Request,
    use_llm: bool = Query(default=False, description="Generate relevance notes via LLM"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[KPBridgeItem]:
    """Auto-derive bridge associations from chunk taxonomy tags."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    svc = KnowledgePointBridgeService()
    provider = get_provider() if use_llm else None

    try:
        created = await svc.sync_from_chunks(db, kp_id, provider=provider)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    AuditService.log(
        db,
        action="sync_bridges",
        resource_type="knowledge_point",
        user_id=current_user.id,
        resource_id=str(kp_id),
        detail={"synced": len(created), "use_llm": use_llm},
        ip_address=get_client_ip(request),
    )
    db.commit()

    # Refresh to get generated IDs, then build response with bridge names
    for record in created:
        db.refresh(record)

    # Fetch bridge names
    bridge_ids = [r.bridge_id for r in created]
    bridges = db.query(Bridge).filter(Bridge.id.in_(bridge_ids)).all() if bridge_ids else []
    name_map = {b.id: b.name for b in bridges}

    return [
        KPBridgeItem(
            id=r.id,
            bridge_id=r.bridge_id,
            bridge_name=name_map.get(r.bridge_id, ""),
            relevance_note=r.relevance_note,
            order_index=r.order_index,
        )
        for r in created
    ]


@router.get("/{kp_id}/bridges", response_model=list[KPBridgeItem])
def list_kp_bridges(
    kp_id: UUID,
    db: Session = Depends(get_db),
) -> list[KPBridgeItem]:
    """List associated bridges with relevance notes."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    svc = KnowledgePointBridgeService()
    items = svc.list_bridges(db, kp_id)

    return [KPBridgeItem(**item) for item in items]


@router.put("/{kp_id}/bridges", response_model=list[KPBridgeItem])
def replace_kp_bridges(
    kp_id: UUID,
    body: KPBridgeReplaceRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[KPBridgeItem]:
    """Replace all bridge associations."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    svc = KnowledgePointBridgeService()
    items_data = [item.model_dump() for item in body.items]
    created = svc.replace_all(db, kp_id, items_data)

    AuditService.log(
        db,
        action="replace_bridges",
        resource_type="knowledge_point",
        user_id=current_user.id,
        resource_id=str(kp_id),
        detail={"count": len(created)},
        ip_address=get_client_ip(request),
    )
    db.commit()

    for record in created:
        db.refresh(record)

    # Fetch bridge names
    bridge_ids = [r.bridge_id for r in created]
    bridges = db.query(Bridge).filter(Bridge.id.in_(bridge_ids)).all() if bridge_ids else []
    name_map = {b.id: b.name for b in bridges}

    return [
        KPBridgeItem(
            id=r.id,
            bridge_id=r.bridge_id,
            bridge_name=name_map.get(r.bridge_id, ""),
            relevance_note=r.relevance_note,
            order_index=r.order_index,
        )
        for r in created
    ]


@router.post("/{kp_id}/generate-flashcards")
async def generate_flashcards(
    kp_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate flashcards for a knowledge point using LLM."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    generator = FlashcardBatchGenerator()
    provider = get_provider()

    try:
        cards = await generator.generate_for_kp(db, kp_id, provider)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("LLM call failed for KP %s flashcards: %s", kp_id, e)
        raise HTTPException(status_code=502, detail="LLM service unavailable. Please try again later.")

    AuditService.log(
        db,
        action="generate_flashcards",
        resource_type="knowledge_point",
        user_id=current_user.id,
        resource_id=str(kp_id),
        detail={"generated": len(cards)},
        ip_address=get_client_ip(request),
    )
    db.commit()

    # Refresh to get generated IDs
    for card in cards:
        db.refresh(card)

    return {
        "generated": len(cards),
        "cards": [
            {
                "id": str(card.id),
                "knowledge_point_id": str(card.knowledge_point_id),
                "card_type": card.card_type,
                "front_title": card.front_title,
                "front_hint": card.front_hint,
                "back_answer": card.back_answer,
                "back_key_features": card.back_key_features,
                "back_example_bridge_id": str(card.back_example_bridge_id) if card.back_example_bridge_id else None,
            }
            for card in cards
        ],
    }


@router.get("/{kp_id}", response_model=KPDetail)
def get_knowledge_point(
    kp_id: UUID,
    db: Session = Depends(get_db),
) -> KPDetail:
    """Get knowledge point detail with key points."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    key_points = (
        db.query(KnowledgePointKeyPoint)
        .filter(KnowledgePointKeyPoint.knowledge_point_id == kp_id)
        .order_by(KnowledgePointKeyPoint.order_index)
        .all()
    )

    return _build_detail(kp, key_points)


@router.put("/{kp_id}", response_model=KPDetail)
def update_knowledge_point(
    kp_id: UUID,
    body: KPUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> KPDetail:
    """Update a knowledge point."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(kp, key, value)

    db.flush()  # flush entity change

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="knowledge_point",
        user_id=current_user.id,
        resource_id=str(kp_id),
        ip_address=get_client_ip(request),
    )
    db.commit()  # single atomic commit

    return get_knowledge_point(kp_id, db)


@router.delete("/{kp_id}", status_code=204)
def delete_knowledge_point(
    kp_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a knowledge point.

    Refuses when chunks still reference the KP via knowledge_point_id. The FK
    action is SET NULL (see schema v9), which would silently orphan chunks
    from their concrete-knowledge entity — unacceptable once Phase 2 switches
    readers to this FK. Mirror the delete_taxonomy_node guard pattern: explicit
    count-check first, then savepoint + IntegrityError as defense-in-depth.
    """
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    chunk_count = (
        db.query(func.count(Chunk.id))
        .filter(Chunk.knowledge_point_id == kp_id)
        .scalar()
        or 0
    )
    if chunk_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete knowledge point with {chunk_count} associated chunk(s)",
        )

    try:
        with db.begin_nested():
            db.delete(kp)
            db.flush()
    except IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete knowledge point due to existing references",
        ) from e

    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="knowledge_point",
        user_id=current_user.id,
        resource_id=str(kp_id),
        ip_address=get_client_ip(request),
    )

    db.commit()


@router.post("/{kp_id}/generate-key-points", response_model=GenerateKeyPointsResponse)
async def generate_key_points(
    kp_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate key points for a knowledge point using LLM."""
    # 1. Find the KP and its taxonomy node
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    # Phase 3: KP is the authoritative "concrete knowledge" entity; its
    # lvl1/lvl2 columns hold the taxonomy path, and the knowledge_point_id
    # FK on chunks is the precise backlink. No TaxonomyNode join needed.
    chunks = (
        db.query(Chunk)
        .filter(Chunk.knowledge_point_id == kp.id)
        .limit(20)
        .all()
    )
    if len(chunks) < 3 and kp.lvl2:
        chunks = (
            db.query(Chunk)
            .filter(Chunk.lvl1 == kp.lvl1, Chunk.lvl2 == kp.lvl2)
            .limit(20)
            .all()
        )

    if not chunks:
        raise HTTPException(
            status_code=422,
            detail="No matching chunks found for this knowledge point's taxonomy",
        )

    # 3. Build evidence text
    evidence_parts = []
    for i, chunk in enumerate(chunks, 1):
        evidence_parts.append(f"[{i}] {chunk.content}")
    evidence = "\n\n".join(evidence_parts)

    # 4. Call LLM
    prompt = (
        f"你是桥梁知识专家。根据以下参考资料，为知识点「{kp.name}」提炼 3-7 条核心要点。\n\n"
        "要求：\n"
        "1. 每条要点包含 summary（一句话，20-40字）和 explanation（展开解释，80-200字）\n"
        "2. 每条要点标注引用的资料编号（citations），编号从1开始\n"
        "3. 按逻辑递进排序\n\n"
        f"参考资料：\n{evidence}\n\n"
        '输出严格的 JSON 格式（不要输出任何其他内容）：\n'
        '{"key_points": [{"summary": "...", "explanation": "...", "citations": [1, 2]}]}'
    )

    provider = get_provider()
    try:
        response = await provider.chat([
            ChatMessage(role="user", content=prompt),
        ])
    except Exception as e:
        logger.error("LLM call failed for KP %s: %s", kp_id, e)
        raise HTTPException(status_code=502, detail="LLM service unavailable. Please try again later.")

    # 5. Parse JSON response
    try:
        # Strip markdown code fences if present
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        parsed = json.loads(text)
        generated_kps = parsed["key_points"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error("Failed to parse LLM response: %s\nResponse: %s", e, response.content)
        raise HTTPException(
            status_code=502,
            detail="Failed to parse LLM response as JSON",
        )

    # 5b. Validate shape before iterating
    if not isinstance(generated_kps, list):
        logger.error("key_points is not a list: %s", type(generated_kps))
        raise HTTPException(status_code=502, detail="LLM returned malformed key_points")
    for i, item in enumerate(generated_kps):
        if not isinstance(item, dict):
            logger.error("key_points[%d] is not a dict: %s", i, type(item))
            raise HTTPException(status_code=502, detail="LLM returned malformed key point data")

    # 6. Transaction: delete old key_points, insert new ones
    db.query(KnowledgePointKeyPoint).filter(
        KnowledgePointKeyPoint.knowledge_point_id == kp_id
    ).delete(synchronize_session=False)

    new_key_points = []
    for idx, item in enumerate(generated_kps):
        # Map citation indices to chunk IDs (defensive: LLM may return non-int values)
        citation_indices = item.get("citations", [])
        if not isinstance(citation_indices, list):
            citation_indices = []
        chunk_ids = []
        for ci in citation_indices:
            if isinstance(ci, int) and 1 <= ci <= len(chunks):
                chunk_ids.append(chunks[ci - 1].id)

        kpkp = KnowledgePointKeyPoint(
            knowledge_point_id=kp_id,
            summary=item.get("summary", ""),
            explanation=item.get("explanation", ""),
            order_index=idx,
            chunk_ids=chunk_ids if chunk_ids else None,
        )
        db.add(kpkp)
        new_key_points.append(kpkp)

    # 7. Audit log (before commit so it's in the same transaction)
    AuditService.log(
        db,
        action="generate_key_points",
        resource_type="knowledge_point",
        user_id=current_user.id,
        resource_id=str(kp_id),
        detail={"generated": len(new_key_points)},
        ip_address=get_client_ip(request),
    )
    db.commit()

    # Refresh to get generated IDs
    for kpkp in new_key_points:
        db.refresh(kpkp)

    return {
        "generated": len(new_key_points),
        "key_points": [
            {
                "id": str(kpkp.id),
                "summary": kpkp.summary,
                "explanation": kpkp.explanation,
                "order_index": kpkp.order_index,
                "chunk_ids": [str(cid) for cid in (kpkp.chunk_ids or [])],
            }
            for kpkp in new_key_points
        ],
    }


def _to_key_point_item(kpkp: KnowledgePointKeyPoint) -> KeyPointItem:
    return KeyPointItem(
        id=kpkp.id,
        summary=kpkp.summary,
        explanation=kpkp.explanation,
        order_index=kpkp.order_index,
        chunk_ids=[str(cid) for cid in (kpkp.chunk_ids or [])],
    )


def _get_kp_or_404(db: Session, kp_id: UUID) -> KnowledgePoint:
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")
    return kp


def _get_key_point_or_404(
    db: Session, kp_id: UUID, kpkp_id: UUID
) -> KnowledgePointKeyPoint:
    kpkp = (
        db.query(KnowledgePointKeyPoint)
        .filter(
            KnowledgePointKeyPoint.id == kpkp_id,
            KnowledgePointKeyPoint.knowledge_point_id == kp_id,
        )
        .first()
    )
    if not kpkp:
        raise HTTPException(status_code=404, detail="Key point not found")
    return kpkp


@router.post(
    "/{kp_id}/key-points",
    response_model=KeyPointItem,
    status_code=201,
)
def create_key_point(
    kp_id: UUID,
    body: KeyPointCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> KeyPointItem:
    """Manually create a single key point under the KP."""
    _get_kp_or_404(db, kp_id)

    if body.order_index is None:
        current_max = (
            db.query(func.coalesce(func.max(KnowledgePointKeyPoint.order_index), -1))
            .filter(KnowledgePointKeyPoint.knowledge_point_id == kp_id)
            .scalar()
        )
        order_index = int(current_max) + 1
    else:
        order_index = body.order_index

    kpkp = KnowledgePointKeyPoint(
        knowledge_point_id=kp_id,
        summary=body.summary,
        explanation=body.explanation,
        order_index=order_index,
        chunk_ids=list(body.chunk_ids) if body.chunk_ids else None,
    )
    db.add(kpkp)
    db.flush()

    AuditService.log(
        db,
        action="create_key_point",
        resource_type="knowledge_point_key_point",
        user_id=current_user.id,
        resource_id=str(kpkp.id),
        detail={"knowledge_point_id": str(kp_id)},
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(kpkp)

    return _to_key_point_item(kpkp)


# NOTE: literal "/reorder" must be registered BEFORE the parametric
# "/{kpkp_id}" routes, otherwise FastAPI matches "reorder" as a UUID path
# param and returns 422. Same pattern as /bridges/clusters vs /{bridge_id}.
@router.put(
    "/{kp_id}/key-points/reorder",
    response_model=list[KeyPointItem],
)
def reorder_key_points(
    kp_id: UUID,
    body: KeyPointReorderRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[KeyPointItem]:
    """Replace order_index for all key points under the KP.

    Payload must cover every existing key point id for the KP. Partial
    reorders are rejected to avoid silently leaving some rows in stale
    positions relative to the new ordering.
    """
    _get_kp_or_404(db, kp_id)

    existing = (
        db.query(KnowledgePointKeyPoint)
        .filter(KnowledgePointKeyPoint.knowledge_point_id == kp_id)
        .all()
    )
    existing_ids = {kpkp.id for kpkp in existing}
    payload_ids = {item.id for item in body.items}

    if existing_ids != payload_ids:
        raise HTTPException(
            status_code=422,
            detail="Reorder payload must include every existing key point id exactly once",
        )

    order_map = {item.id: item.order_index for item in body.items}
    for kpkp in existing:
        kpkp.order_index = order_map[kpkp.id]
    db.flush()

    AuditService.log(
        db,
        action="reorder_key_points",
        resource_type="knowledge_point",
        user_id=current_user.id,
        resource_id=str(kp_id),
        detail={"count": len(existing)},
        ip_address=get_client_ip(request),
    )
    db.commit()

    existing.sort(key=lambda k: k.order_index)
    return [_to_key_point_item(kpkp) for kpkp in existing]


@router.put(
    "/{kp_id}/key-points/{kpkp_id}",
    response_model=KeyPointItem,
)
def update_key_point(
    kp_id: UUID,
    kpkp_id: UUID,
    body: KeyPointUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> KeyPointItem:
    """Partial update of a single key point (summary / explanation / chunk_ids).

    order_index is intentionally NOT updatable here — use the reorder endpoint
    to move key points, which forces callers to submit a coherent full ordering.
    """
    _get_kp_or_404(db, kp_id)
    kpkp = _get_key_point_or_404(db, kp_id, kpkp_id)

    data = body.model_dump(exclude_unset=True)
    if "summary" in data and data["summary"] is not None:
        kpkp.summary = data["summary"]
    if "explanation" in data:
        kpkp.explanation = data["explanation"]
    if "chunk_ids" in data:
        chunk_ids = data["chunk_ids"]
        kpkp.chunk_ids = list(chunk_ids) if chunk_ids else None

    db.flush()

    AuditService.log(
        db,
        action="update_key_point",
        resource_type="knowledge_point_key_point",
        user_id=current_user.id,
        resource_id=str(kpkp_id),
        detail={"knowledge_point_id": str(kp_id)},
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(kpkp)

    return _to_key_point_item(kpkp)


@router.delete(
    "/{kp_id}/key-points/{kpkp_id}",
    status_code=204,
)
def delete_key_point(
    kp_id: UUID,
    kpkp_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a single key point. Leaves order_index gaps on purpose — call
    the reorder endpoint afterwards if the caller wants a compact sequence."""
    _get_kp_or_404(db, kp_id)
    kpkp = _get_key_point_or_404(db, kp_id, kpkp_id)

    db.delete(kpkp)

    AuditService.log(
        db,
        action="delete_key_point",
        resource_type="knowledge_point_key_point",
        user_id=current_user.id,
        resource_id=str(kpkp_id),
        detail={"knowledge_point_id": str(kp_id)},
        ip_address=get_client_ip(request),
    )
    db.commit()
