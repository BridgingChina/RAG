# Batch 1 — Mobile API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the mobile API skeleton (`/api/mobile/v1/`), `knowledge_points` data model, bridge/knowledge endpoints, SSE pseudo-streaming QA, and HybridRetriever TaxonomyFilter — enabling mobile client development to begin.

**Architecture:** New `app/api/mobile/v1/` route tree with its own schemas, sharing the existing database and services. Two new tables (`knowledge_points`, `knowledge_point_key_points`) via schema v2 migration. `HybridRetriever` gains a `TaxonomyFilter` parameter orthogonal to `bridge_filter`. `Generator` gets a new `generate_streaming()` returning a list of SSE events from a single LLM call.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, PostgreSQL + pgvector, Pydantic v2

**Design doc:** `docs/plans/2026-03-26-batch1-mobile-api-design.md`

---

## Task 1: Knowledge Point Models

**Files:**
- Create: `app/models/knowledge_point.py`
- Create: `app/models/knowledge_point_key_point.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_models_knowledge_point.py`

**Step 1: Write the test**

```python
# tests/test_models_knowledge_point.py
"""Tests for KnowledgePoint and KnowledgePointKeyPoint models."""
import uuid

from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_key_point import KnowledgePointKeyPoint


def test_knowledge_point_model_structure():
    """Test KnowledgePoint has correct table name and fields."""
    assert KnowledgePoint.__tablename__ == "knowledge_points"
    columns = {c.name for c in KnowledgePoint.__table__.columns}
    assert columns == {
        "id", "taxonomy_node_id", "name", "aliases", "difficulty",
        "summary", "l2_content", "created_at", "updated_at",
    }


def test_knowledge_point_key_point_model_structure():
    """Test KnowledgePointKeyPoint has correct table name and fields."""
    assert KnowledgePointKeyPoint.__tablename__ == "knowledge_point_key_points"
    columns = {c.name for c in KnowledgePointKeyPoint.__table__.columns}
    assert columns == {
        "id", "knowledge_point_id", "summary", "explanation",
        "order_index", "chunk_ids", "illustration_urls",
        "related_term_ids", "created_at",
    }


def test_knowledge_point_importable_from_models():
    """Test models are registered in __init__.py."""
    from app.models import KnowledgePoint, KnowledgePointKeyPoint
    assert KnowledgePoint is not None
    assert KnowledgePointKeyPoint is not None
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_models_knowledge_point.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.knowledge_point'`

**Step 3: Write the models**

```python
# app/models/knowledge_point.py
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class KnowledgePoint(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "knowledge_points"

    taxonomy_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("taxonomy_nodes.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    l2_content: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_kp_taxonomy", "taxonomy_node_id"),
    )
```

```python
# app/models/knowledge_point_key_point.py
import uuid
from typing import Optional

from sqlalchemy import ARRAY, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDMixin


class KnowledgePointKeyPoint(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "knowledge_point_key_points"

    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_ids: Mapped[Optional[list[uuid.UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    illustration_urls: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    related_term_ids: Mapped[Optional[list[uuid.UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )

    __table_args__ = (
        Index("ix_kpkp_kp", "knowledge_point_id"),
    )
```

Update `app/models/__init__.py` — add imports and `__all__` entries:

```python
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_key_point import KnowledgePointKeyPoint
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_models_knowledge_point.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add app/models/knowledge_point.py app/models/knowledge_point_key_point.py app/models/__init__.py tests/test_models_knowledge_point.py
git commit -m "feat: add knowledge_points and knowledge_point_key_points models"
```

---

## Task 2: Schema Migration v1 → v2

**Files:**
- Modify: `app/core/database.py` — bump `LATEST_SCHEMA_VERSION` to 2, add new tables to `verify_schema_compatibility`
- Modify: `scripts/migrate_db.py` — add v1→v2 migration logic

**Step 1: Update `app/core/database.py`**

Change `LATEST_SCHEMA_VERSION = 1` to `LATEST_SCHEMA_VERSION = 2`.

In `verify_schema_compatibility()`, add to `required_schema`:

```python
"knowledge_points": {
    "id", "taxonomy_node_id", "name", "aliases", "difficulty",
    "summary", "l2_content", "created_at", "updated_at",
},
"knowledge_point_key_points": {
    "id", "knowledge_point_id", "summary", "explanation",
    "order_index", "chunk_ids", "illustration_urls",
    "related_term_ids", "created_at",
},
```

In `init_database()`, update the version description:

```python
set_schema_version(
    engine, LATEST_SCHEMA_VERSION,
    "Schema v2: knowledge_points + knowledge_point_key_points",
    conn=conn,
)
```

**Step 2: Update `scripts/migrate_db.py`**

Replace the placeholder with real migration logic:

```python
"""DB migration script.

Supports incremental migrations from v1 onward.
Use `python scripts/reset_db.py --force` to recreate from scratch.
"""
import sys

import click
from sqlalchemy import text

from app.core.database import (
    LATEST_SCHEMA_VERSION,
    engine,
    get_current_schema_version,
    set_schema_version,
)


def migrate_v1_to_v2(conn) -> None:
    """Add knowledge_points + knowledge_point_key_points tables."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS knowledge_points (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            taxonomy_node_id UUID REFERENCES taxonomy_nodes(id),
            name VARCHAR(200) NOT NULL,
            aliases TEXT,
            difficulty VARCHAR(20),
            summary TEXT,
            l2_content JSONB,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_kp_taxonomy ON knowledge_points(taxonomy_node_id)"
    ))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS knowledge_point_key_points (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            knowledge_point_id UUID NOT NULL REFERENCES knowledge_points(id) ON DELETE CASCADE,
            summary TEXT NOT NULL,
            explanation TEXT,
            order_index INTEGER NOT NULL,
            chunk_ids UUID[],
            illustration_urls TEXT[],
            related_term_ids UUID[],
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_kpkp_kp ON knowledge_point_key_points(knowledge_point_id)"
    ))
    set_schema_version(engine, 2, "Add knowledge_points + knowledge_point_key_points", conn=conn)


MIGRATIONS = {
    1: migrate_v1_to_v2,
}


@click.command()
def main() -> None:
    current = get_current_schema_version(engine)
    if current is None:
        click.echo("No schema_version table found — init_database() will create it on startup.")
        return
    if current == LATEST_SCHEMA_VERSION:
        click.echo(f"Schema v{current} matches code. No migrations needed.")
        return
    if current > LATEST_SCHEMA_VERSION:
        click.echo(
            f"ERROR: DB schema v{current} is ahead of code v{LATEST_SCHEMA_VERSION}.",
            err=True,
        )
        sys.exit(1)

    click.echo(f"Migrating from v{current} to v{LATEST_SCHEMA_VERSION}...")
    with engine.begin() as conn:
        for v in range(current, LATEST_SCHEMA_VERSION):
            migrate_fn = MIGRATIONS.get(v)
            if migrate_fn is None:
                click.echo(f"ERROR: No migration function for v{v} → v{v+1}.", err=True)
                sys.exit(1)
            click.echo(f"  Running v{v} → v{v+1}...")
            migrate_fn(conn)
    click.echo(f"Migration complete. Now at v{LATEST_SCHEMA_VERSION}.")


if __name__ == "__main__":
    main()
```

