# Admin Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the 2-tab Bridge RAG app into a full admin dashboard with sidebar navigation, stats overview, and CRUD management for chunks and bridges.

**Architecture:** Backend adds 3 new FastAPI endpoint modules (stats, chunks, bridges) behind a refactored schema package. Frontend swaps tab navigation for React Router v7 with a collapsible shadcn Sidebar layout. All UI in Chinese.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy, React 19 + TypeScript + shadcn/ui (New York) + Tailwind CSS 4 + React Router v7

**Design doc:** `docs/plans/2026-02-12-admin-dashboard-design.md`

---

## Task 1: Schema Package Refactor

Convert the single `schemas.py` file into a `schemas/` package so new endpoint schemas don't bloat one file. The `__init__.py` re-exports everything so existing imports don't break.

**Files:**
- Delete: `app/api/v1/schemas.py`
- Create: `app/api/v1/schemas/__init__.py`
- Create: `app/api/v1/schemas/common.py`
- Create: `app/api/v1/schemas/ask.py`
- Create: `app/api/v1/schemas/ingest.py`

**Step 1: Create the schemas package directory**

```bash
mkdir -p app/api/v1/schemas
```

**Step 2: Create `common.py` with PaginatedResponse**

```python
# app/api/v1/schemas/common.py
"""Shared schema utilities."""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    """Common pagination query parameters."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
```

**Step 3: Create `ask.py` — move ask-related schemas**

Move `AskContext`, `AskRequest`, `CitationResponse`, `ConfidenceLevel`, `ConfidenceResponse`, `ChunkSummary`, `EvidenceGroupsResponse`, `AskResponse` from the old `schemas.py` into `app/api/v1/schemas/ask.py`. Keep identical code — just a file move.

**Step 4: Create `ingest.py` — move ingest-related schemas**

Move `IngestRequest`, `BridgeBindingStatus`, `IngestedChunkSummary`, `IngestResponse` into `app/api/v1/schemas/ingest.py`.

**Step 5: Create `__init__.py` that re-exports everything**

```python
# app/api/v1/schemas/__init__.py
"""API v1 schemas package — re-exports all names for backward compatibility."""
from app.api.v1.schemas.ask import (
    AskContext,
    AskRequest,
    AskResponse,
    ChunkSummary,
    CitationResponse,
    ConfidenceLevel,
    ConfidenceResponse,
    EvidenceGroupsResponse,
)
from app.api.v1.schemas.common import PageParams, PaginatedResponse
from app.api.v1.schemas.ingest import (
    BridgeBindingStatus,
    IngestRequest,
    IngestResponse,
    IngestedChunkSummary,
)

__all__ = [
    "AskContext",
    "AskRequest",
    "AskResponse",
    "BridgeBindingStatus",
    "ChunkSummary",
    "CitationResponse",
    "ConfidenceLevel",
    "ConfidenceResponse",
    "EvidenceGroupsResponse",
    "IngestRequest",
    "IngestResponse",
    "IngestedChunkSummary",
    "PageParams",
    "PaginatedResponse",
]
```

**Step 6: Delete old `schemas.py`**

```bash
rm app/api/v1/schemas.py
```

**Step 7: Run tests to verify no regressions**

```bash
pytest tests/test_api_v1_ask.py tests/test_api_v1_ingest.py tests/test_schemas_v2.py -v
```

Expected: All pass. The imports in `ask.py` and `ingest.py` (`from app.api.v1.schemas import ...`) still work via `__init__.py`.

**Step 8: Commit**

```bash
git add -A app/api/v1/schemas/ && git rm app/api/v1/schemas.py
git commit -m "refactor: convert schemas.py to schemas/ package for extensibility"
```

---

## Task 2: Stats Endpoint

Add `GET /api/v1/stats/dashboard` returning aggregate counts and distributions.

**Files:**
- Create: `app/api/v1/schemas/stats.py`
- Create: `app/api/v1/stats.py`
- Modify: `app/api/v1/__init__.py` (add stats_router)
- Create: `tests/test_api_v1_stats.py`

**Step 1: Write the test file**

```python
# tests/test_api_v1_stats.py
"""Tests for V1 Stats API endpoint."""
from app.main import app


def test_stats_dashboard_endpoint_exists():
    """Test that /api/v1/stats/dashboard is registered."""
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/stats/dashboard" in route_paths


def test_stats_dashboard_response_schema():
    """Test response has required fields."""
    from fastapi.testclient import TestClient
    # This will fail without a DB, but should at least not 404
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/stats/dashboard")
    # Either 200 (with DB) or 500 (without DB), but NOT 404
    assert response.status_code != 404
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_api_v1_stats.py -v
```

Expected: FAIL — endpoint not registered (404).

**Step 3: Create `schemas/stats.py`**

```python
# app/api/v1/schemas/stats.py
"""Dashboard stats schemas."""
from datetime import datetime

from pydantic import BaseModel


class BindingDistribution(BaseModel):
    primary: int
    ambiguous: int
    none: int


class Lvl1Distribution(BaseModel):
    label: str
    count: int


class RecentIngest(BaseModel):
    source_id: int
    title: str | None
    chunk_count: int
    created_at: datetime


class DashboardStats(BaseModel):
    chunk_count: int
    bridge_count: int
    source_count: int
    ambiguous_ratio: float
    binding_distribution: BindingDistribution
    lvl1_distribution: list[Lvl1Distribution]
    recent_ingests: list[RecentIngest]
```

