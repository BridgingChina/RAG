"""Public API: Knowledge tree and knowledge point detail endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.public.v1.schemas.common import PublicMeta, PublicPaginatedResponse, PublicResponse
from app.api.public.v1.serializers import localized_meta
from app.core.database import get_db
from app.models import Bridge, TaxonomyNode
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_bridge import KnowledgePointBridge
from app.models.flashcard import Flashcard
from app.models.knowledge_point_key_point import KnowledgePointKeyPoint

router = APIRouter()


def _request_locale(request: Request) -> str:
    return getattr(request.state, "locale", "zh-CN")


@router.get("/tree", response_model=PublicResponse[dict])
def get_knowledge_tree(
    request: Request,
    depth: int | None = Query(default=None, ge=0, le=3),
    db: Session = Depends(get_db),
) -> PublicResponse[dict]:
    """Return the knowledge architecture tree.

    Phase 3: lvl1 → lvl2 → KnowledgePoint (3 layers). The old lvl3
    taxonomy layer was a 1:1 mirror of KnowledgePoint, so it has been
    collapsed — the KP itself now sits where lvl3 used to.

    Public clients that previously walked 4 layers must drop the lvl3
    wrapper (see EchoBridgeCQU/web#2, EchoBridgeCQU/app#3).
    """
    locale = _request_locale(request)
    use_en = locale == "en-US"

    # 1. Skeleton: lvl1 + lvl2 rows (lvl3 rows are ignored — being retired).
    nodes = db.query(TaxonomyNode).filter(TaxonomyNode.lvl3.is_(None)).order_by(
        TaxonomyNode.lvl1,
        TaxonomyNode.lvl2.asc().nullsfirst(),
    ).all()

    lvl1_nodes: dict[str, dict] = {}
    lvl2_nodes: dict[tuple[str, str], dict] = {}

    for node in nodes:
        name_en = node.name_en
        if node.lvl2 is None:
            lvl1_display = name_en if (use_en and name_en) else node.lvl1
            if node.lvl1 not in lvl1_nodes:
                lvl1_nodes[node.lvl1] = {
                    "id": str(node.id), "name": lvl1_display,
                    "icon_url": None, "children": [],
                }
            continue

        if node.lvl1 not in lvl1_nodes:
            # lvl1 parent not yet seen (seed order); placeholder using lvl2 id
            lvl1_nodes[node.lvl1] = {
                "id": str(node.id), "name": node.lvl1,
                "icon_url": None, "children": [],
            }

        key2 = (node.lvl1, node.lvl2)
        if key2 not in lvl2_nodes:
            lvl2_display = name_en if (use_en and name_en) else node.lvl2
            lvl2_node = {"id": str(node.id), "name": lvl2_display, "children": []}
            lvl2_nodes[key2] = lvl2_node
            lvl1_nodes[node.lvl1]["children"].append(lvl2_node)

    # 2. Hang each KnowledgePoint under its (lvl1, lvl2) via its own columns.
    kps = (
        db.query(KnowledgePoint)
        .order_by(KnowledgePoint.name)
        .all()
    )
    for kp in kps:
        if not kp.lvl1 or not kp.lvl2:
            continue
        key2 = (kp.lvl1, kp.lvl2)
        if key2 not in lvl2_nodes:
            continue
        kp_name = kp.name_en if (use_en and kp.name_en) else kp.name
        kp_summary = kp.summary_en if (use_en and kp.summary_en) else kp.summary
        lvl2_nodes[key2]["children"].append({
            "id": str(kp.id),
            "name": kp_name,
            "type": "knowledge_point",
            "tags": [],
            "summary": kp_summary,
        })

    lines = list(lvl1_nodes.values())

    if depth is not None:
        if depth <= 1:
            for line in lines:
                line["children"] = []
        elif depth <= 2:
            for line in lines:
                for child in line["children"]:
                    child["children"] = []

    return PublicResponse(data={"lines": lines})


@router.get("/points/{point_id}", response_model=PublicResponse[dict])
def get_knowledge_point(
    point_id: UUID,
    request: Request,
    level: str = Query(default="all", pattern="^(L0|L1|L2|all)$"),
    db: Session = Depends(get_db),
) -> PublicResponse[dict]:
    """Return knowledge point detail at specified depth level."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
    if not kp:
        raise HTTPException(404, detail="知识点不存在")
    locale = _request_locale(request)
    use_en = locale == "en-US"

    # Phase 3: KP carries lvl1 / lvl2 directly; resolve the corresponding
    # lvl1-only and lvl2-only taxonomy_nodes rows for their UUIDs.
    line_info = None
    category_info = None
    if kp.lvl1:
        lvl1_node = db.query(TaxonomyNode).filter(
            TaxonomyNode.lvl1 == kp.lvl1, TaxonomyNode.lvl2.is_(None),
        ).first()
        if lvl1_node:
            line_info = {"id": str(lvl1_node.id), "name": lvl1_node.lvl1}
        if kp.lvl2:
            lvl2_node = db.query(TaxonomyNode).filter(
                TaxonomyNode.lvl1 == kp.lvl1,
                TaxonomyNode.lvl2 == kp.lvl2,
                TaxonomyNode.lvl3.is_(None),
            ).first()
            if lvl2_node:
                category_info = {"id": str(lvl2_node.id), "name": lvl2_node.lvl2}

    key_points = (
        db.query(KnowledgePointKeyPoint)
        .filter(KnowledgePointKeyPoint.knowledge_point_id == point_id)
        .order_by(KnowledgePointKeyPoint.order_index)
        .all()
    )

    # Tags: derive from taxonomy line + difficulty
    tags: list[str] = []
    if line_info:
        tags.append(line_info["name"])
    if kp.difficulty:
        tags.append(kp.difficulty)

    # Count associated bridges
    typical_count = db.query(KnowledgePointBridge).filter(
        KnowledgePointBridge.knowledge_point_id == point_id
    ).count()

    display_name = kp.name_en if (use_en and kp.name_en) else kp.name
    result: dict = {
        "id": str(kp.id),
        "name": display_name,
        "aliases": kp.aliases.split(",") if kp.aliases else [],
        "line": line_info,
        "category": category_info,
        "tags": tags,
        "difficulty": kp.difficulty,
    }
    fell_back = use_en and (not kp.name_en or (kp.summary and not kp.summary_en))
    meta = localized_meta(fell_back, locale)
    if meta is not None:
        result["_meta"] = meta

    if level in ("L0", "L1", "all"):
        result["l0"] = {
            "key_points": [
                {"id": str(kp_item.id), "summary": kp_item.summary, "order": kp_item.order_index}
                for kp_item in key_points
            ],
            "typical_bridges_count": typical_count,
        }

    # Build chunk_id → source mapping for citations
    all_chunk_ids: list = []
    for kp_item in key_points:
        if kp_item.chunk_ids:
            all_chunk_ids.extend(kp_item.chunk_ids)

    # Map chunk_id → source_id, then dedupe sources with stable IDs
    chunk_to_source: dict = {}
    sources: list[dict] = []
    source_id_map: dict = {}  # source.id → display index (1-based)
    if all_chunk_ids:
        from app.models import Chunk, Source
        rows = (
            db.query(Chunk.id, Source.id, Source.title, Source.type)
            .outerjoin(Source, Chunk.source_id == Source.id)
            .filter(Chunk.id.in_(all_chunk_ids))
            .all()
        )
        for chunk_id, source_id, source_title, source_type in rows:
            if source_id is None:
                continue
            chunk_to_source[chunk_id] = source_id
            if source_id not in source_id_map:
                idx = len(source_id_map) + 1
                source_id_map[source_id] = idx
                sources.append({
                    "id": idx, "title": source_title, "author": None,
                    "type": source_type, "excerpt": None, "location": None,
                })

    if level in ("L1", "all"):
        result["l1"] = {
            "key_points": [
                {
                    "id": str(kp_item.id),
                    "summary": kp_item.summary,
                    "explanation": kp_item.explanation,
                    "illustrations": [
                        {"url": url, "caption": None}
                        for url in (kp_item.illustration_urls or [])
                    ],
                    "related_terms": [],
                    "citations": sorted({
                        source_id_map[chunk_to_source[cid]]
                        for cid in (kp_item.chunk_ids or [])
                        if cid in chunk_to_source and chunk_to_source[cid] in source_id_map
                    }),
                }
                for kp_item in key_points
            ],
        }

    if level in ("L2", "all"):
        result["l2"] = kp.l2_content or {}

    result["sources"] = sources

    return PublicResponse(data=result)


@router.get("/points/{point_id}/bridges", response_model=PublicPaginatedResponse[dict])
def get_knowledge_point_bridges(
    point_id: UUID,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PublicPaginatedResponse[dict]:
    """Get bridges associated with a knowledge point."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
    if not kp:
        raise HTTPException(404, detail="知识点不存在")

    locale = _request_locale(request)
    use_en = locale == "en-US"

    base_query = db.query(KnowledgePointBridge).filter(
        KnowledgePointBridge.knowledge_point_id == point_id
    )
    total = base_query.count()

    kp_links = (
        db.query(KnowledgePointBridge, Bridge)
        .join(Bridge, KnowledgePointBridge.bridge_id == Bridge.id)
        .filter(KnowledgePointBridge.knowledge_point_id == point_id)
        .order_by(KnowledgePointBridge.order_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    bridges = [
        {
            "id": str(b.id),
            "name": (b.name_en if (use_en and b.name_en) else b.name),
            "bridge_type": b.bridge_type,
            "era": b.era, "region": b.region,
            "latitude": b.latitude, "longitude": b.longitude,
            "relevance": link.relevance_note,
        }
        for link, b in kp_links
    ]
    return PublicPaginatedResponse(
        data={"bridges": bridges},
        meta=PublicMeta(total=total, page=page, page_size=page_size),
    )


@router.get("/points/{point_id}/flashcards", response_model=PublicResponse[dict])
def get_knowledge_point_flashcards(
    point_id: UUID,
    request: Request,
    card_type: str = Query(default="all", pattern="^(all|concept|identification)$"),
    db: Session = Depends(get_db),
) -> PublicResponse[dict]:
    """Get flashcards for a knowledge point."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
    if not kp:
        raise HTTPException(404, detail="知识点不存在")

    locale = _request_locale(request)
    use_en = locale == "en-US"

    query = db.query(Flashcard).filter(Flashcard.knowledge_point_id == point_id)
    if card_type != "all":
        query = query.filter(Flashcard.card_type == card_type)

    flashcards = query.order_by(Flashcard.created_at).all()

    # Batch-resolve bridge names for example_bridge
    from app.models import Bridge
    bridge_ids = {fc.back_example_bridge_id for fc in flashcards if fc.back_example_bridge_id}
    bridge_info: dict = {}
    if bridge_ids:
        name_rows = db.query(Bridge.id, Bridge.name, Bridge.name_en).filter(
            Bridge.id.in_(bridge_ids)
        ).all()
        bridge_info = {r.id: (r.name, r.name_en) for r in name_rows}

    cards = []
    for fc in flashcards:
        example_bridge = None
        if fc.back_example_bridge_id:
            zh_name, en_name = bridge_info.get(fc.back_example_bridge_id, (None, None))
            example_bridge = {
                "id": str(fc.back_example_bridge_id),
                "name": (en_name if (use_en and en_name) else zh_name),
            }
        front_title = fc.front_title_en if (use_en and fc.front_title_en) else fc.front_title
        back_answer = fc.back_answer_en if (use_en and fc.back_answer_en) else fc.back_answer
        fell_back = use_en and (not fc.front_title_en or not fc.back_answer_en)
        card: dict = {
            "id": str(fc.id),
            "knowledge_point_id": str(fc.knowledge_point_id),
            "card_type": fc.card_type,
            "front": {"title": front_title, "hint": fc.front_hint},
            "back": {
                "answer": back_answer,
                "key_features": fc.back_key_features or [],
                "example_bridge": example_bridge,
            },
        }
        meta = localized_meta(fell_back, locale)
        if meta is not None:
            card["_meta"] = meta
        cards.append(card)

    return PublicResponse(data={"cards": cards})