**Step 3: Commit**

```bash
git add app/core/database.py scripts/migrate_db.py
git commit -m "feat: schema v2 migration — knowledge_points tables"
```

---

## Task 3: Mobile API Route Skeleton

**Files:**
- Create: `app/api/mobile/__init__.py`
- Create: `app/api/mobile/v1/__init__.py`
- Create: `app/api/mobile/v1/dependencies.py`
- Create: `app/api/mobile/v1/schemas/__init__.py`
- Create: `app/api/mobile/v1/schemas/common.py`
- Modify: `app/main.py`
- Test: `tests/test_api_mobile_skeleton.py`

**Step 1: Write the test**

```python
# tests/test_api_mobile_skeleton.py
"""Tests for mobile API route skeleton."""
from app.main import app


def test_mobile_router_registered():
    """Test that mobile routes are registered under /api/mobile/v1."""
    route_paths = [route.path for route in app.routes]
    # Config endpoint should exist
    assert "/api/mobile/v1/config" in route_paths
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_mobile_skeleton.py -v`
Expected: FAIL — `/api/mobile/v1/config` not in route_paths

**Step 3: Create the skeleton files**

```python
# app/api/mobile/__init__.py
"""Mobile API routes."""
from fastapi import APIRouter

from app.api.mobile.v1 import router as v1_router

router = APIRouter()
router.include_router(v1_router)

__all__ = ["router"]
```

```python
# app/api/mobile/v1/__init__.py
"""Mobile API v1 routes."""
from fastapi import APIRouter

from app.api.mobile.v1 import config

router = APIRouter()
router.include_router(config.router)

__all__ = ["router"]
```

```python
# app/api/mobile/v1/dependencies.py
"""Mobile API dependencies."""
import uuid

from fastapi import Header, HTTPException


def require_device_id(x_device_id: str = Header(...)) -> str:
    """Validate X-Device-Id header format (UUID v4) and return it."""
    try:
        uuid.UUID(x_device_id, version=4)
    except ValueError:
        raise HTTPException(400, detail="Invalid X-Device-Id format")
    return x_device_id
```

```python
# app/api/mobile/v1/schemas/__init__.py
"""Mobile API v1 schemas."""
```

```python
# app/api/mobile/v1/schemas/common.py
"""Common mobile API schemas."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class MobileResponse(BaseModel, Generic[T]):
    """Wrapper for single-object responses."""
    data: T


class MobileMeta(BaseModel):
    """Pagination metadata for mobile API."""
    total: int
    page: int
    page_size: int
    has_more: bool


class MobilePaginatedResponse(BaseModel, Generic[T]):
    """Wrapper for paginated responses."""
    data: T
    meta: MobileMeta
```

```python
# app/api/mobile/v1/config.py
"""Mobile API: GET /config."""
from fastapi import APIRouter

from app.api.mobile.v1.schemas.common import MobileResponse

router = APIRouter()


@router.get("/config")
def get_config() -> MobileResponse[dict]:
    """Return app configuration for mobile client.

    Data sourced from config/facets.yaml + hardcoded map config.
    """
    from app.core.constants import load_facets

    facets = load_facets()
    return MobileResponse(data={
        "eras": facets.get("era", []),
        "bridge_types": facets.get("bridge_type", []),
        "regions": facets.get("region", []),
        "map": {
            "provider": None,       # TODO: configure map provider
            "approval_number": None,  # TODO: configure approval number
        },
    })
```

Modify `app/main.py` — add after the v1 router registration:

```python
# Mobile API routes (no auth required)
from app.api.mobile import router as mobile_router
app.include_router(mobile_router, prefix="/api/mobile/v1", tags=["mobile"])
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_mobile_skeleton.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/mobile/ app/main.py tests/test_api_mobile_skeleton.py
git commit -m "feat: mobile API route skeleton with /config endpoint"
```

---

## Task 4: Mobile Bridge Endpoints

**Files:**
- Create: `app/api/mobile/v1/bridges.py`
- Create: `app/api/mobile/v1/schemas/bridge.py`
- Modify: `app/api/mobile/v1/__init__.py` — register bridges router
- Test: `tests/test_api_mobile_bridges.py`

**Step 1: Write the test**

```python
# tests/test_api_mobile_bridges.py
"""Tests for mobile bridges API endpoints."""
from app.main import app


def test_mobile_bridges_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges" in route_paths


def test_mobile_bridges_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges/{bridge_id}" in route_paths


def test_mobile_bridges_knowledge_points_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges/{bridge_id}/knowledge-points" in route_paths
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_mobile_bridges.py -v`
Expected: FAIL

**Step 3: Create bridge schemas and endpoint**

```python
# app/api/mobile/v1/schemas/bridge.py
"""Mobile bridge schemas."""
from uuid import UUID

from pydantic import BaseModel


class MobileBridgeListItem(BaseModel):
    id: UUID
    name: str
    aliases: str | None
    bridge_type: str | None
    era: str | None
    region: str | None
    latitude: float | None
    longitude: float | None
    thumbnail: str | None = None
    distance: float | None = None


class BridgeSectionLevel(BaseModel):
    l0: list[dict] = []
    l1: list[dict] = []


class BridgeSections(BaseModel):
    structure: BridgeSectionLevel = BridgeSectionLevel()
    geography: BridgeSectionLevel = BridgeSectionLevel()
    society: BridgeSectionLevel = BridgeSectionLevel()
    history: BridgeSectionLevel = BridgeSectionLevel()


class MobileBridgeDetail(BaseModel):
    id: UUID
    name: str
    aliases: str | None
    bridge_type: str | None
    era: str | None
    region: str | None
    latitude: float | None
    longitude: float | None
    tags: list[str] = []
    images: list[dict] = []
    sections: BridgeSections = BridgeSections()
    related_knowledge_points: list[dict] = []
    sources: list[dict] = []
    sources_count: int = 0
```

