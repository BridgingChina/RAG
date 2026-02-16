# P1 Implementation Plan: Sources, Taxonomy, Bridge Merge, Dashboard Charts

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver 4 independent feature slices for P1: Sources browsing, Taxonomy CRUD with yaml→DB migration, Bridge merge, and Dashboard recharts upgrade.

**Architecture:** Each slice is a vertical feature (backend + frontend) shipped as an independent branch/PR. Backend follows existing FastAPI + SQLAlchemy patterns. Frontend follows existing React Router lazy-loading + useApi hook patterns.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy, React + React Router + shadcn/ui, recharts (Slice 4)

**Design doc:** `docs/plans/2026-02-16-p1-sources-taxonomy-design.md`

---

## Slice 1: Sources Browsing

### Task 1: Source schema + backend endpoint

**Files:**
- Create: `app/api/v1/schemas/source.py`
- Create: `app/api/v1/sources.py`
- Modify: `app/api/v1/schemas/__init__.py`
- Modify: `app/api/v1/__init__.py`
- Create: `tests/test_api_v1_sources.py`

**Step 1: Write the failing test**

```python
# tests/test_api_v1_sources.py
"""Tests for V1 Sources API endpoint."""
from app.main import app


def test_sources_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/sources" in route_paths


def test_sources_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/sources/{source_id}" in route_paths
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_v1_sources.py -v`
Expected: FAIL — routes not found

**Step 3: Create source schemas**

```python
# app/api/v1/schemas/source.py
"""Source management schemas."""
from datetime import datetime
from pydantic import BaseModel


class SourceListItem(BaseModel):
    id: int
    type: str
    title: str
    url: str | None
    chunk_count: int
    created_at: datetime


class SourceDetail(BaseModel):
    id: int
    type: str
    title: str
    url: str | None
    file_path: str | None
    accessed_at: datetime | None
    chunk_count: int
    created_at: datetime
```

**Step 4: Create sources endpoint**

```python
# app/api/v1/sources.py
"""Sources API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.v1.schemas.common import PaginatedResponse
from app.api.v1.schemas.source import SourceDetail, SourceListItem
from app.core.database import get_db
from app.models import Chunk, Source

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=PaginatedResponse[SourceListItem])
def list_sources(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = None,
    type: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SourceListItem]:
    """List all sources with optional search and type filter."""
    query = (
        db.query(
            Source.id,
            Source.type,
            Source.title,
            Source.url,
            Source.created_at,
            func.count(Chunk.id).label("chunk_count"),
        )
        .outerjoin(Chunk, Source.id == Chunk.source_id)
        .group_by(Source.id)
    )

    if q is not None:
        query = query.filter(Source.title.ilike(f"%{q}%"))
    if type is not None:
        query = query.filter(Source.type == type)

    total = query.count()
    offset = (page - 1) * page_size
    results = query.order_by(desc(Source.created_at)).offset(offset).limit(page_size).all()

    items = [
        SourceListItem(
            id=row.id,
            type=row.type,
            title=row.title,
            url=row.url,
            chunk_count=row.chunk_count,
            created_at=row.created_at,
        )
        for row in results
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages,
    )


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(source_id: int, db: Session = Depends(get_db)) -> SourceDetail:
    """Get detailed information about a specific source."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    chunk_count = db.query(func.count(Chunk.id)).filter(Chunk.source_id == source_id).scalar()

    return SourceDetail(
        id=source.id,
        type=source.type,
        title=source.title,
        url=source.url,
        file_path=source.file_path,
        accessed_at=source.accessed_at,
        chunk_count=chunk_count,
        created_at=source.created_at,
    )
```

**Step 5: Register route and re-export schemas**

Add to `app/api/v1/__init__.py`:
```python
from app.api.v1.sources import router as sources_router
# ... inside router setup:
router.include_router(sources_router)
```

Add to `app/api/v1/schemas/__init__.py`:
```python
# Source schemas
from .source import SourceDetail, SourceListItem
# Add to __all__: "SourceDetail", "SourceListItem"
```

**Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_api_v1_sources.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add app/api/v1/schemas/source.py app/api/v1/sources.py app/api/v1/__init__.py app/api/v1/schemas/__init__.py tests/test_api_v1_sources.py
git commit -m "feat(api): add Sources list and detail endpoints"
```

---

### Task 2: Sources frontend — types, API client, routes

**Files:**
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/router.tsx`
- Modify: `web/src/components/layout/AppSidebar.tsx`

