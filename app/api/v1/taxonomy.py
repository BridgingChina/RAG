"""Taxonomy API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas.taxonomy import (
    TaxonomyBatchUpdate,
    TaxonomyBatchUpdateResult,
    TaxonomyNodeCreate,
    TaxonomyNodeDetail,
    TaxonomyNodeUpdate,
    TaxonomyTree,
    TaxonomyTreeItem,
)
from app.core.database import get_db
from app.core.taxonomy_loader import invalidate_taxonomy_cache
from app.models import Chunk, KnowledgePoint, TaxonomyNode
from app.models.current_user import CurrentUser
from app.services.audit_service import AuditService
from app.services.kp_resolver import resolve_knowledge_point_id

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


@router.get("/tree", response_model=TaxonomyTree)
def get_taxonomy_tree(db: Session = Depends(get_db)) -> TaxonomyTree:
    """Get full taxonomy tree with per-node chunk counts.

    Phase 3: lvl1 → lvl2 → KnowledgePoint (3 layers). The old lvl3 taxonomy
    layer retired with Phase 3; KP now sits where lvl3 used to.
    """
    # Skeleton: only lvl1 / lvl2 taxonomy rows (lvl3 rows are being retired).
    nodes = db.query(TaxonomyNode).filter(TaxonomyNode.lvl3.is_(None)).all()

    lvl1_counts = dict(
        db.query(Chunk.lvl1, func.count(Chunk.id))
        .filter(Chunk.lvl1.isnot(None))
        .group_by(Chunk.lvl1)
        .all()
    )
    lvl2_counts = {}
    for l1, l2, cnt in (
        db.query(Chunk.lvl1, Chunk.lvl2, func.count(Chunk.id))
        .filter(Chunk.lvl1.isnot(None), Chunk.lvl2.isnot(None))
        .group_by(Chunk.lvl1, Chunk.lvl2)
        .all()
    ):
        lvl2_counts[(l1, l2)] = cnt

    kp_chunk_counts = dict(
        db.query(Chunk.knowledge_point_id, func.count(Chunk.id))
        .filter(Chunk.knowledge_point_id.isnot(None))
        .group_by(Chunk.knowledge_point_id)
        .all()
    )

    lvl1_map: dict[str, tuple[UUID, dict[str, UUID]]] = {}
    for node in nodes:
        if node.lvl2 is None:
            lvl1_map.setdefault(node.lvl1, (node.id, {}))
            if lvl1_map[node.lvl1][0] != node.id:
                lvl1_map[node.lvl1] = (node.id, lvl1_map[node.lvl1][1])
            continue
        entry = lvl1_map.setdefault(node.lvl1, (node.id, {}))
        entry[1][node.lvl2] = node.id

    kps_by_lvl2: dict[tuple[str, str], list[KnowledgePoint]] = {}
    for kp in db.query(KnowledgePoint).order_by(KnowledgePoint.name).all():
        if not kp.lvl1 or not kp.lvl2:
            continue
        kps_by_lvl2.setdefault((kp.lvl1, kp.lvl2), []).append(kp)

    items = []
    for lvl1, (lvl1_nid, lvl2_dict) in lvl1_map.items():
        lvl2_children = []
        for lvl2, lvl2_nid in lvl2_dict.items():
            kp_children = [
                TaxonomyTreeItem(
                    node_id=kp.id,
                    label=kp.name,
                    chunk_count=kp_chunk_counts.get(kp.id, 0),
                    children=[],
                )
                for kp in kps_by_lvl2.get((lvl1, lvl2), [])
            ]
            lvl2_children.append(
                TaxonomyTreeItem(
                    node_id=lvl2_nid,
                    label=lvl2,
                    chunk_count=lvl2_counts.get((lvl1, lvl2), 0),
                    children=kp_children,
                )
            )
        items.append(
            TaxonomyTreeItem(
                node_id=lvl1_nid,
                label=lvl1,
                chunk_count=lvl1_counts.get(lvl1, 0),
                children=lvl2_children,
            )
        )

    return TaxonomyTree(items=items)


@router.post("/nodes", response_model=TaxonomyNodeDetail, status_code=201)
def create_taxonomy_node(
    body: TaxonomyNodeCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TaxonomyNodeDetail:
    """Create a new taxonomy node (lvl1 or lvl2 only post-Phase 3)."""
    # Phase 3: lvl3 taxonomy rows no longer exist — concrete knowledge lives
    # in the knowledge_points table. Redirect callers to POST /knowledge-points.
    if body.lvl3:
        raise HTTPException(
            status_code=422,
            detail=(
                "lvl3 taxonomy nodes are no longer supported. "
                "Create a KnowledgePoint via POST /api/v1/knowledge-points instead."
            ),
        )
    if body.lvl2 is None and body.lvl1 is None:
        raise HTTPException(status_code=422, detail="lvl1 is required")

    # Check for duplicate
    query = db.query(TaxonomyNode).filter(TaxonomyNode.lvl1 == body.lvl1)
    if body.lvl2:
        query = query.filter(TaxonomyNode.lvl2 == body.lvl2)
    else:
        query = query.filter(TaxonomyNode.lvl2.is_(None))
    if body.lvl3:
        query = query.filter(TaxonomyNode.lvl3 == body.lvl3)
    else:
        query = query.filter(TaxonomyNode.lvl3.is_(None))

    if query.first():
        raise HTTPException(status_code=409, detail="Taxonomy node already exists")

    node = TaxonomyNode(
        lvl1=body.lvl1,
        lvl2=body.lvl2,
        lvl3=body.lvl3,
        description=body.description,
    )
    db.add(node)
    db.flush()

    AuditService.log(
        db,
        action=AuditService.CREATE,
        resource_type="taxonomy",
        user_id=current_user.id,
        resource_id=str(node.id),
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(node)
    invalidate_taxonomy_cache()

    return TaxonomyNodeDetail(
        id=node.id,
        lvl1=node.lvl1,
        lvl2=node.lvl2,
        lvl3=node.lvl3,
        description=node.description,
        chunk_count=0,
    )


@router.put("/nodes/{node_id}", response_model=TaxonomyNodeDetail)
def update_taxonomy_node(
    node_id: UUID,
    body: TaxonomyNodeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TaxonomyNodeDetail:
    """Update a taxonomy node's description."""
    node = db.query(TaxonomyNode).filter(TaxonomyNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Taxonomy node not found")

    if body.description is not None:
        node.description = body.description

    db.flush()

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="taxonomy",
        user_id=current_user.id,
        resource_id=str(node_id),
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(node)
    invalidate_taxonomy_cache()

    # Count chunks for this node
    chunk_count = _count_chunks_for_node(db, node)

    return TaxonomyNodeDetail(
        id=node.id,
        lvl1=node.lvl1,
        lvl2=node.lvl2,
        lvl3=node.lvl3,
        description=node.description,
        chunk_count=chunk_count,
    )


@router.delete("/nodes/{node_id}", status_code=204)
def delete_taxonomy_node(
    node_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a taxonomy node if no chunks reference it."""
    node = db.query(TaxonomyNode).filter(TaxonomyNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Taxonomy node not found")

    chunk_count = _count_chunks_for_node(db, node)
    if chunk_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete taxonomy node with {chunk_count} associated chunks",
        )

    kp_count = (
        db.query(func.count(KnowledgePoint.id))
        .filter(KnowledgePoint.taxonomy_node_id == node_id)
        .scalar()
        or 0
    )
    if kp_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete taxonomy node with {kp_count} associated knowledge point(s)",
        )

    # Savepoint catches any unchecked FK references (defense-in-depth for
    # future tables that add FKs to taxonomy_nodes without updating the checks
    # above). db.rollback() would nuke the outer transaction, so we use a
    # nested block that PostgreSQL implements as SAVEPOINT.
    try:
        with db.begin_nested():
            db.delete(node)
            db.flush()
    except IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete taxonomy node due to existing references",
        ) from e

    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="taxonomy",
        user_id=current_user.id,
        resource_id=str(node_id),
        ip_address=get_client_ip(request),
    )

    db.commit()
    invalidate_taxonomy_cache()


@router.post(
    "/batch-update",
    response_model=TaxonomyBatchUpdateResult,
    summary="Batch-update chunks' taxonomy tags",
    description=(
        "Reassign taxonomy labels (lvl1/lvl2/lvl3) on the specified chunks. "
        "Despite living under /taxonomy, this endpoint modifies **chunks**, "
        "not taxonomy_nodes. "
        "Deprecated name — a future version will move this to "
        "POST /chunks/batch-taxonomy-update."
    ),
    deprecated=True,
)
def batch_update_chunks(
    body: TaxonomyBatchUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TaxonomyBatchUpdateResult:
    """Batch-update taxonomy labels (lvl1/lvl2/lvl3) on multiple chunks.

    NOTE: This endpoint updates **chunk** rows, not taxonomy_nodes.
    The /taxonomy prefix is misleading; a future version will relocate
    this to POST /chunks/batch-taxonomy-update.
    """
    if not body.chunk_ids:
        raise HTTPException(status_code=422, detail="chunk_ids must not be empty")

    # Validate: lvl3 requires lvl2
    if body.lvl3 and not body.lvl2:
        raise HTTPException(status_code=422, detail="lvl3 requires lvl2")

    # Validate taxonomy path exists in taxonomy_nodes
    node_query = db.query(TaxonomyNode).filter(TaxonomyNode.lvl1 == body.lvl1)
    if body.lvl2:
        node_query = node_query.filter(TaxonomyNode.lvl2 == body.lvl2)
    else:
        node_query = node_query.filter(TaxonomyNode.lvl2.is_(None))
    if body.lvl3:
        node_query = node_query.filter(TaxonomyNode.lvl3 == body.lvl3)
    else:
        node_query = node_query.filter(TaxonomyNode.lvl3.is_(None))
    if not node_query.first():
        raise HTTPException(
            status_code=422,
            detail=f"Taxonomy path not found: {body.lvl1}/{body.lvl2 or ''}/{body.lvl3 or ''}",
        )

    resolved_kp_id = resolve_knowledge_point_id(db, body.lvl1, body.lvl2, body.lvl3)
    updated = (
        db.query(Chunk)
        .filter(Chunk.id.in_(body.chunk_ids))
        .update(
            {
                Chunk.lvl1: body.lvl1,
                Chunk.lvl2: body.lvl2,
                Chunk.lvl3: body.lvl3,
                Chunk.knowledge_point_id: resolved_kp_id,
            },
            synchronize_session=False,
        )
    )
    db.flush()

    AuditService.log(
        db,
        action=AuditService.BATCH_UPDATE,
        resource_type="taxonomy",
        user_id=current_user.id,
        detail={"chunk_ids": [str(cid) for cid in body.chunk_ids], "lvl1": body.lvl1, "lvl2": body.lvl2, "lvl3": body.lvl3},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return TaxonomyBatchUpdateResult(updated_count=updated)


def _count_chunks_for_node(db: Session, node: TaxonomyNode) -> int:
    """Count chunks matching a taxonomy node's path.

    Phase 2: lvl3 nodes count via the knowledge_point_id FK so the query
    uses ix_chunks_knowledge_point_id and picks up the same disambiguation
    the KP→TaxonomyNode relation already provides. lvl1 / lvl2 nodes have
    no FK (knowledge_points only attach to lvl3), so they remain on the
    string columns — those are dropped in Phase 3 anyway.
    """
    if node.lvl3:
        return (
            db.query(func.count(Chunk.id))
            .join(KnowledgePoint, Chunk.knowledge_point_id == KnowledgePoint.id)
            .filter(KnowledgePoint.taxonomy_node_id == node.id)
            .scalar()
            or 0
        )
    query = db.query(func.count(Chunk.id)).filter(Chunk.lvl1 == node.lvl1)
    if node.lvl2:
        query = query.filter(Chunk.lvl2 == node.lvl2)
    return query.scalar() or 0
