"""Taxonomy API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

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
from app.models import Chunk, TaxonomyNode

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

    # Build tree from nodes
    lvl1_map: dict[str, dict[str, list[str]]] = {}
    for node in nodes:
        if node.lvl1 not in lvl1_map:
            lvl1_map[node.lvl1] = {}
        if node.lvl2 and node.lvl2 not in lvl1_map[node.lvl1]:
            lvl1_map[node.lvl1][node.lvl2] = []
        if node.lvl2 and node.lvl3:
            lvl1_map[node.lvl1][node.lvl2].append(node.lvl3)

    items = []
    for lvl1, lvl2_dict in lvl1_map.items():
        lvl2_children = []
        for lvl2, lvl3_list in lvl2_dict.items():
            lvl3_children = [
                TaxonomyTreeItem(
                    label=lvl3,
                    chunk_count=lvl3_counts.get((lvl1, lvl2, lvl3), 0),
                    children=[],
                )
                for lvl3 in lvl3_list
            ]
            lvl2_children.append(
                TaxonomyTreeItem(
                    label=lvl2,
                    chunk_count=lvl2_counts.get((lvl1, lvl2), 0),
                    children=lvl3_children,
                )
            )
        items.append(
            TaxonomyTreeItem(
                label=lvl1,
                chunk_count=lvl1_counts.get(lvl1, 0),
                children=lvl2_children,
            )
        )

    return TaxonomyTree(items=items)


@router.post("/nodes", response_model=TaxonomyNodeDetail, status_code=201)
def create_taxonomy_node(
    body: TaxonomyNodeCreate, db: Session = Depends(get_db)
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
    node_id: int, body: TaxonomyNodeUpdate, db: Session = Depends(get_db)
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
def delete_taxonomy_node(node_id: int, db: Session = Depends(get_db)) -> None:
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

    db.delete(node)
    db.commit()
    invalidate_taxonomy_cache()


@router.post("/batch-update", response_model=TaxonomyBatchUpdateResult)
def batch_update_chunks(
    body: TaxonomyBatchUpdate, db: Session = Depends(get_db)
) -> TaxonomyBatchUpdateResult:
    """Batch update taxonomy labels on multiple chunks."""
    if not body.chunk_ids:
        raise HTTPException(status_code=422, detail="chunk_ids must not be empty")

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

    return TaxonomyBatchUpdateResult(updated_count=updated)


def _count_chunks_for_node(db: Session, node: TaxonomyNode) -> int:
    """Count chunks matching a taxonomy node's path."""
    query = db.query(func.count(Chunk.id)).filter(Chunk.lvl1 == node.lvl1)
    if node.lvl2:
        query = query.filter(Chunk.lvl2 == node.lvl2)
    if node.lvl3:
        query = query.filter(Chunk.lvl3 == node.lvl3)
    return query.scalar() or 0