```python
# app/api/mobile/v1/bridges.py
"""Mobile API: Bridge endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.mobile.v1.schemas.bridge import (
    MobileBridgeDetail,
    MobileBridgeListItem,
)
from app.api.mobile.v1.schemas.common import (
    MobileMeta,
    MobilePaginatedResponse,
    MobileResponse,
)
from app.core.database import get_db
from app.models import Bridge, Chunk

router = APIRouter()


@router.get("")
def list_bridges(
    bridge_type: str | None = None,
    era: str | None = None,
    region: str | None = None,
    keyword: str | None = None,
    near_lat: float | None = None,
    near_lng: float | None = None,
    near_radius: int = Query(default=50000, ge=1),
    sort: str = "name",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MobilePaginatedResponse[dict]:
    """List bridges with filtering for mobile client."""
    query = db.query(Bridge)

    # Multi-select filters (comma-separated)
    if bridge_type:
        types = [t.strip() for t in bridge_type.split(",") if t.strip()]
        if types:
            query = query.filter(Bridge.bridge_type.in_(types))
    if era:
        eras = [e.strip() for e in era.split(",") if e.strip()]
        if eras:
            query = query.filter(Bridge.era.in_(eras))

    # Region ILIKE
    if region:
        query = query.filter(Bridge.region.ilike(f"%{region}%"))

    # Keyword search (name + aliases)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            or_(Bridge.name.ilike(pattern), Bridge.aliases.ilike(pattern))
        )

    # Nearby filter (simple bounding box)
    if near_lat is not None and near_lng is not None:
        # Approximate: 1 degree latitude ≈ 111km
        delta_lat = near_radius / 111_000
        delta_lng = near_radius / 111_000  # rough approximation
        query = query.filter(
            Bridge.latitude.isnot(None),
            Bridge.latitude.between(near_lat - delta_lat, near_lat + delta_lat),
            Bridge.longitude.between(near_lng - delta_lng, near_lng + delta_lng),
        )

    total = query.count()
    # TODO: sort=distance (requires PostGIS or Haversine)
    query = query.order_by(Bridge.name)
    bridges = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        MobileBridgeListItem(
            id=b.id,
            name=b.name,
            aliases=b.aliases,
            bridge_type=b.bridge_type,
            era=b.era,
            region=b.region,
            latitude=b.latitude,
            longitude=b.longitude,
        ).model_dump()
        for b in bridges
    ]

    return MobilePaginatedResponse(
        data={"bridges": items},
        meta=MobileMeta(
            total=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size < total),
        ),
    )


@router.get("/{bridge_id}")
def get_bridge(bridge_id: UUID, db: Session = Depends(get_db)) -> MobileResponse[dict]:
    """Get bridge detail for mobile client.

    Returns basic fields + empty skeleton for sections/images/related_knowledge_points.
    TODO: sections aggregation (Batch 2 #17), images, related_knowledge_points.
    """
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(404, detail="桥梁不存在")

    # sources_count from chunks
    sources_count = (
        db.query(func.count(func.distinct(Chunk.source_id)))
        .filter(Chunk.bridge_id == bridge_id)
        .scalar()
    ) or 0

    detail = MobileBridgeDetail(
        id=bridge.id,
        name=bridge.name,
        aliases=bridge.aliases,
        bridge_type=bridge.bridge_type,
        era=bridge.era,
        region=bridge.region,
        latitude=bridge.latitude,
        longitude=bridge.longitude,
        sources_count=sources_count,
        # TODO (Batch 2): sections, images, related_knowledge_points
    )
    return MobileResponse(data=detail.model_dump())


@router.get("/{bridge_id}/knowledge-points")
def get_bridge_knowledge_points(
    bridge_id: UUID, db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """Get knowledge points related to a bridge.

    TODO (P2): Implement via knowledge_point_bridges association table.
    """
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(404, detail="桥梁不存在")
    return MobileResponse(data={"knowledge_points": []})
```

Update `app/api/mobile/v1/__init__.py` to register the bridges router:

```python
from app.api.mobile.v1 import config, bridges

router = APIRouter()
router.include_router(config.router)
router.include_router(bridges.router, prefix="/bridges")
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_mobile_bridges.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add app/api/mobile/v1/bridges.py app/api/mobile/v1/schemas/bridge.py app/api/mobile/v1/__init__.py tests/test_api_mobile_bridges.py
git commit -m "feat: mobile bridge list/detail/knowledge-points endpoints"
```

---

## Task 5: Mobile Knowledge Endpoints

**Files:**
- Create: `app/api/mobile/v1/knowledge.py`
- Create: `app/api/mobile/v1/schemas/knowledge.py`
- Modify: `app/api/mobile/v1/__init__.py` — register knowledge router
- Test: `tests/test_api_mobile_knowledge.py`

**Step 1: Write the test**

```python
# tests/test_api_mobile_knowledge.py
"""Tests for mobile knowledge API endpoints."""
from app.main import app


def test_mobile_knowledge_tree_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/knowledge/tree" in route_paths


def test_mobile_knowledge_point_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/knowledge/points/{point_id}" in route_paths


def test_mobile_knowledge_point_bridges_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/knowledge/points/{point_id}/bridges" in route_paths
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_mobile_knowledge.py -v`
Expected: FAIL

**Step 3: Create knowledge schemas and endpoint**

```python
# app/api/mobile/v1/schemas/knowledge.py
"""Mobile knowledge schemas."""
from uuid import UUID

from pydantic import BaseModel


class KnowledgeTreeKP(BaseModel):
    """Knowledge point leaf node in the tree."""
    id: UUID
    name: str
    type: str = "knowledge_point"
    tags: list[str] = []
    summary: str | None = None


class KnowledgeTreeNode(BaseModel):
    """Taxonomy node in the tree (recursive)."""
    id: UUID
    name: str
    icon_url: str | None = None
    children: list["KnowledgeTreeNode | KnowledgeTreeKP"] = []


class KeyPointL0(BaseModel):
    id: UUID
    summary: str
    order: int


class KeyPointL1(BaseModel):
    id: UUID
    summary: str
    explanation: str | None
    illustrations: list[dict] = []
    related_terms: list[dict] = []
    citations: list[int] = []


class SourceRef(BaseModel):
    id: int
    title: str
    author: str | None = None
    type: str | None = None
    excerpt: str | None = None
    location: str | None = None
```

