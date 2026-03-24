"""Taxonomy API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
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
from app.models import Chunk, TaxonomyNode, User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


@router.get("/tree", response_model=TaxonomyTree)
def get_taxonomy_tree(db: Session = Depends(get_db)) -> TaxonomyTree:
    """Get full taxonomy tree with per-node chunk counts."""
    nodes = db.query(TaxonomyNode).all()

    # Count chunks per lvl1
    lvl1_counts = dict(
        db.query(Chunk.lvl1, func.count(Chunk.id))
        .filter(Chunk.lvl1.isnot(None))
        .group_by(Chunk.lvl1)
        .all()
    )
    # Count chunks per lvl1+lvl2
    lvl2_counts = {}
    rows = (
        db.query(Chunk.lvl1, Chunk.lvl2, func.count(Chunk.id))
        .filter(Chunk.lvl1.isnot(None), Chunk.lvl2.isnot(None))
        .group_by(Chunk.lvl1, Chunk.lvl2)
        .all()
    )
    for l1, l2, cnt in rows:
        lvl2_counts[(l1, l2)] = cnt

    # Count chunks per lvl1+lvl2+lvl3
    lvl3_counts = {}
    rows = (
        db.query(Chunk.lvl1, Chunk.lvl2, Chunk.lvl3, func.count(Chunk.id))
        .filter(Chunk.lvl1.isnot(None), Chunk.lvl2.isnot(None), Chunk.lvl3.isnot(None))
        .group_by(Chunk.lvl1, Chunk.lvl2, Chunk.lvl3)
        .all()
    )
    for l1, l2, l3, cnt in rows:
        lvl3_counts[(l1, l2, l3)] = cnt

    # Build tree from nodes, tracking node IDs
    # Structure: {lvl1: (node_id, {lvl2: (node_id, {lvl3: node_id})})}
    lvl1_map: dict[str, tuple[UUID, dict[str, tuple[UUID, dict[str, UUID]]]]] = {}
    for node in nodes:
        if node.lvl1 not in lvl1_map:
            # lvl1-only node
            if not node.lvl2:
                lvl1_map[node.lvl1] = (node.id, {})
                continue
            # lvl2+ node but lvl1 entry doesn't exist yet (shouldn't happen with seed)
            lvl1_map[node.lvl1] = (0, {})
        if not node.lvl2:
            # Update lvl1 node_id if this is the lvl1-only row
            lvl1_map[node.lvl1] = (node.id, lvl1_map[node.lvl1][1])
            continue
        lvl1_id, lvl2_dict = lvl1_map[node.lvl1]
        if node.lvl2 not in lvl2_dict:
            if not node.lvl3:
                lvl2_dict[node.lvl2] = (node.id, {})
                continue
            lvl2_dict[node.lvl2] = (0, {})
        if not node.lvl3:
            lvl2_dict[node.lvl2] = (node.id, lvl2_dict[node.lvl2][1])
            continue
        lvl2_id, lvl3_dict = lvl2_dict[node.lvl2]
        lvl3_dict[node.lvl3] = node.id

    items = []
    for lvl1, (lvl1_nid, lvl2_dict) in lvl1_map.items():
        lvl2_children = []
        for lvl2, (lvl2_nid, lvl3_dict) in lvl2_dict.items():
            lvl3_children = [
                TaxonomyTreeItem(
                    node_id=nid,
                    label=lvl3,
                    chunk_count=lvl3_counts.get((lvl1, lvl2, lvl3), 0),
                    children=[],
                )
                for lvl3, nid in lvl3_dict.items()
            ]
            lvl2_children.append(
                TaxonomyTreeItem(
                    node_id=lvl2_nid,
                    label=lvl2,
                    chunk_count=lvl2_counts.get((lvl1, lvl2), 0),
                    children=lvl3_children,
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
    current_user: User = Depends(get_current_user),
) -> TaxonomyNodeDetail:
    """Create a new taxonomy node."""
    # Validate: lvl3 requires lvl2, lvl2 requires lvl1
    if body.lvl3 and not body.lvl2:
        raise HTTPException(status_code=422, detail="lvl3 requires lvl2")

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
    db.commit()
    db.refresh(node)
    invalidate_taxonomy_cache()

    AuditService.log(
        db,
        action=AuditService.CREATE,
        resource_type="taxonomy",
        user_id=current_user.id,
        resource_id=str(node.id),
        ip_address=get_client_ip(request),
    )
    db.commit()

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
    current_user: User = Depends(get_current_user),
) -> TaxonomyNodeDetail:
    """Update a taxonomy node's description."""
    node = db.query(TaxonomyNode).filter(TaxonomyNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Taxonomy node not found")

    if body.description is not None:
        node.description = body.description

    db.commit()
    db.refresh(node)
    invalidate_taxonomy_cache()

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="taxonomy",
        user_id=current_user.id,
        resource_id=str(node_id),
        ip_address=get_client_ip(request),
    )
    db.commit()

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
    current_user: User = Depends(get_current_user),
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

    # Audit log before delete so flush happens before the row is removed
    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="taxonomy",
        user_id=current_user.id,
        resource_id=str(node_id),
        ip_address=get_client_ip(request),
    )

    db.delete(node)
    db.commit()
    invalidate_taxonomy_cache()


@router.post("/batch-update", response_model=TaxonomyBatchUpdateResult)
def batch_update_chunks(
    body: TaxonomyBatchUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaxonomyBatchUpdateResult:
    """Batch update taxonomy labels on multiple chunks."""
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

    updated = (
        db.query(Chunk)
        .filter(Chunk.id.in_(body.chunk_ids))
        .update(
            {
                Chunk.lvl1: body.lvl1,
                Chunk.lvl2: body.lvl2,
                Chunk.lvl3: body.lvl3,
            },
            synchronize_session=False,
        )
    )
    db.commit()

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
    """Count chunks matching a taxonomy node's path."""
    query = db.query(func.count(Chunk.id)).filter(Chunk.lvl1 == node.lvl1)
    if node.lvl2:
        query = query.filter(Chunk.lvl2 == node.lvl2)
    if node.lvl3:
        query = query.filter(Chunk.lvl3 == node.lvl3)
    return query.scalar() or 0