**Step 1: Add TypeScript types**

Append to `web/src/lib/types.ts`:
```typescript
// --- Sources ---

export interface SourceListItem {
  id: number
  type: string
  title: string
  url: string | null
  chunk_count: number
  created_at: string
}

export interface SourceDetail {
  id: number
  type: string
  title: string
  url: string | null
  file_path: string | null
  accessed_at: string | null
  chunk_count: number
  created_at: string
}
```

**Step 2: Add API functions**

Append to `web/src/lib/api.ts`:
```typescript
// --- Sources ---

export function fetchSources(params?: {
  page?: number
  page_size?: number
  q?: string
  type?: string
}): Promise<PaginatedResponse<SourceListItem>> {
  return get<PaginatedResponse<SourceListItem>>("/sources", params)
}

export function fetchSource(id: number): Promise<SourceDetail> {
  return get<SourceDetail>(`/sources/${id}`)
}
```

Add `SourceListItem, SourceDetail` to the imports from `"./types"`.

**Step 3: Add routes to router.tsx**

Add inside the children array of `router.tsx`:
```tsx
{ path: "sources", lazy: () => import("@/pages/SourceListPage") },
{ path: "sources/:id", lazy: () => import("@/pages/SourceDetailPage") },
```

**Step 4: Add sidebar nav item**

In `AppSidebar.tsx`, add to the "数据管理" group items array:
```typescript
{ path: "/sources", icon: FileText, label: "来源" },
```

Import `FileText` from `lucide-react` (already imported).