```python
# app/api/mobile/v1/knowledge.py
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
    depth: int | None = None,
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
    # Group nodes by level
    lvl1_nodes: dict[str, dict] = {}  # lvl1 name -> tree node
    lvl2_nodes: dict[tuple[str, str], dict] = {}  # (lvl1, lvl2) -> tree node

    for node in nodes:
        # lvl1 only (no lvl2)
        if node.lvl2 is None:
            if node.lvl1 not in lvl1_nodes:
                lvl1_nodes[node.lvl1] = {
                    "id": str(node.id),
                    "name": node.lvl1,
                    "icon_url": None,
                    "children": [],
                }
            continue

        # Ensure lvl1 parent exists
        if node.lvl1 not in lvl1_nodes:
            lvl1_nodes[node.lvl1] = {
                "id": str(node.id),
                "name": node.lvl1,
                "icon_url": None,
                "children": [],
            }

        # lvl2 only (no lvl3)
        if node.lvl3 is None:
            key2 = (node.lvl1, node.lvl2)
            if key2 not in lvl2_nodes:
                lvl2_node = {
                    "id": str(node.id),
                    "name": node.lvl2,
                    "children": [],
                }
                lvl2_nodes[key2] = lvl2_node
                lvl1_nodes[node.lvl1]["children"].append(lvl2_node)
            continue

        # lvl3 node
        key2 = (node.lvl1, node.lvl2)
        if key2 not in lvl2_nodes:
            lvl2_node = {
                "id": str(node.id),
                "name": node.lvl2,
                "children": [],
            }
            lvl2_nodes[key2] = lvl2_node
            lvl1_nodes[node.lvl1]["children"].append(lvl2_node)

        lvl3_entry = {
            "id": str(node.id),
            "name": node.lvl3,
            "children": kp_by_taxonomy.get(node.id, []),
        }
        lvl2_nodes[key2]["children"].append(lvl3_entry)

    lines = list(lvl1_nodes.values())

    # Apply depth truncation
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

    # Get taxonomy context (line = lvl1, category = lvl2)
    line_info = None
    category_info = None
    if kp.taxonomy_node_id:
        tax_node = db.query(TaxonomyNode).filter(
            TaxonomyNode.id == kp.taxonomy_node_id
        ).first()
        if tax_node:
            # Find line (lvl1-only node)
            lvl1_node = db.query(TaxonomyNode).filter(
                TaxonomyNode.lvl1 == tax_node.lvl1,
                TaxonomyNode.lvl2.is_(None),
            ).first()
            if lvl1_node:
                line_info = {"id": str(lvl1_node.id), "name": lvl1_node.lvl1}
            # Find category (lvl2 node)
            if tax_node.lvl2:
                lvl2_node = db.query(TaxonomyNode).filter(
                    TaxonomyNode.lvl1 == tax_node.lvl1,
                    TaxonomyNode.lvl2 == tax_node.lvl2,
                    TaxonomyNode.lvl3.is_(None),
                ).first()
                if lvl2_node:
                    category_info = {"id": str(lvl2_node.id), "name": lvl2_node.lvl2}

    # Get key points
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

    # L0: key point summaries
    if level in ("L0", "L1", "all"):
        result["l0"] = {
            "key_points": [
                {"id": str(kp_item.id), "summary": kp_item.summary, "order": kp_item.order_index}
                for kp_item in key_points
            ],
            "typical_bridges_count": 0,  # TODO: count from knowledge_point_bridges
        }

    # L1: key points with explanation + citations
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
                    "related_terms": [],  # TODO: resolve related_term_ids
                    "citations": list(range(1, len(kp_item.chunk_ids or []) + 1)),
                }
                for kp_item in key_points
            ],
        }

    # L2: deep dive content
    if level in ("L2", "all"):
        result["l2"] = kp.l2_content or {}

    # Sources: aggregate from chunk_ids across all key_points
    all_chunk_ids: list = []
    for kp_item in key_points:
        if kp_item.chunk_ids:
            all_chunk_ids.extend(kp_item.chunk_ids)

    sources: list[dict] = []
    if all_chunk_ids:
        from app.models import Chunk, Source
        rows = (
            db.query(Source.id, Source.title, Source.type)
            .join(Chunk, Chunk.source_id == Source.id)
            .filter(Chunk.id.in_(all_chunk_ids))
            .distinct()
            .all()
        )
        for idx, row in enumerate(rows, 1):
            sources.append({
                "id": idx,
                "title": row.title,
                "author": None,
                "type": row.type,
                "excerpt": None,
                "location": None,
            })

    result["sources"] = sources

    return MobileResponse(data=result)


@router.get("/points/{point_id}/bridges")
def get_knowledge_point_bridges(
    point_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """Get bridges related to a knowledge point.

    TODO (P2): Implement via knowledge_point_bridges association table.
    """
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
    if not kp:
        raise HTTPException(404, detail="知识点不存在")
    return MobileResponse(data={"bridges": []})
```

Update `app/api/mobile/v1/__init__.py`:

```python
from app.api.mobile.v1 import config, bridges, knowledge

router = APIRouter()
router.include_router(config.router)
router.include_router(bridges.router, prefix="/bridges")
router.include_router(knowledge.router, prefix="/knowledge")
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_api_mobile_knowledge.py tests/test_api_mobile_bridges.py tests/test_api_mobile_skeleton.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/api/mobile/v1/knowledge.py app/api/mobile/v1/schemas/knowledge.py app/api/mobile/v1/__init__.py tests/test_api_mobile_knowledge.py
git commit -m "feat: mobile knowledge tree and knowledge point detail endpoints"
```

---

## Task 6: HybridRetriever TaxonomyFilter

**Files:**
- Modify: `app/services/hybrid_retriever.py`
- Test: `tests/test_hybrid_retriever.py` (add new tests)

**Step 1: Write the test**

Append to `tests/test_hybrid_retriever.py`:

```python
from app.services.hybrid_retriever import TaxonomyFilter


def test_taxonomy_filter_dataclass():
    """Test TaxonomyFilter structure."""
    tf = TaxonomyFilter(lvl1="形制与技术", lvl2="结构体系")
    assert tf.lvl1 == "形制与技术"
    assert tf.lvl2 == "结构体系"
    assert tf.lvl3 is None


def test_taxonomy_filter_all_none():
    """Test TaxonomyFilter with all None fields."""
    tf = TaxonomyFilter()
    assert tf.lvl1 is None
    assert tf.lvl2 is None
    assert tf.lvl3 is None
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_hybrid_retriever.py::test_taxonomy_filter_dataclass -v`
Expected: FAIL — `ImportError: cannot import name 'TaxonomyFilter'`

