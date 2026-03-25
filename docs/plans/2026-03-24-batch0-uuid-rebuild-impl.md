# Batch 0: UUID Rebuild Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate all 8 tables to UUID primary keys, clean rebuild database to schema v1, rename `bridges.location` → `region` + add geo fields, and sync frontend types.

**Architecture:** Bottom-up single-PR approach — base mixins → models → database.py → services → API schemas → API endpoints → frontend types → frontend pages → tests. All in one worktree branch.

**Tech Stack:** SQLAlchemy 2.x (Mapped/mapped_column), PostgreSQL UUID, Pydantic v2, React + TypeScript

---

### Task 1: Rewrite `base.py` — UUIDMixin + TimestampMixin split

**Files:**
- Modify: `app/models/base.py`

**Step 1: Rewrite base.py**

Replace the entire file with:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

**Step 2: Verify import works**

Run: `python -c "from app.models.base import Base, UUIDMixin, CreatedAtMixin, TimestampMixin; print('OK')"`

**Step 3: Commit**

```
git add app/models/base.py
git commit -m "refactor(models): add UUIDMixin, split CreatedAtMixin/TimestampMixin"
```

---

### Task 2: Rewrite all models to UUID primary keys

**Files:**
- Modify: `app/models/bridge.py`
- Modify: `app/models/chunk.py`
- Modify: `app/models/source.py`
- Modify: `app/models/taxonomy.py`
- Modify: `app/models/chunk_bridge_link.py`
- Modify: `app/models/user.py`
- Modify: `app/models/audit_log.py`
- Modify: `app/models/ingest_task.py`

**Step 1: Rewrite each model**

**`bridge.py`** — Use `UUIDMixin + TimestampMixin`. Rename `location` → `region`. Add `latitude`/`longitude` (Double). Add `ix_bridges_geo` partial index.

```python
import uuid
from typing import Optional

from sqlalchemy import Double, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TimestampMixin


class Bridge(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "bridges"

    name: Mapped[str] = mapped_column(String(255))
    aliases: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    era: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bridge_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    material: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    function: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Double, nullable=True)

    __table_args__ = (
        Index(
            "ix_bridges_geo", "latitude", "longitude",
            postgresql_where=text("latitude IS NOT NULL"),
        ),
    )
```

**`chunk.py`** — Use `UUIDMixin + CreatedAtMixin`. Keep manual `updated_at`. Change FK types to `UUID`.

```python
import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text as sql_text
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import EMBEDDING_DIM
from app.models.base import Base, UUIDMixin, CreatedAtMixin


class Chunk(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "chunks"

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id"))
    content: Mapped[str] = mapped_column(Text)
    section_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lvl1: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl3: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bridge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bridges.id"), nullable=True
    )
    bridge_binding_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=sql_text("'none'"),
    )
    page_range: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    contextual_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    search_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tsv: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)
    needs_reindex: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_chunks_taxonomy", "lvl1", "lvl2", "lvl3"),
        Index("ix_chunks_bridge", "bridge_id"),
        Index("ix_chunks_source", "source_id"),
        Index("ix_chunks_binding_status", "bridge_binding_status"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
```

**`source.py`** — Use `UUIDMixin + CreatedAtMixin`.

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, CreatedAtMixin


class Source(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "sources"

    type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

**`taxonomy.py`** — Use `UUIDMixin` only (no timestamps).

```python
from typing import Optional

from sqlalchemy import Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class TaxonomyNode(Base, UUIDMixin):
    __tablename__ = "taxonomy_nodes"

    lvl1: Mapped[str] = mapped_column(String(100))
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl3: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "uq_taxonomy_nodes_path",
            "lvl1",
            text("COALESCE(lvl2, '')"),
            text("COALESCE(lvl3, '')"),
            unique=True,
        ),
    )
```

**`chunk_bridge_link.py`** — Use `UUIDMixin + CreatedAtMixin`. Change FK types to UUID.

```python
import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, CreatedAtMixin


class ChunkBridgeLink(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "chunk_bridge_links"

    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id"), nullable=False)
    bridge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bridges.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        Index("ix_chunk_bridge_links_chunk_id", "chunk_id"),
        Index("ix_chunk_bridge_links_bridge_id", "bridge_id"),
        Index("ix_chunk_bridge_links_role_confidence", "role", "confidence"),
    )
```

**`user.py`** — Use `UUIDMixin + TimestampMixin`. Remove manual `created_at`/`updated_at`.

```python
"""User model for authentication."""
from typing import Optional

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TimestampMixin


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

**`audit_log.py`** — Use `UUIDMixin + CreatedAtMixin`. Change `user_id` FK to UUID.

```python
"""Audit log model for tracking write operations."""
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, CreatedAtMixin


class AuditLog(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "audit_logs"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_user_id", "user_id"),
    )
```

**`ingest_task.py`** — Use `UUIDMixin + TimestampMixin`. Change FK types to UUID. Remove manual `created_at`/`updated_at`.

```python
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TimestampMixin


class IngestTask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ingest_tasks"

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploading")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    r2_raw_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    r2_parsed_prefix: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    zhipu_task_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id"), nullable=True
    )
    parsed_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