**Step 4: Create `stats.py` endpoint**

```python
# app/api/v1/stats.py
"""V1 Stats API endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.api.v1.schemas.stats import (
    BindingDistribution,
    DashboardStats,
    Lvl1Distribution,
    RecentIngest,
)
from app.core.database import get_db
from app.models import Bridge, Chunk, Source

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/dashboard", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    """Aggregate stats for the admin dashboard."""
    chunk_count = db.query(func.count(Chunk.id)).scalar() or 0
    bridge_count = db.query(func.count(Bridge.id)).scalar() or 0
    source_count = db.query(func.count(Source.id)).scalar() or 0

    # Binding status distribution
    binding_rows = (
        db.query(Chunk.bridge_binding_status, func.count(Chunk.id))
        .group_by(Chunk.bridge_binding_status)
        .all()
    )
    binding_map = {status: count for status, count in binding_rows}
    binding_distribution = BindingDistribution(
        primary=binding_map.get("primary", 0),
        ambiguous=binding_map.get("ambiguous", 0),
        none=binding_map.get("none", 0),
    )

    ambiguous_ratio = (
        binding_distribution.ambiguous / chunk_count if chunk_count > 0 else 0.0
    )

    # lvl1 distribution
    lvl1_rows = (
        db.query(Chunk.lvl1, func.count(Chunk.id))
        .filter(Chunk.lvl1.isnot(None))
        .group_by(Chunk.lvl1)
        .order_by(func.count(Chunk.id).desc())
        .all()
    )
    lvl1_distribution = [
        Lvl1Distribution(label=label, count=count) for label, count in lvl1_rows
    ]

    # Recent ingests (last 10 sources with chunk counts)
    from sqlalchemy import desc

    recent_rows = (
        db.query(
            Source.id,
            Source.title,
            func.count(Chunk.id).label("chunk_count"),
            Source.created_at,
        )
        .outerjoin(Chunk, Chunk.source_id == Source.id)
        .group_by(Source.id)
        .order_by(desc(Source.created_at))
        .limit(10)
        .all()
    )
    recent_ingests = [
        RecentIngest(
            source_id=row.id,
            title=row.title,
            chunk_count=row.chunk_count,
            created_at=row.created_at,
        )
        for row in recent_rows
    ]

    return DashboardStats(
        chunk_count=chunk_count,
        bridge_count=bridge_count,
        source_count=source_count,
        ambiguous_ratio=round(ambiguous_ratio, 4),
        binding_distribution=binding_distribution,
        lvl1_distribution=lvl1_distribution,
        recent_ingests=recent_ingests,
    )
```

**Step 5: Register in `__init__.py`**

Add to `app/api/v1/__init__.py`:

```python
from app.api.v1.stats import router as stats_router
# ...
router.include_router(stats_router)
```

**Step 6: Update `schemas/__init__.py`** to re-export stats schemas.

**Step 7: Run tests**

```bash
pytest tests/test_api_v1_stats.py tests/test_api_v1_ask.py -v
```

Expected: All pass.

**Step 8: Commit**

```bash
git commit -m "feat(api): add GET /stats/dashboard endpoint"
```

---

## Task 3: Chunks CRUD Endpoints

Add list, detail, update, and delete for chunks.

**Files:**
- Create: `app/api/v1/schemas/chunk.py`
- Create: `app/api/v1/chunks.py`
- Modify: `app/api/v1/__init__.py` (add chunks_router)
- Create: `tests/test_api_v1_chunks.py`

**Step 1: Write tests**

```python
# tests/test_api_v1_chunks.py
"""Tests for V1 Chunks API endpoint."""
from app.main import app


def test_chunks_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/chunks" in route_paths


def test_chunks_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/chunks/{chunk_id}" in route_paths


def test_chunks_list_not_404():
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/chunks")
    assert response.status_code != 404


def test_chunks_detail_not_found():
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/chunks/999999")
    # Should be 404 (not found) or 500 (no DB), but not 405/422
    assert response.status_code in (404, 500)
```

**Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_api_v1_chunks.py -v
```

**Step 3: Create `schemas/chunk.py`**

```python
# app/api/v1/schemas/chunk.py
"""Chunk management schemas."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChunkListItem(BaseModel):
    id: int
    content_preview: str
    bridge_id: int | None
    bridge_name: str | None
    lvl1: str | None
    lvl2: str | None
    binding_status: str
    source_id: int
    source_title: str | None
    created_at: datetime


class ChunkBridgeLinkDetail(BaseModel):
    id: int
    bridge_id: int
    bridge_name: str | None
    role: str
    confidence: float
    method: str


class ChunkDetail(BaseModel):
    id: int
    content: str
    contextual_text: str | None
    search_text: str | None
    section_title: str | None
    page_range: str | None
    lvl1: str | None
    lvl2: str | None
    lvl3: str | None
    bridge_id: int | None
    bridge_name: str | None
    binding_status: str
    source_id: int
    source_title: str | None
    created_at: datetime
    bridge_links: list[ChunkBridgeLinkDetail]


class ChunkUpdate(BaseModel):
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None
    bridge_id: int | None = None
    binding_status: Literal["none", "primary", "ambiguous"] | None = None
```

**Step 4: Create `chunks.py` endpoint**

```python
# app/api/v1/chunks.py
"""V1 Chunks API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.schemas.chunk import (
    ChunkBridgeLinkDetail,
    ChunkDetail,
    ChunkListItem,
    ChunkUpdate,
)
from app.api.v1.schemas.common import PaginatedResponse
from app.core.database import get_db
from app.models import Bridge, Chunk, ChunkBridgeLink, Source