**Step 3: Implement TaxonomyFilter**

In `app/services/hybrid_retriever.py`:

1. Add `TaxonomyFilter` dataclass after the existing dataclass definitions (near line 37):

```python
@dataclass
class TaxonomyFilter:
    """Filter chunks by taxonomy labels."""
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None
```

2. Add `taxonomy_filter` parameter to `retrieve()` signature (after `target_bridge_id`):

```python
async def retrieve(
    self,
    db: Session,
    query: str,
    target_bridge_id: Optional[uuid.UUID] = None,
    taxonomy_filter: Optional[TaxonomyFilter] = None,
    quota: tuple[int, int, int] = DEFAULT_QUOTA,
    facet: Optional[Facet] = None,
    debug: bool = False,
) -> HybridRetrievalResult:
```

3. In `retrieve()`, when `taxonomy_filter` is set and `target_bridge_id` is None, use taxonomy_filter for anchor channel instead. Replace the anchor channel block:

```python
# Anchor channel: by bridge_id OR by taxonomy_filter
anchor_chunks: list[RetrievedChunk] = []
if anchor_quota > 0 and (target_bridge_id is not None or taxonomy_filter is not None):
    if debug:
        t0 = time.perf_counter()
    anchor_chunks, anchor_dbg = await self._retrieve_channel(
        db,
        query,
        query_embedding,
        bridge_filter=target_bridge_id,
        taxonomy_filter=taxonomy_filter if target_bridge_id is None else None,
        limit=anchor_quota,
        debug=debug,
        channel_name="anchor",
    )
    if debug:
        timings["anchor"] = time.perf_counter() - t0
        if anchor_dbg:
            channel_debugs.append(anchor_dbg)
```

4. Add `taxonomy_filter` to `_retrieve_channel()`, `_vector_search()`, and `_fts_search()`:

In `_retrieve_channel()` add parameter `taxonomy_filter: Optional[TaxonomyFilter] = None` and pass it through:

```python
vec_results = self._vector_search(
    db, query_embedding, bridge_filter, require_no_bridge_id, fetch_limit,
    taxonomy_filter=taxonomy_filter,
)
fts_results = self._fts_search(
    db, query, bridge_filter, require_no_bridge_id, fetch_limit,
    taxonomy_filter=taxonomy_filter,
)
```

In `_vector_search()` and `_fts_search()`, add parameter and SQL conditions:

```python
def _vector_search(
    self, db, query_embedding, bridge_filter, require_no_bridge_id, limit,
    taxonomy_filter: Optional[TaxonomyFilter] = None,
) -> list[uuid.UUID]:
    # ... existing code ...
    # After existing bridge_filter conditions, before ORDER BY:
    if taxonomy_filter:
        if taxonomy_filter.lvl1:
            sql += " AND lvl1 = :tax_lvl1"
            params["tax_lvl1"] = taxonomy_filter.lvl1
        if taxonomy_filter.lvl2:
            sql += " AND lvl2 = :tax_lvl2"
            params["tax_lvl2"] = taxonomy_filter.lvl2
        if taxonomy_filter.lvl3:
            sql += " AND lvl3 = :tax_lvl3"
            params["tax_lvl3"] = taxonomy_filter.lvl3
    # ... ORDER BY ...
```

Same pattern for `_fts_search()`.

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_hybrid_retriever.py -v`
Expected: ALL PASS (existing + 2 new)

**Step 5: Commit**

```bash
git add app/services/hybrid_retriever.py tests/test_hybrid_retriever.py
git commit -m "feat: add TaxonomyFilter to HybridRetriever"
```

---

## Task 7: Generator.generate_streaming()

**Files:**
- Modify: `app/services/generator.py`
- Test: `tests/test_generator.py` (add new tests)

**Step 1: Write the test**

Append to `tests/test_generator.py`:

```python
@pytest.mark.asyncio
async def test_generate_streaming_returns_event_list():
    """Test generate_streaming returns structured SSE events."""

    class MockProvider:
        async def chat(self, messages):
            return ChatResponse(
                content='{"key_points": [{"summary": "要点一", "explanation": "解释一", "citations": [1]}, {"summary": "要点二", "explanation": "解释二", "citations": [2]}], "deep_dive": null, "confidence": {"level": "high", "reason": "充分"}}',
                usage={"total_tokens": 200},
            )

    generator = Generator(provider=MockProvider())
    evidence = HybridRetrievalResult(
        anchor_chunks=[
            RetrievedChunk(chunk_id=_UUID1, content="内容一", bridge_id=_UUID1, bridge_name="赵州桥", score=0.9),
            RetrievedChunk(chunk_id=_UUID2, content="内容二", bridge_id=_UUID1, bridge_name="赵州桥", score=0.8),
        ],
        concept_chunks=[],
        analogy_chunks=[],
    )
    events = await generator.generate_streaming("测试问题", evidence)

    assert isinstance(events, list)
    # outline + 2 details + sources = 4 events
    event_types = [e[0] for e in events]
    assert event_types[0] == "outline"
    assert event_types[1] == "detail"
    assert event_types[2] == "detail"
    assert event_types[3] == "sources"

    # Check outline structure
    outline_data = events[0][1]
    assert len(outline_data["key_points"]) == 2
    assert outline_data["key_points"][0]["summary"] == "要点一"

    # Check detail structure
    detail_data = events[1][1]
    assert detail_data["explanation"] == "解释一"