```

**Step 2: Verify all models import**

Run: `python -c "from app.models import Base, Bridge, Chunk, Source, TaxonomyNode, ChunkBridgeLink, User, AuditLog, IngestTask; print('OK')"`

**Step 3: Commit**

```
git add app/models/
git commit -m "refactor(models): migrate all tables to UUID primary keys

- Bridge: location→region, add latitude/longitude, add TimestampMixin
- Chunk: UUID FKs, keep manual updated_at for optimistic lock
- Source/TaxonomyNode/ChunkBridgeLink/AuditLog: UUID + CreatedAtMixin
- User/IngestTask: UUID + TimestampMixin"
```

---

### Task 3: Rewrite `database.py` — clean rebuild to schema v1

**Files:**
- Modify: `app/core/database.py`

**Step 1: Update database.py**

Changes:
1. `LATEST_SCHEMA_VERSION = 1`
2. Delete entire `_migrate_schema()` function
3. Update `verify_schema_compatibility()` `required_schema` dict:
   - `bridges`: replace `location` → `region`, add `latitude`, `longitude`, `updated_at`
   - Add `users` table: `{"id", "username", "hashed_password", "display_name", "is_active", "created_at", "updated_at"}`
   - Add `audit_logs` table: `{"id", "user_id", "action", "resource_type", "resource_id", "detail", "ip_address", "created_at"}`
4. Update `init_database()`:
   - Remove `_migrate_schema` call
   - Keep version < LATEST handling as RuntimeError (no migration path)
   - Change version stamp description to `"Schema v1: UUID primary keys, clean rebuild"`

**Step 2: Verify module imports**

Run: `python -c "from app.core.database import LATEST_SCHEMA_VERSION; assert LATEST_SCHEMA_VERSION == 1; print('OK')"`

**Step 3: Commit**

```
git add app/core/database.py
git commit -m "refactor(db): clean rebuild schema v1, delete old migrations

- LATEST_SCHEMA_VERSION = 1
- Remove _migrate_schema (v2→v6 chain)
- Update verify_schema_compatibility for new column names
- Add users/audit_logs to required_schema"
```

---

### Task 4: Update services — UUID type annotations + location→region

**Files:**
- Modify: `app/services/hybrid_retriever.py` (line 32, 39, 41, 154, 459, 489, 517, 522, 549)
- Modify: `app/services/ranker.py` (line 9, 10)
- Modify: `app/services/generator.py` (line 11)
- Modify: `app/services/audit_service.py` (line 31)
- Modify: `app/services/auth_service.py` (line 26)
- Modify: `app/services/ingest_task_service.py` (line 46, 56, 86, 242)
- Modify: `app/services/chunk_editor.py` (line 181, 233)
- Modify: `app/services/bridge_linker.py` (line 18)
- Modify: `app/api/v1/ask.py` (line 33 — `_resolve_bridge_from_question` return type)

**Step 1: Update type annotations**

For each service file, change `int` type hints for ID fields to `uuid.UUID`. Add `import uuid` where needed.

Key changes:
- `hybrid_retriever.py`: `bridge_id: Optional[int]` → `Optional[uuid.UUID]`, `chunk_id: int` → `uuid.UUID`, `target_bridge_id: Optional[int]` → `Optional[uuid.UUID]`, `chunk_ids: list[int]` → `list[uuid.UUID]`. **Line 489**: `Bridge.location.like(...)` → `Bridge.region.like(...)`
- `ranker.py`: `chunk_id: int` → `uuid.UUID`, `bridge_id: int | None` → `uuid.UUID | None`
- `generator.py`: `chunk_id: int` → `uuid.UUID`
- `audit_service.py`: `user_id: int | None` → `uuid.UUID | None`
- `auth_service.py`: `create_access_token(user_id: int, ...)` → `create_access_token(user_id: uuid.UUID, ...)`; the JWT `sub` field should store `str(user_id)`
- `ingest_task_service.py`: `user_id: int | None` → `uuid.UUID | None`, `task_id: int` → `uuid.UUID`
- `chunk_editor.py`: `chunk_ids: list[int]` → `list[uuid.UUID]`, `source_id: int` → `uuid.UUID`
- `bridge_linker.py`: `bridge_id: int` → `uuid.UUID`
- `ask.py`: `_resolve_bridge_from_question` return type → `uuid.UUID | None`

**Step 2: Verify services import**

Run: `python -c "from app.services.hybrid_retriever import HybridRetriever; from app.services.generator import Generator; print('OK')"`

**Step 3: Commit**

```
git add app/services/ app/api/v1/ask.py
git commit -m "refactor(services): update ID type annotations to UUID