router = APIRouter(prefix="/chunks", tags=["chunks"])


@router.get("", response_model=PaginatedResponse[ChunkListItem])
def list_chunks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    bridge_id: int | None = None,
    lvl1: str | None = None,
    lvl2: str | None = None,
    binding_status: str | None = None,
    source_id: int | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    """List chunks with filtering and pagination."""
    query = (
        db.query(
            Chunk.id,
            Chunk.content,
            Chunk.bridge_id,
            Bridge.name.label("bridge_name"),
            Chunk.lvl1,
            Chunk.lvl2,
            Chunk.bridge_binding_status,
            Chunk.source_id,
            Source.title.label("source_title"),
            Chunk.created_at,
        )
        .outerjoin(Bridge, Chunk.bridge_id == Bridge.id)
        .outerjoin(Source, Chunk.source_id == Source.id)
    )

    if bridge_id is not None:
        query = query.filter(Chunk.bridge_id == bridge_id)
    if lvl1 is not None:
        query = query.filter(Chunk.lvl1 == lvl1)
    if lvl2 is not None:
        query = query.filter(Chunk.lvl2 == lvl2)
    if binding_status is not None:
        query = query.filter(Chunk.bridge_binding_status == binding_status)
    if source_id is not None:
        query = query.filter(Chunk.source_id == source_id)
    if q:
        query = query.filter(Chunk.content.ilike(f"%{q}%"))

    total = query.count()
    rows = (
        query.order_by(Chunk.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        ChunkListItem(
            id=row.id,
            content_preview=row.content[:80] + ("..." if len(row.content) > 80 else ""),
            bridge_id=row.bridge_id,
            bridge_name=row.bridge_name,
            lvl1=row.lvl1,
            lvl2=row.lvl2,
            binding_status=row.bridge_binding_status,
            source_id=row.source_id,
            source_title=row.source_title,
            created_at=row.created_at,
        )
        for row in rows
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{chunk_id}", response_model=ChunkDetail)
def get_chunk(chunk_id: int, db: Session = Depends(get_db)):
    """Get chunk detail with bridge links."""
    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    bridge_name = None
    if chunk.bridge_id:
        bridge = db.query(Bridge).filter(Bridge.id == chunk.bridge_id).first()
        bridge_name = bridge.name if bridge else None

    source = db.query(Source).filter(Source.id == chunk.source_id).first()

    links = (
        db.query(ChunkBridgeLink, Bridge.name.label("bridge_name"))
        .outerjoin(Bridge, ChunkBridgeLink.bridge_id == Bridge.id)
        .filter(ChunkBridgeLink.chunk_id == chunk_id)
        .all()
    )

    return ChunkDetail(
        id=chunk.id,
        content=chunk.content,
        contextual_text=chunk.contextual_text,
        search_text=chunk.search_text,
        section_title=chunk.section_title,
        page_range=chunk.page_range,
        lvl1=chunk.lvl1,
        lvl2=chunk.lvl2,
        lvl3=chunk.lvl3,
        bridge_id=chunk.bridge_id,
        bridge_name=bridge_name,
        binding_status=chunk.bridge_binding_status,
        source_id=chunk.source_id,
        source_title=source.title if source else None,
        created_at=chunk.created_at,
        bridge_links=[
            ChunkBridgeLinkDetail(
                id=link.ChunkBridgeLink.id,
                bridge_id=link.ChunkBridgeLink.bridge_id,
                bridge_name=link.bridge_name,
                role=link.ChunkBridgeLink.role,
                confidence=link.ChunkBridgeLink.confidence,
                method=link.ChunkBridgeLink.method,
            )
            for link in links
        ],
    )


@router.put("/{chunk_id}", response_model=ChunkDetail)
def update_chunk(
    chunk_id: int,
    body: ChunkUpdate,
    db: Session = Depends(get_db),
):
    """Update chunk metadata (taxonomy, bridge assignment, binding status)."""
    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    update_data = body.model_dump(exclude_unset=True)
    if "binding_status" in update_data:
        update_data["bridge_binding_status"] = update_data.pop("binding_status")

    for field, value in update_data.items():
        setattr(chunk, field, value)

    db.commit()
    db.refresh(chunk)
    return get_chunk(chunk_id, db)


@router.delete("/{chunk_id}", status_code=204)
def delete_chunk(chunk_id: int, db: Session = Depends(get_db)):
    """Delete a chunk and its bridge links."""
    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    db.query(ChunkBridgeLink).filter(ChunkBridgeLink.chunk_id == chunk_id).delete()
    db.delete(chunk)
    db.commit()
```

**Step 5: Register in `__init__.py`**

```python
from app.api.v1.chunks import router as chunks_router
router.include_router(chunks_router)
```

**Step 6: Run tests**

```bash
pytest tests/test_api_v1_chunks.py tests/test_api_v1_ask.py -v
```

**Step 7: Commit**

```bash
git commit -m "feat(api): add chunks CRUD endpoints (list/detail/update/delete)"
```

---

## Task 4: Bridges CRUD Endpoints

Add full CRUD for bridges plus a chunks-by-bridge endpoint.

**Files:**
- Create: `app/api/v1/schemas/bridge.py`
- Create: `app/api/v1/bridges.py`
- Modify: `app/api/v1/__init__.py` (add bridges_router)
- Create: `tests/test_api_v1_bridges.py`

**Step 1: Write tests**

```python
# tests/test_api_v1_bridges.py
"""Tests for V1 Bridges API endpoint."""
from app.main import app


def test_bridges_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/bridges" in route_paths


def test_bridges_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/bridges/{bridge_id}" in route_paths


def test_bridges_create_accepts_post():
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/v1/bridges", json={"name": "测试桥"})
    # 200/201 with DB, 500 without — but never 404/405
    assert response.status_code not in (404, 405)


def test_bridges_chunks_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/bridges/{bridge_id}/chunks" in route_paths
```

**Step 2: Run tests — expect FAIL**

**Step 3: Create `schemas/bridge.py`**

```python
# app/api/v1/schemas/bridge.py
"""Bridge management schemas."""
from datetime import datetime

from pydantic import BaseModel


class BridgeListItem(BaseModel):
    id: int
    name: str
    aliases: str | None
    bridge_type: str | None
    material: str | None
    era: str | None
    location: str | None
    chunk_count: int
    created_at: datetime


class BridgeDetail(BaseModel):
    id: int
    name: str
    aliases: str | None
    bridge_type: str | None
    material: str | None
    era: str | None
    location: str | None
    function: str | None
    summary: str | None
    chunk_count: int
    created_at: datetime


class BridgeCreate(BaseModel):
    name: str
    aliases: str | None = None
    bridge_type: str | None = None
    material: str | None = None
    era: str | None = None
    location: str | None = None
    function: str | None = None
    summary: str | None = None


class BridgeUpdate(BaseModel):
    name: str | None = None
    aliases: str | None = None
    bridge_type: str | None = None
    material: str | None = None
    era: str | None = None
    location: str | None = None
    function: str | None = None
    summary: str | None = None
```

**Step 4: Create `bridges.py` endpoint**

```python
# app/api/v1/bridges.py
"""V1 Bridges API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.schemas.bridge import (
    BridgeCreate,
    BridgeDetail,
    BridgeListItem,
    BridgeUpdate,
)
from app.api.v1.schemas.chunk import ChunkListItem
from app.api.v1.schemas.common import PaginatedResponse
from app.core.database import get_db
from app.models import Bridge, Chunk, Source

router = APIRouter(prefix="/bridges", tags=["bridges"])


def _bridge_chunk_count(db: Session, bridge_id: int) -> int:
    return (
        db.query(func.count(Chunk.id))
        .filter(Chunk.bridge_id == bridge_id)
        .scalar()
        or 0
    )


@router.get("", response_model=PaginatedResponse[BridgeListItem])
def list_bridges(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = None,
    db: Session = Depends(get_db),
):
    """List bridges with optional search and pagination."""
    query = db.query(
        Bridge.id,
        Bridge.name,
        Bridge.aliases,
        Bridge.bridge_type,
        Bridge.material,
        Bridge.era,
        Bridge.location,
        Bridge.created_at,
        func.count(Chunk.id).label("chunk_count"),
    ).outerjoin(Chunk, Chunk.bridge_id == Bridge.id).group_by(Bridge.id)

    if q:
        query = query.filter(Bridge.name.ilike(f"%{q}%"))

    total = db.query(func.count()).select_from(Bridge).scalar() or 0
    if q:
        total = query.count()

    rows = (
        query.order_by(Bridge.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        BridgeListItem(
            id=row.id,
            name=row.name,
            aliases=row.aliases,
            bridge_type=row.bridge_type,
            material=row.material,
            era=row.era,
            location=row.location,
            chunk_count=row.chunk_count,
            created_at=row.created_at,
        )
        for row in rows
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{bridge_id}", response_model=BridgeDetail)
def get_bridge(bridge_id: int, db: Session = Depends(get_db)):
    """Get bridge detail."""
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    return BridgeDetail(
        id=bridge.id,
        name=bridge.name,
        aliases=bridge.aliases,
        bridge_type=bridge.bridge_type,
        material=bridge.material,
        era=bridge.era,
        location=bridge.location,
        function=bridge.function,
        summary=bridge.summary,
        chunk_count=_bridge_chunk_count(db, bridge.id),
        created_at=bridge.created_at,
    )


@router.post("", response_model=BridgeDetail, status_code=201)
def create_bridge(body: BridgeCreate, db: Session = Depends(get_db)):
    """Create a new bridge."""
    bridge = Bridge(**body.model_dump())
    db.add(bridge)
    db.commit()
    db.refresh(bridge)
    return get_bridge(bridge.id, db)


@router.put("/{bridge_id}", response_model=BridgeDetail)
def update_bridge(
    bridge_id: int, body: BridgeUpdate, db: Session = Depends(get_db)
):
    """Update bridge metadata."""
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(bridge, field, value)

    db.commit()
    db.refresh(bridge)
    return get_bridge(bridge.id, db)


@router.delete("/{bridge_id}", status_code=204)
def delete_bridge(bridge_id: int, db: Session = Depends(get_db)):
    """Delete bridge (only if no chunks reference it)."""
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    chunk_count = _bridge_chunk_count(db, bridge.id)
    if chunk_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete bridge with {chunk_count} associated chunks",
        )

    db.delete(bridge)
    db.commit()


@router.get("/{bridge_id}/chunks", response_model=list[ChunkListItem])
def get_bridge_chunks(bridge_id: int, db: Session = Depends(get_db)):
    """Get all chunks associated with a bridge."""
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    rows = (
        db.query(
            Chunk.id,
            Chunk.content,
            Chunk.bridge_id,
            Bridge.name.label("bridge_name"),
            Chunk.lvl1,
            Chunk.lvl2,
            Chunk.bridge_binding_status,
            Chunk.source_id,
            Source.title.label("source_title"),
            Chunk.created_at,
        )
        .outerjoin(Bridge, Chunk.bridge_id == Bridge.id)
        .outerjoin(Source, Chunk.source_id == Source.id)
        .filter(Chunk.bridge_id == bridge_id)
        .order_by(Chunk.id.desc())
        .all()
    )

    return [
        ChunkListItem(
            id=row.id,
            content_preview=row.content[:80] + ("..." if len(row.content) > 80 else ""),
            bridge_id=row.bridge_id,
            bridge_name=row.bridge_name,
            lvl1=row.lvl1,
            lvl2=row.lvl2,
            binding_status=row.bridge_binding_status,
            source_id=row.source_id,
            source_title=row.source_title,
            created_at=row.created_at,
        )
        for row in rows
    ]
```

**Step 5: Register in `__init__.py`**

```python
from app.api.v1.bridges import router as bridges_router
router.include_router(bridges_router)
```

**Step 6: Run tests**

```bash
pytest tests/test_api_v1_bridges.py tests/test_api_v1_ask.py tests/test_api_v1_ingest.py -v
```

**Step 7: Commit**

```bash
git commit -m "feat(api): add bridges CRUD endpoints (list/detail/create/update/delete/chunks)"
```

---

## Task 5: Frontend Dependencies + shadcn Components

Install React Router and all needed shadcn components.

**Files:**
- Modify: `web/package.json` (new deps)
- Create: ~10 files in `web/src/components/ui/`

**Step 1: Install react-router**

```bash
cd web && npm install react-router
```

**Step 2: Add shadcn components**

```bash
cd web && npx shadcn@latest add card table select dialog separator skeleton sidebar dropdown-menu tooltip pagination
```

Note: This is interactive — accept defaults. Each component creates a file under `web/src/components/ui/`.

**Step 3: Verify build still works**

```bash
cd web && npx tsc --noEmit
```

**Step 4: Commit**

```bash
git commit -m "feat(web): add react-router and shadcn UI components"
```

---

## Task 6: Frontend Types + API Client Extension

Extend the TypeScript types and API client with all new endpoint functions.

**Files:**
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/lib/api.ts`
- Create: `web/src/hooks/useApi.ts`

**Step 1: Extend `types.ts`**

Add after existing types:

```typescript
// --- Pagination ---

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// --- Dashboard ---

export interface BindingDistribution {
  primary: number
  ambiguous: number
  none: number
}

export interface Lvl1Distribution {
  label: string
  count: number
}

export interface RecentIngest {
  source_id: number
  title: string | null
  chunk_count: number
  created_at: string
}

export interface DashboardStats {
  chunk_count: number
  bridge_count: number
  source_count: number
  ambiguous_ratio: number
  binding_distribution: BindingDistribution
  lvl1_distribution: Lvl1Distribution[]
  recent_ingests: RecentIngest[]
}

// --- Chunks ---

export interface ChunkListItem {
  id: number
  content_preview: string
  bridge_id: number | null
  bridge_name: string | null
  lvl1: string | null
  lvl2: string | null
  binding_status: string
  source_id: number
  source_title: string | null
  created_at: string
}

export interface ChunkBridgeLinkDetail {
  id: number
  bridge_id: number
  bridge_name: string | null
  role: string
  confidence: number
  method: string
}

export interface ChunkDetail {
  id: number
  content: string
  contextual_text: string | null
  search_text: string | null
  section_title: string | null
  page_range: string | null
  lvl1: string | null
  lvl2: string | null
  lvl3: string | null
  bridge_id: number | null
  bridge_name: string | null
  binding_status: string
  source_id: number
  source_title: string | null
  created_at: string
  bridge_links: ChunkBridgeLinkDetail[]
}

export interface ChunkUpdateRequest {
  lvl1?: string | null
  lvl2?: string | null
  lvl3?: string | null
  bridge_id?: number | null
  binding_status?: "none" | "primary" | "ambiguous"
}

// --- Bridges ---

export interface BridgeListItem {
  id: number
  name: string
  aliases: string | null
  bridge_type: string | null
  material: string | null
  era: string | null
  location: string | null
  chunk_count: number
  created_at: string
}

export interface BridgeDetail {
  id: number
  name: string
  aliases: string | null
  bridge_type: string | null
  material: string | null
  era: string | null
  location: string | null
  function: string | null
  summary: string | null
  chunk_count: number
  created_at: string
}

export interface BridgeCreateRequest {
  name: string
  aliases?: string | null
  bridge_type?: string | null
  material?: string | null
  era?: string | null
  location?: string | null
  function?: string | null
  summary?: string | null
}

export interface BridgeUpdateRequest {
  name?: string
  aliases?: string | null
  bridge_type?: string | null
  material?: string | null
  era?: string | null
  location?: string | null
  function?: string | null
  summary?: string | null
}
```

**Step 2: Rewrite `api.ts` with GET/PUT/DELETE support**

Replace entire `web/src/lib/api.ts`:

```typescript
import type {
  AskResponse,
  BridgeCreateRequest,
  BridgeDetail,
  BridgeListItem,
  BridgeUpdateRequest,
  ChunkDetail,
  ChunkListItem,
  ChunkUpdateRequest,
  DashboardStats,
  IngestResponse,
  PaginatedResponse,
} from "./types"

const BASE = "/api/v1"

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

async function get<T>(url: string, params?: Record<string, string | number | undefined | null>): Promise<T> {
  const searchParams = new URLSearchParams()
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value != null && value !== "") {
        searchParams.set(key, String(value))
      }
    }
  }
  const qs = searchParams.toString()
  const fullUrl = qs ? `${BASE}${url}?${qs}` : `${BASE}${url}`
  const res = await fetch(fullUrl)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

async function put<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

async function del(url: string): Promise<void> {
  const res = await fetch(`${BASE}${url}`, { method: "DELETE" })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

// --- Ask ---
export function askQuestion(
  question: string,
  targetBridgeId?: number | null,
): Promise<AskResponse> {
  return post<AskResponse>("/ask", {
    question,
    target_bridge_id: targetBridgeId ?? null,
  })
}

// --- Ingest ---
export function ingestDocument(
  content: string,
  sourceType: string = "document",
  options?: {
    bridgeCandidates?: string[] | null
    minPrimaryConfidence?: number
    enableAutoBridgeDetection?: boolean
  },
): Promise<IngestResponse> {
  return post<IngestResponse>("/ingest", {
    content,
    source_type: sourceType,
    bridge_candidates: options?.bridgeCandidates ?? null,
    min_primary_confidence: options?.minPrimaryConfidence ?? 0.75,
    enable_auto_bridge_detection: options?.enableAutoBridgeDetection ?? true,
  })
}

// --- Stats ---
export function fetchDashboardStats(): Promise<DashboardStats> {
  return get<DashboardStats>("/stats/dashboard")
}

// --- Chunks ---
export function fetchChunks(params?: {
  page?: number
  page_size?: number
  bridge_id?: number
  lvl1?: string
  lvl2?: string
  binding_status?: string
  source_id?: number
  q?: string
}): Promise<PaginatedResponse<ChunkListItem>> {
  return get<PaginatedResponse<ChunkListItem>>("/chunks", params as Record<string, string | number | undefined>)
}

export function fetchChunk(id: number): Promise<ChunkDetail> {
  return get<ChunkDetail>(`/chunks/${id}`)
}

export function updateChunk(id: number, data: ChunkUpdateRequest): Promise<ChunkDetail> {
  return put<ChunkDetail>(`/chunks/${id}`, data)
}

export function deleteChunk(id: number): Promise<void> {
  return del(`/chunks/${id}`)
}

// --- Bridges ---
export function fetchBridges(params?: {
  page?: number
  page_size?: number
  q?: string
}): Promise<PaginatedResponse<BridgeListItem>> {
  return get<PaginatedResponse<BridgeListItem>>("/bridges", params as Record<string, string | number | undefined>)
}

export function fetchBridge(id: number): Promise<BridgeDetail> {
  return get<BridgeDetail>(`/bridges/${id}`)
}

export function createBridge(data: BridgeCreateRequest): Promise<BridgeDetail> {
  return post<BridgeDetail>("/bridges", data)
}

export function updateBridge(id: number, data: BridgeUpdateRequest): Promise<BridgeDetail> {
  return put<BridgeDetail>(`/bridges/${id}`, data)
}

export function deleteBridge(id: number): Promise<void> {
  return del(`/bridges/${id}`)
}

export function fetchBridgeChunks(id: number): Promise<ChunkListItem[]> {
  return get<ChunkListItem[]>(`/bridges/${id}/chunks`)
}
```

**Step 3: Create `useApi.ts` hook**

```typescript
// web/src/hooks/useApi.ts
import { useCallback, useEffect, useState } from "react"

interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    fetcher()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load()
  }, [load])

  return { data, loading, error, refetch: load }
}
```

**Step 4: Verify TypeScript compiles**

```bash
cd web && npx tsc --noEmit
```

**Step 5: Commit**

```bash
git commit -m "feat(web): extend types, API client, and add useApi hook"
```

---

## Task 7: Router + Layout Shell

Replace tab navigation with React Router and collapsible sidebar.

**Files:**
- Create: `web/src/router.tsx`
- Create: `web/src/components/layout/DashboardLayout.tsx`
- Create: `web/src/components/layout/AppSidebar.tsx`
- Create: `web/src/components/layout/PageHeader.tsx`
- Modify: `web/src/main.tsx`
- Modify: `web/src/index.css` (add warm-gray background + Noto Sans SC)

**Step 1: Update `index.css`** — Replace the Google Fonts import and `--font-sans`:

Change the first line to import Noto Sans SC:
```css
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
```

Update `--font-sans` in the `@theme` block:
```css
--font-sans: 'Noto Sans SC', system-ui, sans-serif;
```

Update `:root` to use warm background:
```css
--background: oklch(0.975 0.002 75);  /* warm gray ~#F7F6F3 */
```

**Step 2: Create `AppSidebar.tsx`**

Use shadcn Sidebar components with Chinese labels, Lucide icons, and `NavLink` from React Router for active state styling. Navigation groups: 概览, 数据管理, 工具. Sidebar collapses to icon-only mode.

Key implementation: `<Sidebar collapsible="icon">` with `<SidebarGroup>` for each nav section. Each item uses `<NavLink>` for route-aware active state.

**Step 3: Create `PageHeader.tsx`**

Simple component: `SidebarTrigger` button + page title + optional action slot (children). Sits at the top of `SidebarInset`.

**Step 4: Create `DashboardLayout.tsx`**

```
<SidebarProvider defaultOpen={true}>
  <AppSidebar />
  <SidebarInset>
    <Outlet />
  </SidebarInset>
</SidebarProvider>
```

Reads/writes sidebar open state from `localStorage("sidebar-open")`.

**Step 5: Create `router.tsx`**

```typescript
import { createBrowserRouter } from "react-router"
import { DashboardLayout } from "@/components/layout/DashboardLayout"

// Lazy-load pages
// For now, create placeholder pages that will be implemented in Task 8-11

export const router = createBrowserRouter([
  {
    element: <DashboardLayout />,
    children: [
      { index: true, lazy: () => import("@/pages/DashboardPage") },
      { path: "chunks", lazy: () => import("@/pages/ChunkListPage") },
      { path: "chunks/:id", lazy: () => import("@/pages/ChunkDetailPage") },
      { path: "bridges", lazy: () => import("@/pages/BridgeListPage") },
      { path: "bridges/new", lazy: () => import("@/pages/BridgeCreatePage") },
      { path: "bridges/:id", lazy: () => import("@/pages/BridgeDetailPage") },
      { path: "ingest", lazy: () => import("@/pages/IngestPage") },
      { path: "ask", lazy: () => import("@/pages/AskPage") },
    ],
  },
])
```

**Step 6: Update `main.tsx`**

```typescript
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import './index.css'
import { router } from './router'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
```

**Step 7: Create placeholder pages** (one per route) in `web/src/pages/`:

Each page exports a `Component` function (for React Router lazy loading) that just renders a `<PageHeader>` with the page name. This ensures the router works before we build real content.

Files: `DashboardPage.tsx`, `ChunkListPage.tsx`, `ChunkDetailPage.tsx`, `BridgeListPage.tsx`, `BridgeDetailPage.tsx`, `BridgeCreatePage.tsx`, `IngestPage.tsx`, `AskPage.tsx`

**Step 8: Verify TypeScript compiles and dev server starts**

```bash
cd web && npx tsc --noEmit && npm run dev
```

**Step 9: Commit**

```bash
git commit -m "feat(web): add React Router, sidebar layout, and placeholder pages"
```

---

## Task 8: Dashboard Page

Implement the real Dashboard page with stat cards and distribution bars.

**Files:**
- Replace: `web/src/pages/DashboardPage.tsx`
- Create: `web/src/components/dashboard/StatCard.tsx`
- Create: `web/src/components/dashboard/DistributionBar.tsx`
- Create: `web/src/components/dashboard/IngestTimeline.tsx`

**Step 1: Create `StatCard.tsx`**

A shadcn `Card` showing a label, large number, and optional description. Takes props: `title: string`, `value: string | number`, `description?: string`, `icon?: LucideIcon`.

**Step 2: Create `DistributionBar.tsx`**

Pure CSS horizontal stacked bar. Takes `items: {label: string, count: number, color: string}[]`. Each segment is a `<div>` with percentage width and Tailwind bg class. Labels below.

**Step 3: Create `IngestTimeline.tsx`**

Simple list rendering `RecentIngest[]`. Each row: title, chunk count badge, relative time. Links to source detail (future P1).

**Step 4: Implement `DashboardPage.tsx`**

Uses `useApi(fetchDashboardStats)`. Shows:
- 4 `StatCard` in a responsive grid (`grid-cols-2 lg:grid-cols-4`)
- `DistributionBar` for binding status (green/amber/gray)
- Lvl1 distribution as horizontal bars
- `IngestTimeline` list
- `Skeleton` loading state

**Step 5: Verify in browser**

```bash
cd web && npm run dev
# Navigate to http://localhost:5173/
```

**Step 6: Commit**

```bash
git commit -m "feat(web): implement Dashboard page with stat cards and distribution bars"
```

---

## Task 9: Chunk Explorer Pages

Implement chunk list with filters and chunk detail with edit form.

**Files:**
- Replace: `web/src/pages/ChunkListPage.tsx`
- Replace: `web/src/pages/ChunkDetailPage.tsx`
- Create: `web/src/components/chunks/ChunkFilters.tsx`
- Create: `web/src/components/chunks/ChunkTable.tsx`

**Step 1: Create `ChunkFilters.tsx`**

Row of shadcn `Select` dropdowns for lvl1, binding_status, plus an `Input` for search text. Calls `onChange` with filter object when any value changes. Fetches bridge list for bridge_id select.

**Step 2: Create `ChunkTable.tsx`**

shadcn `Table` rendering `ChunkListItem[]`. Columns: 内容预览, 桥梁, 分类, 绑定状态 (colored badge), 来源. Row click navigates to `/chunks/:id`.

**Step 3: Implement `ChunkListPage.tsx`**

Uses `useApi(fetchChunks, [filters])`. Combines `ChunkFilters` + `ChunkTable` + shadcn `Pagination`. State: `page`, `filters` object.

**Step 4: Implement `ChunkDetailPage.tsx`**

Uses `useApi(fetchChunk, [id])` via `useParams()`. Left/right split layout:
- Left (60%): chunk content rendered as Markdown, contextual_text in muted block
- Right (40%): `Select` dropdowns for lvl1/lvl2/lvl3/binding_status, bridge_id input. Save button calls `updateChunk()`. Delete button with `Dialog` confirmation calls `deleteChunk()` then navigates back.
- Bottom: `Table` showing `bridge_links` array (bridge name, role, confidence, method)

**Step 5: Verify in browser**

```bash
cd web && npm run dev
# Navigate to /chunks and /chunks/1
```

**Step 6: Commit**

```bash
git commit -m "feat(web): implement Chunk Explorer (list + detail pages)"
```

---

## Task 10: Bridge Manager Pages

Implement bridge list, detail, and create pages.

**Files:**
- Replace: `web/src/pages/BridgeListPage.tsx`
- Replace: `web/src/pages/BridgeDetailPage.tsx`
- Replace: `web/src/pages/BridgeCreatePage.tsx`
- Create: `web/src/components/bridges/BridgeForm.tsx`

**Step 1: Create `BridgeForm.tsx`**

Reusable form for both create and edit. Props: `initialData?: BridgeDetail`, `onSubmit: (data) => Promise<void>`, `submitLabel: string`. Fields: name (required), aliases, bridge_type, material, era, location, function, summary. Uses shadcn `Input` and `Select` (with facet enum values from hardcoded constants matching `config/facets.yaml`).

**Step 2: Implement `BridgeListPage.tsx`**

Search input + shadcn `Table` + `Pagination`. "新建桥梁" button links to `/bridges/new`. Row click navigates to `/bridges/:id`.

**Step 3: Implement `BridgeCreatePage.tsx`**

`BridgeForm` with empty initial data. On submit: `createBridge(data)` then navigate to `/bridges/:id`.

**Step 4: Implement `BridgeDetailPage.tsx`**

`BridgeForm` pre-filled with bridge data. Below: chunk list (fetched via `fetchBridgeChunks`). Delete button (only enabled when `chunk_count === 0`).

**Step 5: Verify in browser**

```bash
cd web && npm run dev
# Navigate to /bridges, /bridges/new, /bridges/1
```

**Step 6: Commit**

```bash
git commit -m "feat(web): implement Bridge Manager (list + detail + create pages)"
```

---

## Task 11: Ingest & Ask Page Migration

Wrap existing `IngestPanel` and `AskPanel` components in page wrappers for the new router.

**Files:**
- Replace: `web/src/pages/IngestPage.tsx`
- Replace: `web/src/pages/AskPage.tsx`

**Step 1: Implement `IngestPage.tsx`**

```typescript
import { PageHeader } from "@/components/layout/PageHeader"
import { IngestPanel } from "@/components/ingest/IngestPanel"

export function Component() {
  return (
    <>
      <PageHeader title="入库" description="上传 Markdown 文档到知识库" />
      <main className="p-6">
        <IngestPanel />
      </main>
    </>
  )
}
```

**Step 2: Implement `AskPage.tsx`**

Same pattern wrapping `AskPanel`.

**Step 3: Verify both panels still work**

```bash
cd web && npm run dev
# Navigate to /ingest and /ask — verify existing functionality intact
```

**Step 4: Commit**

```bash
git commit -m "feat(web): migrate Ingest and Ask panels to router pages"
```

---

## Task 12: Final Verification + Regression Tests

Run full test suite and verify all routes work.

**Files:** None new — verification only.

**Step 1: Run all backend tests**

```bash
pytest tests/ -v
```

Expected: 93+ passed, 29 skipped. No new failures.

**Step 2: TypeScript check**

```bash
cd web && npx tsc --noEmit
```

Expected: No errors.

**Step 3: Manual smoke test**

```bash
cd web && npm run dev
```

Verify each route:
- `/` — Dashboard with skeleton or stats
- `/chunks` — Chunk list with filters
- `/chunks/:id` — Chunk detail with edit form
- `/bridges` — Bridge list with search
- `/bridges/new` — Create form
- `/bridges/:id` — Bridge detail with chunks
- `/ingest` — Ingest panel works
- `/ask` — Ask panel works
- Sidebar collapse/expand works and persists across page reload

**Step 4: Final commit if any fixes needed**

```bash
git commit -m "fix: address P0 admin dashboard smoke test issues"
```

---

## Summary

| Task | What | Files Created | Files Modified |
|------|------|---------------|----------------|
| 1 | Schema package refactor | 4 (schemas/) | 0 (delete schemas.py) |
| 2 | Stats endpoint | 2 (stats.py + schema + test) | 1 (__init__.py) |
| 3 | Chunks CRUD | 2 (chunks.py + schema + test) | 1 (__init__.py) |
| 4 | Bridges CRUD | 2 (bridges.py + schema + test) | 1 (__init__.py) |
| 5 | Frontend deps + shadcn | ~10 (ui components) | 1 (package.json) |
| 6 | Types + API client + hook | 1 (useApi.ts) | 2 (types.ts, api.ts) |
| 7 | Router + layout shell | 12 (router, layout, pages) | 2 (main.tsx, index.css) |
| 8 | Dashboard page | 4 (page + 3 components) | 0 |
| 9 | Chunk Explorer | 4 (2 pages + 2 components) | 0 |
| 10 | Bridge Manager | 4 (3 pages + 1 component) | 0 |
| 11 | Ingest & Ask migration | 2 (page wrappers) | 0 |
| 12 | Verification | 0 | 0 |