@pytest.mark.asyncio
async def test_generate_streaming_fallback_on_bad_json():
    """Test generate_streaming handles malformed LLM output."""

    class MockProvider:
        async def chat(self, messages):
            return ChatResponse(content="这不是JSON", usage={"total_tokens": 50})

    generator = Generator(provider=MockProvider())
    evidence = HybridRetrievalResult(
        anchor_chunks=[], concept_chunks=[], analogy_chunks=[],
    )
    events = await generator.generate_streaming("测试问题", evidence)

    assert isinstance(events, list)
    assert len(events) >= 1
    # Should have an error-like event or a single outline with empty key_points
    event_types = [e[0] for e in events]
    assert "outline" in event_types or "error" in event_types
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_generator.py::test_generate_streaming_returns_event_list -v`
Expected: FAIL — `AttributeError: 'Generator' object has no attribute 'generate_streaming'`

**Step 3: Implement `generate_streaming()`**

Add to `app/services/generator.py`, after the existing `_parse_response()` method:

```python
async def generate_streaming(
    self,
    question: str,
    evidence: HybridRetrievalResult,
) -> list[tuple[str, dict]]:
    """Single LLM call + pseudo-streaming split into SSE events.

    Returns list of (event_type, data) tuples:
    - ("outline", {"key_points": [...]})
    - ("detail", {"key_point_id": ..., "explanation": ..., "citations": [...]})
    - ("deep_dive", {...})  -- if present
    - ("sources", {"sources": [...]})

    TODO: Upgrade to real LLM streaming with async generator.
    """
    from app.services.hybrid_retriever import format_evidence_for_llm

    evidence_text = format_evidence_for_llm(evidence)

    prompt = f"""你是桥梁知识助手。根据以下证据回答问题。

{evidence_text}

问题：{question}

请按以下JSON格式回答（不要输出任何其他内容）：
{{
    "key_points": [
        {{"summary": "要点摘要", "explanation": "详细解释", "citations": [1, 2]}}
    ],
    "deep_dive": null,
    "confidence": {{
        "level": "high|medium|low",
        "reason": "置信度理由"
    }}
}}

要求：
- key_points 包含 3~7 个要点，每个有 summary（一句话）和 explanation（展开说明）
- citations 引用证据编号（从1开始）
- deep_dive 如有比较或争议可填写，否则 null
- 置信度按证据充分程度判断"""

    messages = [ChatMessage(role="user", content=prompt)]
    response = await self.provider.chat(messages)

    return self._parse_streaming_response(response.content, evidence)

def _parse_streaming_response(
    self,
    content: str,
    evidence: HybridRetrievalResult,
) -> list[tuple[str, dict]]:
    """Parse LLM JSON response into a list of SSE events."""
    events: list[tuple[str, dict]] = []

    try:
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            raise json.JSONDecodeError("No JSON found", content, 0)

        data = json.loads(content[json_start:json_end])
        key_points = data.get("key_points", [])

        # Generate IDs for key points
        kp_entries = []
        for i, kp in enumerate(key_points, 1):
            kp_id = str(uuid.uuid4())
            kp_entries.append({
                "id": kp_id,
                "summary": kp.get("summary", ""),
                "order": i,
                "_explanation": kp.get("explanation", ""),
                "_citations": kp.get("citations", []),
            })

        # Outline event
        events.append(("outline", {
            "key_points": [
                {"id": kp["id"], "summary": kp["summary"], "order": kp["order"]}
                for kp in kp_entries
            ],
        }))

        # Detail events
        for kp in kp_entries:
            events.append(("detail", {
                "key_point_id": kp["id"],
                "explanation": kp["_explanation"],
                "citations": kp["_citations"],
            }))

        # Deep dive event (if present)
        deep_dive = data.get("deep_dive")
        if deep_dive:
            events.append(("deep_dive", deep_dive))

    except (json.JSONDecodeError, KeyError, TypeError):
        # Fallback: single outline with the raw text as one key point
        fallback_id = str(uuid.uuid4())
        events.append(("outline", {
            "key_points": [{"id": fallback_id, "summary": content[:200], "order": 1}],
        }))
        events.append(("detail", {
            "key_point_id": fallback_id,
            "explanation": content,
            "citations": [],
        }))

    # Sources event — build from evidence chunks
    all_chunks = evidence.all_chunks()
    sources = []
    seen_sources: set[str] = set()
    for i, chunk in enumerate(all_chunks, 1):
        source_title = chunk.bridge_name or f"来源{i}"
        if source_title not in seen_sources:
            sources.append({
                "id": i,
                "title": source_title,
                "author": None,
                "type": None,
                "excerpt": chunk.content[:100] if chunk.content else None,
                "location": None,
            })
            seen_sources.add(source_title)
    events.append(("sources", {"sources": sources}))

    return events
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_generator.py -v`
Expected: ALL PASS (existing + 2 new)

**Step 5: Commit**

```bash
git add app/services/generator.py tests/test_generator.py
git commit -m "feat: add Generator.generate_streaming() for SSE pseudo-streaming"
```

---

## Task 8: SSE QA Endpoint

**Files:**
- Create: `app/api/mobile/v1/qa.py`
- Create: `app/api/mobile/v1/schemas/qa.py`
- Modify: `app/api/mobile/v1/__init__.py`
- Test: `tests/test_api_mobile_qa.py`

**Step 1: Write the test**

```python
# tests/test_api_mobile_qa.py
"""Tests for mobile QA SSE endpoint."""
from app.main import app


def test_mobile_qa_ask_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/qa/ask" in route_paths


def test_mobile_qa_ask_accepts_post():
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/mobile/v1/qa/ask",
        json={"question": "测试问题"},
    )
    # Should not be 404 or 405 (may be 500 without DB, that's OK for route test)
    assert response.status_code not in (404, 405)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_mobile_qa.py -v`
Expected: FAIL

**Step 3: Create QA schemas and endpoint**

```python
# app/api/mobile/v1/schemas/qa.py
"""Mobile QA schemas."""
from uuid import UUID

from pydantic import BaseModel


class QAContext(BaseModel):
    type: str | None = None       # "bridge" / "knowledge_point" / "search" / "map" / None
    id: UUID | None = None
    filters: dict | None = None


class QARequest(BaseModel):
    question: str
    context: QAContext | None = None
```

```python
# app/api/mobile/v1/qa.py
"""Mobile API: SSE streaming QA endpoint."""
import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.mobile.v1.schemas.qa import QARequest
from app.core.database import get_db
from app.models import TaxonomyNode
from app.models.knowledge_point import KnowledgePoint
from app.providers import ZhipuProvider
from app.services.facet_extractor import FacetExtractor
from app.services.generator import Generator
from app.services.hybrid_retriever import (
    HybridRetriever,
    HybridRetrievalResult,
    TaxonomyFilter,
)
from app.services.tokenizer import Tokenizer, default_user_dict_path

router = APIRouter()


