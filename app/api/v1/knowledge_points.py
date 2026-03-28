"""Admin knowledge points CRUD + LLM generate key points."""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas.common import PaginatedResponse
from app.api.v1.schemas.knowledge_point import (
    GenerateKeyPointsResponse,
    KPBridgeItem,
    KPBridgeReplaceRequest,
    KPCreate,
    KPDetail,
    KPListItem,
    KPUpdate,
    KeyPointItem,
)
from app.core.database import get_db
from app.models import Bridge, Chunk, Flashcard, KnowledgePoint, KnowledgePointKeyPoint, TaxonomyNode, User
from app.providers import ChatMessage, ZhipuProvider
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

    total = query.count()
    offset = (page - 1) * page_size
    results = query.order_by(KnowledgePoint.name).offset(offset).limit(page_size).all()

    items = [
        KPListItem(
            id=kp.id,
            name=kp.name,
            taxonomy_node_id=kp.taxonomy_node_id,
            difficulty=kp.difficulty,
            summary=kp.summary,
        )
        for kp in results
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=KPDetail, status_code=201)
def create_knowledge_point(
    body: KPCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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


@router.post("/{kp_id}/sync-bridges", response_model=list[KPBridgeItem])
async def sync_bridges(
    kp_id: UUID,
    request: Request,
    use_llm: bool = Query(default=False, description="Generate relevance notes via LLM"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[KPBridgeItem]:
    """Auto-derive bridge associations from chunk taxonomy tags."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    svc = KnowledgePointBridgeService()
    provider = ZhipuProvider() if use_llm else None

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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
):
    """Generate flashcards for a knowledge point using LLM."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    generator = FlashcardBatchGenerator()
    provider = ZhipuProvider()

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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a knowledge point (CASCADE deletes key points)."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="knowledge_point",
        user_id=current_user.id,
        resource_id=str(kp_id),
        ip_address=get_client_ip(request),
    )

    db.delete(kp)
    db.commit()


@router.post("/{kp_id}/generate-key-points", response_model=GenerateKeyPointsResponse)
async def generate_key_points(
    kp_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate key points for a knowledge point using LLM."""
    # 1. Find the KP and its taxonomy node
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).first()
    if not kp:
        raise HTTPException(status_code=404, detail="Knowledge point not found")

    taxonomy_node = None
    if kp.taxonomy_node_id:
        taxonomy_node = (
            db.query(TaxonomyNode)
            .filter(TaxonomyNode.id == kp.taxonomy_node_id)
            .first()
        )

    # 2. Query chunks matching taxonomy (lvl3 first, fallback to lvl2)
    chunks = []
    if taxonomy_node:
        if taxonomy_node.lvl3:
            chunks = (
                db.query(Chunk)
                .filter(Chunk.lvl3 == taxonomy_node.lvl3)
                .limit(20)
                .all()
            )
        if len(chunks) < 3 and taxonomy_node.lvl2:
            chunks = (
                db.query(Chunk)
                .filter(Chunk.lvl2 == taxonomy_node.lvl2)
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

    provider = ZhipuProvider()
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
