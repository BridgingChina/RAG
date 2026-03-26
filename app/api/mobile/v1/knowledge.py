"""Mobile API: Knowledge tree and knowledge point detail endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.mobile.v1.schemas.common import MobileResponse
from app.core.database import get_db
from app.models import TaxonomyNode
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_key_point import KnowledgePointKeyPoint

router = APIRouter()


@router.get("/tree")
def get_knowledge_tree(
    depth: int | None = Query(default=None, ge=0, le=3),
    db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """Return the knowledge architecture tree.

    Combines taxonomy_nodes (3-level hierarchy) with knowledge_points
    (leaf entities under lvl3 nodes).
    """
    # 1. Load all taxonomy nodes
    nodes = db.query(TaxonomyNode).order_by(
        TaxonomyNode.lvl1, TaxonomyNode.lvl2, TaxonomyNode.lvl3
    ).all()

    # 2. Load all knowledge points
    kps = db.query(KnowledgePoint).all()
    kp_by_taxonomy: dict[UUID, list[dict]] = {}
    for kp in kps:
        if kp.taxonomy_node_id:
            kp_by_taxonomy.setdefault(kp.taxonomy_node_id, []).append({
                "id": str(kp.id),
                "name": kp.name,
                "type": "knowledge_point",
                "tags": [],
                "summary": kp.summary,
            })

    # 3. Build tree in memory
    lvl1_nodes: dict[str, dict] = {}
    lvl2_nodes: dict[tuple[str, str], dict] = {}

    for node in nodes:
        if node.lvl2 is None:
            if node.lvl1 not in lvl1_nodes:
                lvl1_nodes[node.lvl1] = {
                    "id": str(node.id), "name": node.lvl1, "icon_url": None, "children": [],
                }
            continue

        if node.lvl1 not in lvl1_nodes:
            lvl1_nodes[node.lvl1] = {
                "id": str(node.id), "name": node.lvl1, "icon_url": None, "children": [],
            }

        if node.lvl3 is None:
            key2 = (node.lvl1, node.lvl2)
            if key2 not in lvl2_nodes:
                lvl2_node = {"id": str(node.id), "name": node.lvl2, "children": []}
                lvl2_nodes[key2] = lvl2_node
                lvl1_nodes[node.lvl1]["children"].append(lvl2_node)
            continue

        key2 = (node.lvl1, node.lvl2)
        if key2 not in lvl2_nodes:
            lvl2_node = {"id": str(node.id), "name": node.lvl2, "children": []}
            lvl2_nodes[key2] = lvl2_node
            lvl1_nodes[node.lvl1]["children"].append(lvl2_node)

        lvl3_entry = {
            "id": str(node.id), "name": node.lvl3,
            "children": kp_by_taxonomy.get(node.id, []),
        }
        lvl2_nodes[key2]["children"].append(lvl3_entry)

    lines = list(lvl1_nodes.values())

    if depth is not None:
        if depth <= 1:
            for line in lines:
                line["children"] = []
        elif depth <= 2:
            for line in lines:
                for child in line["children"]:
                    child["children"] = []

    return MobileResponse(data={"lines": lines})


@router.get("/points/{point_id}")
def get_knowledge_point(
    point_id: UUID,
    level: str = Query(default="all", pattern="^(L0|L1|L2|all)$"),
    db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """Return knowledge point detail at specified depth level."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
    if not kp:
        raise HTTPException(404, detail="知识点不存在")

    line_info = None
    category_info = None
    if kp.taxonomy_node_id:
        tax_node = db.query(TaxonomyNode).filter(TaxonomyNode.id == kp.taxonomy_node_id).first()
        if tax_node:
            lvl1_node = db.query(TaxonomyNode).filter(
                TaxonomyNode.lvl1 == tax_node.lvl1, TaxonomyNode.lvl2.is_(None),
            ).first()
            if lvl1_node:
                line_info = {"id": str(lvl1_node.id), "name": lvl1_node.lvl1}
            if tax_node.lvl2:
                lvl2_node = db.query(TaxonomyNode).filter(
                    TaxonomyNode.lvl1 == tax_node.lvl1,
                    TaxonomyNode.lvl2 == tax_node.lvl2,
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

    result: dict = {
        "id": str(kp.id),
        "name": kp.name,
        "aliases": kp.aliases.split(",") if kp.aliases else [],
        "line": line_info,
        "category": category_info,
        "tags": [],
        "difficulty": kp.difficulty,
    }

    if level in ("L0", "L1", "all"):
        result["l0"] = {
            "key_points": [
                {"id": str(kp_item.id), "summary": kp_item.summary, "order": kp_item.order_index}
                for kp_item in key_points
            ],
            "typical_bridges_count": 0,
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

    return MobileResponse(data=result)


@router.get("/points/{point_id}/bridges")
def get_knowledge_point_bridges(
    point_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """TODO (P2): Implement via knowledge_point_bridges association table."""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
    if not kp:
        raise HTTPException(404, detail="知识点不存在")
    return MobileResponse(data={"bridges": []})