- All bridge_id/chunk_id/source_id/user_id/task_id → uuid.UUID
- Bridge.location → Bridge.region in hybrid_retriever"
```

---

### Task 5: Update API schemas — int→UUID, location→region

**Files:**
- Modify: `app/api/v1/schemas/bridge.py`
- Modify: `app/api/v1/schemas/chunk.py`
- Modify: `app/api/v1/schemas/source.py`
- Modify: `app/api/v1/schemas/taxonomy.py`
- Modify: `app/api/v1/schemas/ingest_task.py`
- Modify: `app/api/v1/schemas/audit.py`
- Modify: `app/api/v1/schemas/auth.py`
- Modify: `app/api/v1/schemas/ask.py`

**Step 1: Update each schema file**

Add `from uuid import UUID` to each file. Change all ID fields from `int` to `UUID`.

**`schemas/bridge.py`:**
- `id: int` → `id: UUID` in `BridgeListItem`, `BridgeDetail`
- `location: str | None` → `region: str | None` in all four schemas
- Add `latitude: float | None = None` and `longitude: float | None = None` to all four schemas
- `source_bridge_id: int` → `source_bridge_id: UUID` in `BridgeMergeRequest`

**`schemas/chunk.py`:**
- `id: int` → `id: UUID` in `ChunkListItem`, `ChunkBridgeLinkDetail`, `ChunkDetail`
- `bridge_id: int | None` → `bridge_id: UUID | None` everywhere
- `source_id: int` → `source_id: UUID` everywhere
- `chunk_ids: list[int]` → `chunk_ids: list[UUID]` in `ChunkMergeRequest`, `ChunkBatchRequest`
- `bridge_id: int` → `bridge_id: UUID` in `BridgeLinkInput`, `ChunkBatchUpdate`
- `source_id: int` → `source_id: UUID` in `ReindexResponse`
- `chunks_failed: list[int]` → `chunks_failed: list[UUID]` in `ReindexResponse`

**`schemas/source.py`:**
- `id: int` → `id: UUID`

**`schemas/taxonomy.py`:**
- `id: int` → `id: UUID` in `TaxonomyNodeDetail`
- `node_id: int` → `node_id: UUID` in `TaxonomyTreeItem`
- `chunk_ids: list[int]` → `chunk_ids: list[UUID]` in `TaxonomyBatchUpdate`

**`schemas/ingest_task.py`:**
- `id: int` → `id: UUID` in `IngestTaskDetail`, `IngestTaskListItem`
- `source_id: int | None` → `source_id: UUID | None`
- `task_ids: list[int]` → `task_ids: list[UUID]` in `BatchDeleteRequest`
- `deleted: list[int]` / `skipped: list[int]` → `list[UUID]` in `BatchDeleteResponse`

**`schemas/audit.py`:**
- `id: int` → `id: UUID`
- `user_id: int | None` → `user_id: UUID | None`

**`schemas/auth.py`:**
- `id: int` → `id: UUID` in `UserInfo`

**`schemas/ask.py`:**
- `bridge_id: int | None` → `bridge_id: UUID | None` in `AskContext`
- `target_bridge_id: int | None` → `target_bridge_id: UUID | None` in `AskRequest`
- `chunk_id: int` → `chunk_id: UUID` in `CitationResponse`, `ChunkSummary`
- `bridge_id: int | None` → `bridge_id: UUID | None` in `ChunkSummary`
- `vec_ids: list[int]` → `list[UUID]` and `fts_ids: list[int]` → `list[UUID]` in `ChannelDebugResponse`
- `rrf_scores: list[list[int | float]]` → `list[list[UUID | float]]` — **Wait:** rrf_scores contain [chunk_id, score] pairs. Change to `list[list]` (mixed type) or keep as-is since chunk_id will be serialized as string in JSON. Actually, since these are UUID+float mixed lists, keep the type as `list[list]` or define a proper type. Simplest: keep `list[list]` without inner type constraint.
- `final_ids: list[int]` → `list[UUID]`

**Step 2: Verify schemas import**

Run: `python -c "from app.api.v1.schemas import BridgeListItem, ChunkListItem, AskRequest; print('OK')"`

**Step 3: Commit**

```
git add app/api/v1/schemas/
git commit -m "refactor(schemas): migrate all ID fields to UUID, location→region"
```

---

### Task 6: Update API endpoints — path params int→UUID

**Files:**
- Modify: `app/api/v1/bridges.py`
- Modify: `app/api/v1/chunks.py`
- Modify: `app/api/v1/sources.py`
- Modify: `app/api/v1/taxonomy.py`
- Modify: `app/api/v1/ingest_tasks.py`
- Modify: `app/api/v1/audit.py`

**Step 1: Update each endpoint file**

Add `from uuid import UUID` to each file.

**`bridges.py`:**
- All `bridge_id: int` → `bridge_id: UUID` in function signatures
- `target_id: int` → `target_id: UUID` in `merge_bridges`
- `Bridge.location` → `Bridge.region` in list query (line 40)
- `location=row.location` → `region=row.region` in list/detail response construction (lines 68, 105, 145)
- `bridge_id: int | None = None` query param in chunks list → `bridge_id: UUID | None = None` (actually this is in `chunks.py`)

**`chunks.py`:**
- `chunk_id: int` → `chunk_id: UUID` in all function signatures
- `bridge_id: int | None = None` → `bridge_id: UUID | None = None` in list_chunks query param
- `source_id: int | None = None` → `source_id: UUID | None = None` in list_chunks query param

**`sources.py`:**
- `source_id: int` → `source_id: UUID` in all function signatures

**`taxonomy.py`:**
- `node_id: int` → `node_id: UUID` in function signatures

**`ingest_tasks.py`:**
- `task_id: int` → `task_id: UUID` in all function signatures
- `_run_sync_and_parse(task_id: int, ...)` → `_run_sync_and_parse(task_id: UUID, ...)`
- `_run_indexing(task_id: int, ...)` → `_run_indexing(task_id: UUID, ...)`
- `user_id: int | None` → `user_id: UUID | None` in background task functions
- `deleted: list[int]` / `skipped: list[int]` → `list[UUID]` in batch_delete

**`audit.py`:** — Check if there are any ID path params (likely just query params for `user_id` filter).

**Step 2: Verify server starts**

Run: `python -c "from app.main import app; print('routes:', len(app.routes))"`

**Step 3: Commit**

```
git add app/api/v1/
git commit -m "refactor(api): migrate all path/query params to UUID"
```

---

### Task 7: Update frontend types — number→string, location→region

**Files:**
- Modify: `web/src/lib/types.ts`

**Step 1: Update all ID fields from `number` to `string`**

Search-and-replace pattern: every `id: number`, `bridge_id: number`, `source_id: number`, `chunk_id: number`, `node_id: number`, `user_id: number` → change `number` to `string`. Be careful not to change non-ID number fields like `chunk_count`, `page`, `page_size`, `confidence`, `file_size`, `image_count`, `position`, `order`.

Also rename all `location` fields to `region`, and add `latitude: number | null` and `longitude: number | null` where bridge types have `region`.

**Step 2: Verify types compile**

Run: `cd web && npx tsc --noEmit` — This will show errors in other files that still use `number` for IDs. That's expected; we fix those in the next tasks.

**Step 3: Commit**

```
git add web/src/lib/types.ts
git commit -m "refactor(web): migrate ID types to string, location→region"
```

---

### Task 8: Update frontend API client — number→string

**Files:**
- Modify: `web/src/lib/api.ts`

**Step 1: Change all function signatures**

Every function that takes an ID parameter typed as `number` → change to `string`. Examples:
- `fetchChunk(id: number)` → `fetchChunk(id: string)`
- `fetchBridge(id: number)` → `fetchBridge(id: string)`
- `fetchSource(id: number)` → `fetchSource(id: string)`
- `fetchIngestTask(id: number)` → `fetchIngestTask(id: string)`
- etc.

Do NOT change `window.location.href` references — those are browser APIs, not bridge location.

**Step 2: Commit**

```
git add web/src/lib/api.ts
git commit -m "refactor(web): update API client ID params to string"
```

---

### Task 9: Update frontend pages — remove Number() conversions, location→region

**Files:**
- Modify: `web/src/pages/ChunkDetailPage.tsx` (lines ~45, 73, 87: remove `Number(id)`)
- Modify: `web/src/pages/BridgeDetailPage.tsx` (lines ~58, 63, 70, 79: remove `Number(id)`)
- Modify: `web/src/pages/SourceDetailPage.tsx` (lines ~55, 60: remove `Number(id)`)
- Modify: `web/src/pages/IngestTaskDetailPage.tsx` (line ~178: remove `Number(id)` / `const taskId = Number(id)`)
- Modify: `web/src/pages/BridgeListPage.tsx` (line ~140: `bridge.location` → `bridge.region`)
- Modify: `web/src/components/bridges/BridgeForm.tsx` (lines ~57, 184, 186: `location` → `region`)

**Step 1: Update each file**

For detail pages, the pattern is:
```typescript
// Before
const { id } = useParams()
fetchChunk(Number(id))