**Step 5: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: Errors about missing page files (that's OK, we create them next)

**Step 6: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/api.ts web/src/router.tsx web/src/components/layout/AppSidebar.tsx
git commit -m "feat(web): add Sources types, API client, routes, and sidebar nav"
```

---

### Task 3: Sources frontend — SourceListPage

**Files:**
- Create: `web/src/pages/SourceListPage.tsx`

**Step 1: Create SourceListPage**

Follow the exact pattern from `BridgeListPage.tsx`:
- `export function Component()` (lazy-loaded)
- `useApi` hook with `fetchSources`
- Search input + type filter (Select with options: pdf, web, note)
- Table with columns: type (badge), title, chunk_count, created_at
- Pagination controls
- Click row → navigate to `/sources/${id}`

**Key difference from BridgeListPage:** No "Create" button (sources are read-only, created by ingest flow).

**Step 2: Verify it compiles**

Run: `cd web && npx tsc --noEmit`
Expected: Only SourceDetailPage missing

**Step 3: Commit**

```bash
git add web/src/pages/SourceListPage.tsx
git commit -m "feat(web): add SourceListPage with search and type filter"
```

---

### Task 4: Sources frontend — SourceDetailPage

**Files:**
- Create: `web/src/pages/SourceDetailPage.tsx`

**Step 1: Create SourceDetailPage**

Layout:
- PageHeader with "Back to list" button
- Card: source metadata (type badge, title, url as link, file_path, accessed_at, chunk_count, created_at)
- Card: associated chunks — use `fetchChunks({ source_id: id })` (existing API) + same Table pattern as BridgeDetailPage chunks section

**Step 2: Verify TypeScript compiles clean**

Run: `cd web && npx tsc --noEmit`
Expected: PASS

**Step 3: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add web/src/pages/SourceDetailPage.tsx
git commit -m "feat(web): add SourceDetailPage with metadata and chunk list"
```

---

## Slice 2: Taxonomy CRUD + yaml→DB Migration

### Task 5: Taxonomy loader — DB-backed with cache

**Files:**
- Create: `app/core/taxonomy_loader.py`
- Modify: `app/core/constants.py`
- Modify: `app/core/database.py` (seed on init)
- Create: `tests/test_taxonomy_loader.py`

**Step 1: Write failing test**

```python
# tests/test_taxonomy_loader.py
"""Tests for taxonomy loader (DB-backed)."""
import pytest
from app.core.taxonomy_loader import (
    load_taxonomy_from_db,
    get_taxonomy_lvl1_from_db,
    get_taxonomy_lvl2_from_db,
    get_taxonomy_lvl3_from_db,
    invalidate_taxonomy_cache,
)


def test_taxonomy_loader_imports():
    """Verify the module and its public API exist."""
    assert callable(load_taxonomy_from_db)
    assert callable(get_taxonomy_lvl1_from_db)
    assert callable(get_taxonomy_lvl2_from_db)
    assert callable(get_taxonomy_lvl3_from_db)
    assert callable(invalidate_taxonomy_cache)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_taxonomy_loader.py -v`
Expected: FAIL — module not found

**Step 3: Create taxonomy_loader.py**

```python
# app/core/taxonomy_loader.py
"""DB-backed taxonomy loader with in-process cache.

Replaces the yaml-based @lru_cache approach in constants.py.
The cache is a module-level dict invalidated manually after CRUD operations.
"""
from sqlalchemy.orm import Session

from app.models.taxonomy import TaxonomyNode

# Module-level cache
_cache: dict[str, dict[str, list[str]]] | None = None


def invalidate_taxonomy_cache() -> None:
    """Clear the in-process taxonomy cache. Call after any CRUD op."""
    global _cache
    _cache = None


def load_taxonomy_from_db(db: Session) -> dict[str, dict[str, list[str]]]:
    """Load full taxonomy tree from DB.

    Returns:
        Nested dict: {lvl1: {lvl2: [lvl3, ...]}}
    """
    global _cache
    if _cache is not None:
        return _cache

    nodes = db.query(TaxonomyNode).all()
    tree: dict[str, dict[str, list[str]]] = {}

    for node in nodes:
        if node.lvl1 not in tree:
            tree[node.lvl1] = {}
        if node.lvl2 and node.lvl2 not in tree[node.lvl1]:
            tree[node.lvl1][node.lvl2] = []
        if node.lvl2 and node.lvl3:
            tree[node.lvl1][node.lvl2].append(node.lvl3)

    _cache = tree
    return tree


def get_taxonomy_lvl1_from_db(db: Session) -> list[str]:
    """Get list of lvl1 taxonomy categories from DB."""
    return list(load_taxonomy_from_db(db).keys())


def get_taxonomy_lvl2_from_db(db: Session, lvl1: str) -> list[str]:
    """Get list of lvl2 categories for a given lvl1 from DB."""
    taxonomy = load_taxonomy_from_db(db)
    if lvl1 in taxonomy:
        return list(taxonomy[lvl1].keys())
    return []


def get_taxonomy_lvl3_from_db(db: Session, lvl1: str, lvl2: str) -> list[str]:
    """Get list of lvl3 items for given lvl1 and lvl2 from DB."""
    taxonomy = load_taxonomy_from_db(db)
    if lvl1 in taxonomy and lvl2 in taxonomy[lvl1]:
        return taxonomy[lvl1][lvl2]
    return []
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_taxonomy_loader.py -v`
Expected: PASS

**Step 5: Modify constants.py**

Replace `load_taxonomy()`, `get_taxonomy_lvl1()`, `get_taxonomy_lvl2()`, `get_taxonomy_lvl3()` to delegate to taxonomy_loader when a DB session is available. **Keep the yaml fallback** for contexts where no DB session is passed (e.g., tagger.py which currently passes no session).

The key change: `constants.py` functions remain the same signature but use a hybrid approach:
- If called with no session → fall back to yaml (existing behavior, for tagger.py)
- A new `set_taxonomy_db_session()` can inject a session for DB reads

**Alternative approach (simpler):** Since tagger.py already receives a provider and is called within an ingest flow that has a DB session, modify tagger.py to accept taxonomy data directly. But this is a larger change. For now, keep yaml fallback in constants.py.

```python
# Modified constants.py: keep yaml functions unchanged, add db-aware variants
# The taxonomy_loader.py is the DB-backed version
# tagger.py continues to use yaml-backed load_taxonomy() unchanged
# New API endpoints will use taxonomy_loader functions directly with their DB sessions
```

**Decision:** Do NOT modify constants.py yet. The taxonomy API endpoints will use `taxonomy_loader.py` directly with their DB sessions. `tagger.py` continues using yaml-based `constants.py` unchanged. This avoids risking the ingest pipeline. Migration of tagger.py to DB can be done as a follow-up.

**Step 6: Add seed logic to init_database()**

In `app/core/database.py`, add a seed function called during `init_database()`:

```python
def _seed_taxonomy_if_empty(conn: Connection) -> None:
    """Seed taxonomy_nodes from config/taxonomy.yaml if table is empty."""
    result = conn.execute(text("SELECT COUNT(*) FROM taxonomy_nodes"))
    if result.scalar_one() > 0:
        return

    from app.core.constants import load_taxonomy
    taxonomy = load_taxonomy()

    for lvl1, lvl2_dict in taxonomy.items():
        # Insert lvl1-only node
        conn.execute(
            text("INSERT INTO taxonomy_nodes (lvl1) VALUES (:lvl1)"),
            {"lvl1": lvl1},
        )
        for lvl2, lvl3_list in lvl2_dict.items():
            # Insert lvl1+lvl2 node
            conn.execute(
                text("INSERT INTO taxonomy_nodes (lvl1, lvl2) VALUES (:lvl1, :lvl2)"),
                {"lvl1": lvl1, "lvl2": lvl2},
            )
            for lvl3 in lvl3_list:
                conn.execute(
                    text("INSERT INTO taxonomy_nodes (lvl1, lvl2, lvl3) VALUES (:lvl1, :lvl2, :lvl3)"),
                    {"lvl1": lvl1, "lvl2": lvl2, "lvl3": lvl3},
                )
```

Call `_seed_taxonomy_if_empty(conn)` after `Base.metadata.create_all(conn)` in `init_database()`.

**Step 7: Commit**

```bash
git add app/core/taxonomy_loader.py tests/test_taxonomy_loader.py app/core/database.py
git commit -m "feat: add DB-backed taxonomy loader with cache and seed logic"
```

---

### Task 6: Taxonomy API endpoints

**Files:**
- Create: `app/api/v1/schemas/taxonomy.py`
- Create: `app/api/v1/taxonomy.py`
- Modify: `app/api/v1/schemas/__init__.py`
- Modify: `app/api/v1/__init__.py`
- Create: `tests/test_api_v1_taxonomy.py`

**Step 1: Write failing test**

```python
# tests/test_api_v1_taxonomy.py
"""Tests for V1 Taxonomy API endpoint."""
from app.main import app


def test_taxonomy_tree_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/taxonomy/tree" in route_paths


def test_taxonomy_nodes_create_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/taxonomy/nodes" in route_paths


def test_taxonomy_batch_update_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/taxonomy/batch-update" in route_paths
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_v1_taxonomy.py -v`
Expected: FAIL

**Step 3: Create taxonomy schemas**

```python
# app/api/v1/schemas/taxonomy.py
"""Taxonomy management schemas."""
from __future__ import annotations
from pydantic import BaseModel


class TaxonomyNodeCreate(BaseModel):
    lvl1: str
    lvl2: str | None = None
    lvl3: str | None = None
    description: str | None = None


class TaxonomyNodeUpdate(BaseModel):
    description: str | None = None


class TaxonomyNodeDetail(BaseModel):
    id: int
    lvl1: str
    lvl2: str | None
    lvl3: str | None
    description: str | None
    chunk_count: int


class TaxonomyTreeItem(BaseModel):
    label: str
    chunk_count: int
    children: list[TaxonomyTreeItem]


class TaxonomyTree(BaseModel):
    items: list[TaxonomyTreeItem]


class TaxonomyBatchUpdate(BaseModel):
    chunk_ids: list[int]
    lvl1: str
    lvl2: str | None = None
    lvl3: str | None = None


class TaxonomyBatchUpdateResult(BaseModel):
    updated_count: int
```

**Step 4: Create taxonomy endpoint**

```python
# app/api/v1/taxonomy.py
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
```

**Step 5: Register route and re-export schemas**

Same pattern as Task 1 — add `taxonomy_router` to `__init__.py`, add taxonomy schemas to schemas `__init__.py`.

**Step 6: Run tests**

Run: `python3 -m pytest tests/test_api_v1_taxonomy.py tests/test_taxonomy_loader.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add app/api/v1/schemas/taxonomy.py app/api/v1/taxonomy.py app/api/v1/__init__.py app/api/v1/schemas/__init__.py tests/test_api_v1_taxonomy.py
git commit -m "feat(api): add Taxonomy CRUD and batch-update endpoints"
```

---

### Task 7: Taxonomy frontend — types, API client, routes

**Files:**
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/router.tsx`
- Modify: `web/src/components/layout/AppSidebar.tsx`

**Step 1: Add TypeScript types**

Append to `web/src/lib/types.ts`:
```typescript
// --- Taxonomy ---

export interface TaxonomyTreeItem {
  label: string
  chunk_count: number
  children: TaxonomyTreeItem[]
}

export interface TaxonomyTree {
  items: TaxonomyTreeItem[]
}

export interface TaxonomyNodeDetail {
  id: number
  lvl1: string
  lvl2: string | null
  lvl3: string | null
  description: string | null
  chunk_count: number
}

export interface TaxonomyNodeCreate {
  lvl1: string
  lvl2?: string | null
  lvl3?: string | null
  description?: string | null
}

export interface TaxonomyBatchUpdate {
  chunk_ids: number[]
  lvl1: string
  lvl2?: string | null
  lvl3?: string | null
}

export interface TaxonomyBatchUpdateResult {
  updated_count: number
}
```

**Step 2: Add API functions**

```typescript
// --- Taxonomy ---

export function fetchTaxonomyTree(): Promise<TaxonomyTree> {
  return get<TaxonomyTree>("/taxonomy/tree")
}

export function createTaxonomyNode(data: TaxonomyNodeCreate): Promise<TaxonomyNodeDetail> {
  return post<TaxonomyNodeDetail>("/taxonomy/nodes", data)
}

export function updateTaxonomyNode(
  id: number,
  data: { description?: string | null },
): Promise<TaxonomyNodeDetail> {
  return put<TaxonomyNodeDetail>(`/taxonomy/nodes/${id}`, data)
}

export function deleteTaxonomyNode(id: number): Promise<void> {
  return del(`/taxonomy/nodes/${id}`)
}

export function batchUpdateTaxonomy(
  data: TaxonomyBatchUpdate,
): Promise<TaxonomyBatchUpdateResult> {
  return post<TaxonomyBatchUpdateResult>("/taxonomy/batch-update", data)
}
```

**Step 3: Add route and sidebar**

Router: `{ path: "taxonomy", lazy: () => import("@/pages/TaxonomyPage") }`

Sidebar: Add "知识体系" group with `{ path: "/taxonomy", icon: FolderTree, label: "分类目录" }`. Import `FolderTree` from lucide-react.

**Step 4: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/api.ts web/src/router.tsx web/src/components/layout/AppSidebar.tsx
git commit -m "feat(web): add Taxonomy types, API client, routes, and sidebar nav"
```

---

### Task 8: Taxonomy frontend — TaxonomyPage + TaxonomyTree

**Files:**
- Create: `web/src/pages/TaxonomyPage.tsx`
- Create: `web/src/components/taxonomy/TaxonomyTree.tsx`

**Step 1: Create TaxonomyTree component**

A recursive tree component:
- Each node: expand/collapse toggle + label + chunk_count badge
- Leaf nodes: click to select (triggers onSelect callback)
- Node actions: add child, edit description (inline), delete (with confirmation)

**Step 2: Create TaxonomyPage**

Layout:
- PageHeader
- Left panel (w-1/3): TaxonomyTree + "Add top-level category" button
- Right panel (w-2/3): When a node is selected, show chunks with that taxonomy filter using `fetchChunks({ lvl1, lvl2, lvl3 })` + ChunkTable-style table
- Batch update toolbar: when chunks are selected, show "Set taxonomy" button → Dialog to pick new lvl1/lvl2/lvl3 → call batchUpdateTaxonomy

**Step 3: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: PASS

**Step 4: Run all backend tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add web/src/pages/TaxonomyPage.tsx web/src/components/taxonomy/TaxonomyTree.tsx
git commit -m "feat(web): add TaxonomyPage with tree navigation and batch update"
```

---

## Slice 3: Bridge Merge

### Task 9: Bridge merge backend endpoint

**Files:**
- Modify: `app/api/v1/schemas/bridge.py`
- Modify: `app/api/v1/bridges.py`
- Modify: `tests/test_api_v1_bridges.py`

**Step 1: Write failing test**

Append to `tests/test_api_v1_bridges.py`:
```python
def test_bridges_merge_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/bridges/{target_id}/merge" in route_paths
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_v1_bridges.py::test_bridges_merge_endpoint_exists -v`
Expected: FAIL

**Step 3: Add BridgeMergeRequest schema**

Add to `app/api/v1/schemas/bridge.py`:
```python
class BridgeMergeRequest(BaseModel):
    source_bridge_id: int
```

**Step 4: Add merge endpoint**

Add to `app/api/v1/bridges.py`:
```python
@router.post("/{target_id}/merge", response_model=BridgeDetail)
def merge_bridges(
    target_id: int, body: BridgeMergeRequest, db: Session = Depends(get_db)
) -> BridgeDetail:
    """Merge source bridge into target bridge."""
    if body.source_bridge_id == target_id:
        raise HTTPException(status_code=422, detail="Cannot merge a bridge into itself")

    target = db.query(Bridge).filter(Bridge.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target bridge not found")

    source = db.query(Bridge).filter(Bridge.id == body.source_bridge_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source bridge not found")

    # 1. Migrate primary chunks
    db.query(Chunk).filter(Chunk.bridge_id == source.id).update(
        {Chunk.bridge_id: target.id}, synchronize_session=False
    )

    # 2. Migrate chunk_bridge_links (skip duplicates)
    existing_links = set(
        db.query(ChunkBridgeLink.chunk_id)
        .filter(ChunkBridgeLink.bridge_id == target.id)
        .scalars()
        .all()
    )
    source_links = (
        db.query(ChunkBridgeLink)
        .filter(ChunkBridgeLink.bridge_id == source.id)
        .all()
    )
    for link in source_links:
        if link.chunk_id in existing_links:
            db.delete(link)
        else:
            link.bridge_id = target.id

    # 3. Merge aliases
    source_aliases = [s.strip() for s in (source.aliases or "").split(",") if s.strip()]
    source_aliases.append(source.name)
    target_aliases = [s.strip() for s in (target.aliases or "").split(",") if s.strip()]
    merged = list(dict.fromkeys(target_aliases + source_aliases))  # dedupe, preserve order
    target.aliases = ", ".join(merged) if merged else None

    # 4. Delete source bridge
    db.delete(source)
    db.commit()

    return get_bridge(target_id, db)
```

Add `BridgeMergeRequest` to the imports from schemas/bridge.

**Step 5: Run tests**

Run: `python3 -m pytest tests/test_api_v1_bridges.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add app/api/v1/schemas/bridge.py app/api/v1/bridges.py app/api/v1/schemas/__init__.py tests/test_api_v1_bridges.py
git commit -m "feat(api): add Bridge merge endpoint"
```

---

### Task 10: Bridge merge frontend

**Files:**
- Create: `web/src/components/bridges/BridgeMergeDialog.tsx`
- Modify: `web/src/pages/BridgeDetailPage.tsx`
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/lib/types.ts`

**Step 1: Add types and API function**

Add to types.ts:
```typescript
export interface BridgeMergeRequest {
  source_bridge_id: number
}
```

Add to api.ts:
```typescript
export function mergeBridge(
  targetId: number,
  data: BridgeMergeRequest,
): Promise<BridgeDetail> {
  return post<BridgeDetail>(`/bridges/${targetId}/merge`, data)
}
```

**Step 2: Create BridgeMergeDialog**

Props: `{ targetBridge: BridgeDetail, open: boolean, onOpenChange, onMerged: () => void }`

Content:
- Search input for bridge name → calls `fetchBridges({ q })` → dropdown list
- Select source bridge → show preview (source name, chunk count, "will be merged into {target}")
- Warning text: "This operation is irreversible"
- Confirm button (variant="destructive"): calls `mergeBridge(targetId, { source_bridge_id })`
- On success → call `onMerged()`, close dialog

**Step 3: Add merge button to BridgeDetailPage**

After the "Back to list" button in PageHeader, add:
```tsx
<Button variant="outline" onClick={() => setIsMergeDialogOpen(true)}>
  合并桥梁
</Button>
```

Add the MergeDialog component with `onMerged={refetch}`.

**Step 4: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: PASS

**Step 5: Commit**

```bash
git add web/src/components/bridges/BridgeMergeDialog.tsx web/src/pages/BridgeDetailPage.tsx web/src/lib/api.ts web/src/lib/types.ts
git commit -m "feat(web): add Bridge merge dialog"
```

---

## Slice 4: Dashboard Recharts Upgrade

### Task 11: Install recharts

**Step 1: Install dependency**

Run: `cd web && npm install recharts`

**Step 2: Verify it installed**

Run: `cd web && node -e "require('recharts')"`
Expected: No error

**Step 3: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "chore(web): add recharts dependency"
```

---

### Task 12: Replace Dashboard CSS charts with recharts

**Files:**
- Create: `web/src/components/dashboard/BindingPieChart.tsx`
- Create: `web/src/components/dashboard/Lvl1BarChart.tsx`
- Modify: `web/src/pages/DashboardPage.tsx`

**Step 1: Create BindingPieChart**

```tsx
// web/src/components/dashboard/BindingPieChart.tsx
import { PieChart, Pie, Cell, Legend, ResponsiveContainer, Tooltip } from "recharts"
import type { BindingDistribution } from "@/lib/types"

const COLORS = {
  primary: "#16A34A",   // green-600
  ambiguous: "#D97706", // amber-600
  none: "#D6D3D1",      // stone-300
}

const LABELS: Record<string, string> = {
  primary: "绑定",
  ambiguous: "歧义",
  none: "未绑定",
}

interface Props {
  distribution: BindingDistribution
}

export function BindingPieChart({ distribution }: Props) {
  const data = [
    { name: LABELS.primary, value: distribution.primary, key: "primary" },
    { name: LABELS.ambiguous, value: distribution.ambiguous, key: "ambiguous" },
    { name: LABELS.none, value: distribution.none, key: "none" },
  ].filter((d) => d.value > 0)

  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无数据</p>
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={90}
          dataKey="value"
          label={({ name, value }) => `${name}: ${value}`}
        >
          {data.map((entry) => (
            <Cell
              key={entry.key}
              fill={COLORS[entry.key as keyof typeof COLORS]}
            />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  )
}
```

**Step 2: Create Lvl1BarChart**

```tsx
// web/src/components/dashboard/Lvl1BarChart.tsx
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import type { Lvl1Distribution } from "@/lib/types"

interface Props {
  data: Lvl1Distribution[]
}

export function Lvl1BarChart({ data }: Props) {
  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无数据</p>
  }

  return (
    <ResponsiveContainer width="100%" height={data.length * 50 + 40}>
      <BarChart data={data} layout="vertical" margin={{ left: 80 }}>
        <XAxis type="number" />
        <YAxis type="category" dataKey="label" width={80} />
        <Tooltip />
        <Bar dataKey="count" fill="#2563EB" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
```

**Step 3: Update DashboardPage.tsx**

Replace the binding distribution section:
- Remove `DistributionBar` import
- Import `BindingPieChart` from `@/components/dashboard/BindingPieChart`
- Replace `<DistributionBar items={[...]} />` with `<BindingPieChart distribution={data.binding_distribution} />`

Replace the lvl1 distribution section:
- Import `Lvl1BarChart` from `@/components/dashboard/Lvl1BarChart`
- Replace the inline CSS progress bars IIFE with `<Lvl1BarChart data={data.lvl1_distribution} />`

**Step 4: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: PASS

**Step 5: Run all backend tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 6: Commit**

```bash
git add web/src/components/dashboard/BindingPieChart.tsx web/src/components/dashboard/Lvl1BarChart.tsx web/src/pages/DashboardPage.tsx
git commit -m "feat(web): upgrade Dashboard charts to recharts PieChart + BarChart"
```

---

## Final Verification

### Task 13: Full regression check

**Step 1: Run all backend tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass (103+ tests)

**Step 2: TypeScript type check**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 3: Frontend build**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 4: Manual smoke test**

Run: `cd web && npm run dev` (in one terminal)
Run: `uvicorn app.main:app --reload` (in another terminal, with DB running)

Verify:
- `/` — Dashboard shows recharts PieChart + BarChart
- `/sources` — Source list loads with type filter
- `/sources/:id` — Source detail shows metadata + chunks
- `/taxonomy` — Tree loads, nodes expandable, batch update works
- `/bridges/:id` — "Merge" button opens dialog
- All existing pages still work (chunks, bridges, ingest, ask)