def _sse_event(event: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resolve_context(
    db: Session, request: QARequest,
) -> tuple[uuid.UUID | None, TaxonomyFilter | None]:
    """Resolve QA context to bridge_id or taxonomy_filter."""
    if not request.context or not request.context.type or not request.context.id:
        return None, None

    if request.context.type == "bridge":
        return request.context.id, None

    if request.context.type == "knowledge_point":
        kp = db.query(KnowledgePoint).filter(
            KnowledgePoint.id == request.context.id
        ).first()
        if kp and kp.taxonomy_node_id:
            tax_node = db.query(TaxonomyNode).filter(
                TaxonomyNode.id == kp.taxonomy_node_id
            ).first()
            if tax_node:
                return None, TaxonomyFilter(
                    lvl1=tax_node.lvl1,
                    lvl2=tax_node.lvl2,
                    lvl3=tax_node.lvl3,
                )
    return None, None


@router.post("/ask")
async def ask_sse(
    request: QARequest,
    db: Session = Depends(get_db),
):
    """SSE streaming QA endpoint.

    Single LLM call + pseudo-streaming: retrieves evidence, generates structured
    response, then splits into SSE events.
    TODO: Upgrade to real LLM streaming.
    TODO: SSE heartbeat (15s ping) + total timeout (60s).
    """
    async def event_stream():
        qa_id = str(uuid.uuid4())
        yield _sse_event("started", {"qa_id": qa_id})

        try:
            provider = ZhipuProvider()
            tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
            retriever = HybridRetriever(provider=provider, tokenizer=tokenizer)
            generator = Generator(provider=provider)
            facet_extractor = FacetExtractor(provider=provider)

            # Resolve context
            target_bridge_id, taxonomy_filter = _resolve_context(db, request)

            # Auto-resolve bridge from question text if no context
            if not target_bridge_id and not taxonomy_filter:
                from app.api.v1.ask import _resolve_bridge_from_question
                target_bridge_id = _resolve_bridge_from_question(db, request.question)

            # Extract facets
            facet = None
            try:
                facet = await facet_extractor.extract(request.question)
            except Exception:
                pass

            # Retrieve evidence
            try:
                evidence = await retriever.retrieve(
                    db,
                    request.question,
                    target_bridge_id=target_bridge_id,
                    taxonomy_filter=taxonomy_filter,
                    facet=facet,
                )
            except Exception:
                evidence = HybridRetrievalResult(
                    anchor_chunks=[], concept_chunks=[], analogy_chunks=[],
                )

            # Check for empty evidence
            if not evidence.all_chunks():
                yield _sse_event("error", {
                    "code": "INSUFFICIENT_EVIDENCE",
                    "message": "未找到直接证据，建议换一种问法或缩小范围",
                    "fallback_actions": [],
                })
                yield _sse_event("done", {"qa_id": qa_id})
                return

            # Generate streaming events
            events = await generator.generate_streaming(request.question, evidence)
            for event_type, data in events:
                yield _sse_event(event_type, data)

            yield _sse_event("done", {"qa_id": qa_id})

        except Exception as e:
            yield _sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": f"服务端内部错误: {str(e)}",
            })
            yield _sse_event("done", {"qa_id": qa_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

Update `app/api/mobile/v1/__init__.py`:

```python
from app.api.mobile.v1 import config, bridges, knowledge, qa

router = APIRouter()
router.include_router(config.router)
router.include_router(bridges.router, prefix="/bridges")
router.include_router(knowledge.router, prefix="/knowledge")
router.include_router(qa.router, prefix="/qa")
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_api_mobile_qa.py tests/test_api_mobile_skeleton.py tests/test_api_mobile_bridges.py tests/test_api_mobile_knowledge.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/api/mobile/v1/qa.py app/api/mobile/v1/schemas/qa.py app/api/mobile/v1/__init__.py tests/test_api_mobile_qa.py
git commit -m "feat: SSE pseudo-streaming QA endpoint for mobile"
```

---

## Task 9: Search Endpoint Placeholder

**Files:**
- Create: `app/api/mobile/v1/search.py`
- Create: `app/api/mobile/v1/schemas/search.py`
- Modify: `app/api/mobile/v1/__init__.py`
- Test: `tests/test_api_mobile_search.py`

**Step 1: Write the test**

```python
# tests/test_api_mobile_search.py
"""Tests for mobile search endpoint (placeholder)."""
from app.main import app


def test_mobile_search_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/search" in route_paths
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_mobile_search.py -v`
Expected: FAIL

**Step 3: Create placeholder**

```python
# app/api/mobile/v1/schemas/search.py
"""Mobile search schemas (placeholder)."""
```

```python
# app/api/mobile/v1/search.py
"""Mobile API: Unified search endpoint.

TODO (Batch 2 #14): Implement bridge + knowledge_point search with category filter.
"""
from fastapi import APIRouter, Query

from app.api.mobile.v1.schemas.common import MobileMeta, MobilePaginatedResponse

router = APIRouter()


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    type: str = "all",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> MobilePaginatedResponse[dict]:
    """Unified search across bridges and knowledge points.

    TODO (Batch 2 #14): Implement actual search logic.
    """
    return MobilePaginatedResponse(
        data={"results": [], "suggestions": []},
        meta=MobileMeta(total=0, page=page, page_size=page_size, has_more=False),
    )
```

Update `app/api/mobile/v1/__init__.py`:

```python
from app.api.mobile.v1 import config, bridges, knowledge, qa, search

router = APIRouter()
router.include_router(config.router)
router.include_router(bridges.router, prefix="/bridges")
router.include_router(knowledge.router, prefix="/knowledge")
router.include_router(qa.router, prefix="/qa")
router.include_router(search.router)
```

**Step 4: Run test**

Run: `python3 -m pytest tests/test_api_mobile_search.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/mobile/v1/search.py app/api/mobile/v1/schemas/search.py app/api/mobile/v1/__init__.py tests/test_api_mobile_search.py
git commit -m "feat: mobile search endpoint placeholder"
```

---

## Task 10: Seed Script for Knowledge Points

**Files:**
- Create: `scripts/seed_knowledge_points.py`

**Step 1: Create the seed script**

```python
# scripts/seed_knowledge_points.py
"""Seed test knowledge_points data for mobile client integration testing.

Creates 3-5 knowledge_points under existing lvl3 taxonomy_nodes,
each with 2-3 key_points. Links chunk_ids from matching chunks where available.

Usage: python3 scripts/seed_knowledge_points.py
"""
import uuid

import click
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models import TaxonomyNode
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_key_point import KnowledgePointKeyPoint


SEED_DATA = [
    {
        "lvl3": "拱桥结构",
        "name": "拱桥结构",
        "aliases": "拱券桥,拱形桥",
        "difficulty": "beginner",
        "summary": "以拱圈为主要承重构件，将荷载转化为轴向压力的桥梁形式",
        "key_points": [
            {
                "summary": "拱桥以拱圈为主要承重构件，将荷载转化为轴向压力",
                "explanation": "拱桥利用拱形结构将竖向荷载转化为沿拱轴的压力，传至两端拱脚。这种受力方式使得石材等抗压材料的优势得到充分发挥。",
                "order_index": 1,
            },
            {
                "summary": "按拱圈形式分为圆弧拱、尖拱、抛物线拱等",
                "explanation": "不同的拱轴线形状决定了拱桥的受力特性和建筑风格。圆弧拱施工简便，尖拱常见于西方哥特式建筑，抛物线拱最接近理想压力线。",
                "order_index": 2,
            },
            {
                "summary": "中国古代石拱桥以赵州桥为代表，创造性地采用了敞肩拱设计",
                "explanation": "赵州桥在拱肩设置四个小拱，减轻自重、节约石料、利于泄洪，是世界桥梁史上的重要创新。",
                "order_index": 3,
            },
        ],
    },
    {
        "lvl3": "桥墩设计",
        "name": "桥墩设计",
        "aliases": "桥墩,墩台",
        "difficulty": "intermediate",
        "summary": "桥梁下部结构中承受上部荷载并传递至基础的构件",
        "key_points": [
            {
                "summary": "桥墩按形式分为重力式、柱式、薄壁式等",
                "explanation": "重力式桥墩靠自重抵抗水平力，适用于大跨径桥梁；柱式桥墩轻巧美观，常用于公路桥；薄壁式桥墩兼顾强度与经济性。",
                "order_index": 1,
            },
            {
                "summary": "古代桥墩常采用分水尖和船形墩减少水流冲刷",
                "explanation": "分水尖将水流分向两侧，降低墩前水压。船形墩上游尖下游圆，进一步优化水力学性能。洛阳桥即采用了筏型基础和船形墩。",
                "order_index": 2,
            },
        ],
    },
    {
        "lvl3": "河流特征",
        "name": "河流与桥梁选址",
        "aliases": "水文条件,桥位选择",
        "difficulty": "beginner",
        "summary": "河流的水文特征对桥梁选址和设计具有决定性影响",
        "key_points": [
            {
                "summary": "桥梁选址需考虑河宽、水深、流速、洪水频率等水文参数",
                "explanation": "理想的桥位应选在河道顺直、河床稳定、岸基坚固的地方。弯道处水流冲刷不均，不利于桥墩安全。",
                "order_index": 1,
            },
            {
                "summary": "中国南北方河流特征差异导致桥梁形式的地域差异",
                "explanation": "北方河流季节性强、含沙量大，多采用简支梁桥；南方水网密布、水量充沛，发展出丰富的拱桥和廊桥形式。",
                "order_index": 2,
            },
        ],
    },
]


@click.command()
def main() -> None:
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Check if knowledge_points table exists
        result = db.execute(text("SELECT to_regclass('public.knowledge_points')"))
        if result.scalar_one() is None:
            click.echo("ERROR: knowledge_points table does not exist. Run migration first.")
            return

        # Check if already seeded
        count = db.execute(text("SELECT COUNT(*) FROM knowledge_points")).scalar_one()
        if count > 0:
            click.echo(f"knowledge_points already has {count} records. Skipping seed.")
            return

        created = 0
        for item in SEED_DATA:
            # Find matching lvl3 taxonomy node
            tax_node = db.query(TaxonomyNode).filter(
                TaxonomyNode.lvl3 == item["lvl3"]
            ).first()

            if not tax_node:
                click.echo(f"  WARNING: lvl3 '{item['lvl3']}' not found in taxonomy_nodes, skipping")
                continue

            # Find matching chunk IDs for citations
            chunk_rows = db.execute(
                text("SELECT id FROM chunks WHERE lvl3 = :lvl3 LIMIT 5"),
                {"lvl3": item["lvl3"]},
            ).all()
            chunk_ids = [row[0] for row in chunk_rows] if chunk_rows else None

            kp = KnowledgePoint(
                taxonomy_node_id=tax_node.id,
                name=item["name"],
                aliases=item["aliases"],
                difficulty=item["difficulty"],
                summary=item["summary"],
            )
            db.add(kp)
            db.flush()

            for kp_data in item["key_points"]:
                key_point = KnowledgePointKeyPoint(
                    knowledge_point_id=kp.id,
                    summary=kp_data["summary"],
                    explanation=kp_data["explanation"],
                    order_index=kp_data["order_index"],
                    chunk_ids=chunk_ids,
                )
                db.add(key_point)

            created += 1
            click.echo(f"  Created: {item['name']} ({len(item['key_points'])} key points)")

        db.commit()
        click.echo(f"\nSeeded {created} knowledge points.")

    except Exception as e:
        db.rollback()
        click.echo(f"ERROR: {e}", err=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

**Step 2: Verify script is syntactically correct**

Run: `python3 -c "import ast; ast.parse(open('scripts/seed_knowledge_points.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/seed_knowledge_points.py
git commit -m "feat: seed script for test knowledge_points data"
```

---

## Task 11: Run Full Test Suite + Final Commit

**Step 1: Run all tests**

Run: `python3 -m pytest tests/ -v --ignore=tests/integration`
Expected: ALL PASS (existing tests should not be broken)

**Step 2: Verify mobile endpoints are all registered**

Run: `python3 -c "from app.main import app; paths = [r.path for r in app.routes]; mobile = [p for p in paths if '/api/mobile/' in p]; print('\n'.join(sorted(mobile)))"`

Expected output:
```
/api/mobile/v1/bridges
/api/mobile/v1/bridges/{bridge_id}
/api/mobile/v1/bridges/{bridge_id}/knowledge-points
/api/mobile/v1/config
/api/mobile/v1/knowledge/points/{point_id}
/api/mobile/v1/knowledge/points/{point_id}/bridges
/api/mobile/v1/knowledge/tree
/api/mobile/v1/qa/ask
/api/mobile/v1/search
```

**Step 3: If any test failures, fix and commit**

**Step 4: Update CLAUDE.md if needed**

Add to the **API Endpoints** section:
```
- Mobile API (no auth): `/api/mobile/v1/config`, `/api/mobile/v1/bridges`, `/api/mobile/v1/knowledge/tree`, `/api/mobile/v1/knowledge/points/{id}`, `/api/mobile/v1/qa/ask`, `/api/mobile/v1/search`
```

Add to **Gotchas** if any new ones discovered.

Commit:
```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with mobile API endpoints"
```