// After
const { id } = useParams()
fetchChunk(id!)
```

For `IngestTaskDetailPage.tsx`:
```typescript
// Before
const { id } = useParams<{ id: string }>()
const taskId = Number(id)
// ... uses taskId and String(taskId) ...

// After
const { id: taskId } = useParams<{ id: string }>()
// ... use taskId directly (already string) ...
```

For `BridgeForm.tsx`:
```typescript
// Before
location: initialData?.location || null
// After
region: initialData?.region || null
```

For `BridgeListPage.tsx`:
```typescript
// Before
{bridge.location || ...
// After
{bridge.region || ...
```

**Step 2: Verify frontend compiles**

Run: `cd web && npx tsc --noEmit`
Expected: PASS (0 errors)

**Step 3: Commit**

```
git add web/src/
git commit -m "refactor(web): remove Number() ID conversions, location→region"
```

---

### Task 10: Update tests — UUID fixtures, location→region, schema assertions

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_database_init.py`
- Modify: `tests/test_models.py`

**Step 1: Update conftest.py**

- `location=` → `region=` in all Bridge fixtures (lines 71, 78, 85, 92)
- `bridge_id: int | None = None` → `bridge_id: uuid.UUID | None = None` in `chunk_factory` (line 114)
- Add `import uuid` at top

**Step 2: Update test_database_init.py**

- `"location"` → `"region"` in required_columns dicts (lines 125, 231)
- Add `"latitude"`, `"longitude"`, `"updated_at"` to bridges column sets
- Add `"users"` and `"audit_logs"` to `required_tables` lists and `required_columns` dicts
- Update `"Schema v6 with ingest_tasks table"` → `"Schema v1: UUID primary keys, clean rebuild"` in assertion (line 363)

**Step 3: Update test_models.py**

- `Bridge(name="赵州桥", location="河北赵县")` → `Bridge(name="赵州桥", region="河北赵县")` (line 23)

**Step 4: Run unit tests**

Run: `pytest tests/ -v --ignore=tests/integration -x`
Expected: All non-integration tests pass (except `test_health_endpoint` which is a known failure)

**Step 5: Commit**

```
git add tests/
git commit -m "test: update fixtures and assertions for UUID + region rename"
```

---

### Task 11: Full verification

**Step 1: Run type check**

Run: `cd web && npx tsc --noEmit`
Expected: PASS

**Step 2: Run unit tests**

Run: `pytest tests/ -v --ignore=tests/integration -x`
Expected: PASS (minus known `test_health_endpoint` failure)

**Step 3: Run lint**

Run: `cd web && npm run lint`
Expected: PASS (or only pre-existing warnings)

**Step 4: Verify server starts (requires DB)**

Run: `python scripts/reset_db.py --force && uvicorn app.main:app --host 0.0.0.0 --port 8000 &; sleep 3; curl -s http://localhost:8000/health | python -m json.tool; kill %1`
Expected: Health endpoint responds with version info

**Step 5: Final commit (if any fixes needed)**

If any issues found in steps 1-4, fix and commit with appropriate message.
