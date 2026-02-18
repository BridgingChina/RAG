# Chunk Editor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a manual chunk proofreading panel — content editing, tag/bridge_link modification, split/merge, batch operations, and stale-flag-based reindexing.

**Architecture:** Fine-grained REST endpoints (split, merge, batch, reindex) extending existing chunk CRUD. New `needs_reindex` column tracks stale embeddings. A daily background cron recomputes stale chunks. New `ChunkEditorPage` with dual-pane layout (list + editor) at `/sources/:sourceId/chunks/edit`.

**Tech Stack:** Python/FastAPI + SQLAlchemy (backend), React + TypeScript + shadcn/ui (frontend), jieba tokenizer, Zhipu embedding API.

**Design doc:** `docs/plans/2026-02-18-chunk-editor-design.md`

---

## Task 1: Schema — Add `needs_reindex` Column

**Files:**
- Modify: `app/models/chunk.py:15-34`
- Modify: `app/core/database.py:14`
- Modify: `scripts/migrate_db.py:157-204`
- Modify: `app/api/v1/schemas/chunk.py:7-17,29-45`
- Modify: `web/src/lib/types.ts:115-154`

**Step 1: Add column to Chunk model**

In `app/models/chunk.py`, after line 34 (`tsv` column), add:

```python
needs_reindex: Mapped[bool] = mapped_column(
    nullable=False, server_default=sql_text("false")
)
```

Import `Boolean` is not needed — `Mapped[bool]` infers it automatically.

**Step 2: Bump schema version**

In `app/core/database.py:14`, change:

```python
LATEST_SCHEMA_VERSION = 4
```

**Step 3: Add migration logic**

In `scripts/migrate_db.py`, add to `col_specs` list (after line 203):

```python
("chunks", "needs_reindex", "BOOLEAN NOT NULL DEFAULT false"),
```

Update `target_schema_description` at line 158:

```python
target_schema_description = "Schema v4 with chunk needs_reindex flag"
```

**Step 4: Add `needs_reindex` to schemas**

In `app/api/v1/schemas/chunk.py`:

- `ChunkListItem` (line 7): add `needs_reindex: bool` after `created_at`
- `ChunkDetail` (line 29): add `needs_reindex: bool` after `bridge_links`

**Step 5: Add to frontend types**

In `web/src/lib/types.ts`:

- `ChunkListItem` (line 115): add `needs_reindex: boolean` after `created_at`
- `ChunkDetail` (line 137): add `needs_reindex: boolean` after `bridge_links`

**Step 6: Update `list_chunks` and `get_chunk` to include `needs_reindex`**

In `app/api/v1/chunks.py`:

- `list_chunks` (line 37): add `Chunk.needs_reindex` to the query columns
- Line 84 `ChunkListItem(...)`: add `needs_reindex=row.needs_reindex`
- `get_chunk` (line 152): add `needs_reindex=chunk.needs_reindex`

**Step 7: Commit**

```bash
git add app/models/chunk.py app/core/database.py scripts/migrate_db.py \
       app/api/v1/chunks.py app/api/v1/schemas/chunk.py web/src/lib/types.ts
git commit -m "feat: add needs_reindex column to chunks (schema v4)"
```

---

## Task 2: Backend — Extend `ChunkUpdate` for Content + Bridge Links

**Files:**
- Modify: `app/api/v1/schemas/chunk.py:48-63`
- Modify: `app/api/v1/schemas/__init__.py:36-41,104-108`
- Test: `tests/test_api_v1_chunks.py`

**Step 1: Write route existence tests**

Append to `tests/test_api_v1_chunks.py`:

```python
def test_chunks_split_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/chunks/{chunk_id}/split" in route_paths


def test_chunks_merge_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/chunks/merge" in route_paths


def test_chunks_batch_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/chunks/batch" in route_paths


def test_sources_reindex_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/sources/{source_id}/reindex" in route_paths
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_v1_chunks.py -v
```

Expected: 4 new tests FAIL (routes don't exist yet).

**Step 3: Extend schemas**

In `app/api/v1/schemas/chunk.py`, add after line 63:

```python
class BridgeLinkInput(BaseModel):
    bridge_id: int
    role: Literal["primary", "secondary", "candidate"]
    confidence: float = 1.0
    method: Literal["hint", "rule", "llm", "manual"] = "manual"
```

Extend `ChunkUpdate` (line 48) — add fields after `binding_status`:

```python
    content: str | None = None
    section_title: str | None = None
    bridge_links: list[BridgeLinkInput] | None = None
```

Add new request/response schemas at the end of the file:

```python
class ChunkSplitRequest(BaseModel):
    position: int

class ChunkSplitResponse(BaseModel):
    chunks: list[ChunkDetail]

class ChunkMergeRequest(BaseModel):
    chunk_ids: list[int]

class ChunkBatchUpdate(BaseModel):
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None
    bridge_id: int | None = None
    binding_status: Literal["none", "primary", "ambiguous"] | None = None

    @field_validator("lvl1", "lvl2", "lvl3", mode="before")
    @classmethod
    def normalize_empty(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip() if isinstance(v, str) else v
            if isinstance(v, str) and not v:
                return None
        return v

class ChunkBatchRequest(BaseModel):
    chunk_ids: list[int]
    action: Literal["update", "delete"]
    updates: ChunkBatchUpdate | None = None

class ReindexResponse(BaseModel):
    source_id: int
    chunks_reindexed: int
    chunks_failed: list[int]
```

**Step 4: Update `__init__.py` re-exports**

In `app/api/v1/schemas/__init__.py`, update the chunk import block (lines 36-41) to include all new schemas:

```python
from .chunk import (
    BridgeLinkInput,
    ChunkBatchRequest,
    ChunkBatchUpdate,
    ChunkBridgeLinkDetail,
    ChunkDetail,
    ChunkListItem,
    ChunkMergeRequest,
    ChunkSplitRequest,
    ChunkSplitResponse,
    ChunkUpdate,
    ReindexResponse,
)
```

And add them to `__all__` (after line 108):

```python
    "BridgeLinkInput",
    "ChunkBatchRequest",
    "ChunkBatchUpdate",
    "ChunkMergeRequest",
    "ChunkSplitRequest",
    "ChunkSplitResponse",
    "ReindexResponse",
```

**Step 5: Commit**

```bash
git add app/api/v1/schemas/chunk.py app/api/v1/schemas/__init__.py tests/test_api_v1_chunks.py
git commit -m "feat: add chunk editor schemas (split/merge/batch/reindex)"
```

---

## Task 3: Backend — Extend `PUT /chunks/{id}` for Content + TSV

**Files:**
- Modify: `app/api/v1/chunks.py:172-244`
- Test: `tests/integration/test_chunk_editor.py` (create)

**Step 1: Write integration test**

Create `tests/integration/test_chunk_editor.py`:

```python
"""Integration tests for chunk editor endpoints."""
import pytest
from sqlalchemy import text

from app.core.constants import EMBEDDING_DIM


@pytest.fixture
def sample_chunk(db_session, test_source, tokenizer):
    """Create a single chunk for editing tests."""
    from app.models import Chunk

    chunk = Chunk(
        source_id=test_source.id,
        content="赵州桥是一座石拱桥，建于隋代。",
        section_title="赵州桥概述",
        lvl1="形制与技术",
        embedding=[0.0] * EMBEDDING_DIM,
        search_text="赵州桥是一座石拱桥，建于隋代。",
        contextual_text="关于赵州桥的基本介绍",
    )
    db_session.add(chunk)
    db_session.flush()

    tsv_text = tokenizer.to_tsvector_text(chunk.search_text)
    db_session.execute(
        text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
        {"tsv_text": tsv_text, "id": chunk.id},
    )
    db_session.flush()
    return chunk


def test_update_chunk_content(db_session, sample_chunk, tokenizer):
    """Updating content should recompute search_text, tsv, and set needs_reindex."""
    from app.services.chunk_editor import update_chunk_content

    new_content = "赵州桥是世界上现存最古老的石拱桥。"
    result = update_chunk_content(
        db=db_session,
        chunk=sample_chunk,
        new_content=new_content,
        tokenizer=tokenizer,
    )

    assert result.content == new_content
    assert new_content in result.search_text
    assert result.needs_reindex is True

    # Verify tsv was updated (non-null)
    row = db_session.execute(
        text("SELECT tsv IS NOT NULL as has_tsv FROM chunks WHERE id = :id"),
        {"id": sample_chunk.id},
    ).first()
    assert row.has_tsv is True
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/integration/test_chunk_editor.py::test_update_chunk_content -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.chunk_editor'`.

**Step 3: Create chunk_editor service**

Create `app/services/chunk_editor.py`:

```python
"""Service for chunk editing operations (content update, split, merge)."""
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.models import Chunk, ChunkBridgeLink
from app.services.tokenizer import Tokenizer


def update_chunk_content(
    *,
    db: Session,
    chunk: Chunk,
    new_content: str,
    tokenizer: Tokenizer,
) -> Chunk:
    """Update chunk content and recompute search_text + tsv. Sets needs_reindex=True."""
    chunk.content = new_content

    # Recompute search_text: contextual_text + content
    if chunk.contextual_text:
        chunk.search_text = f"{chunk.contextual_text}\n\n{new_content}"
    else:
        chunk.search_text = new_content

    # Recompute tsv
    tsv_text = tokenizer.to_tsvector_text(chunk.search_text)
    db.execute(
        sql_text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
        {"tsv_text": tsv_text, "id": chunk.id},
    )

    chunk.needs_reindex = True
    db.flush()
    return chunk
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/integration/test_chunk_editor.py::test_update_chunk_content -v
```

Expected: PASS.

**Step 5: Wire content update into `PUT /chunks/{id}`**

In `app/api/v1/chunks.py`, modify `update_chunk` (line 172-244):

- Add import: `from app.services.chunk_editor import update_chunk_content`
- Add import: `from app.api.v1.dependencies import get_tokenizer` (or create a tokenizer dependency)
- After line 224 (binding_status mapping), before the generic `setattr` loop, handle `content` specially:

```python
    # Handle content update (requires search_text + tsv recomputation)
    if "content" in update_data:
        from app.services.tokenizer import Tokenizer, default_user_dict_path
        tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
        update_chunk_content(
            db=db, chunk=chunk, new_content=update_data.pop("content"), tokenizer=tokenizer,
        )

    # Handle section_title
    if "section_title" in update_data:
        chunk.section_title = update_data.pop("section_title")

    # Handle bridge_links replacement (Task 4)
    if "bridge_links" in update_data:
        update_data.pop("bridge_links")  # placeholder, implemented in Task 4
```

The remaining fields flow through the existing `setattr` loop unchanged.

**Step 6: Commit**

```bash
git add app/services/chunk_editor.py app/api/v1/chunks.py \
       tests/integration/test_chunk_editor.py
git commit -m "feat: support content editing in PUT /chunks/{id}"
```

---

## Task 4: Backend — Bridge Links Replacement in PUT

**Files:**
- Modify: `app/services/chunk_editor.py`
- Modify: `app/api/v1/chunks.py:172-244`
- Test: `tests/integration/test_chunk_editor.py`

**Step 1: Write integration test**

Append to `tests/integration/test_chunk_editor.py`:

```python
def test_replace_bridge_links(db_session, sample_chunk, test_bridges):
    """Replacing bridge_links should delete old links and insert new ones."""
    from app.models import ChunkBridgeLink
    from app.services.chunk_editor import replace_bridge_links

    target = test_bridges["target"]
    candidate1 = test_bridges["candidate1"]

    links_input = [
        {"bridge_id": target.id, "role": "primary", "confidence": 0.95, "method": "manual"},
        {"bridge_id": candidate1.id, "role": "secondary", "confidence": 0.6, "method": "manual"},
    ]

    replace_bridge_links(db=db_session, chunk=sample_chunk, links=links_input)

    db_links = (
        db_session.query(ChunkBridgeLink)
        .filter(ChunkBridgeLink.chunk_id == sample_chunk.id)
        .order_by(ChunkBridgeLink.role)
        .all()
    )
    assert len(db_links) == 2
    assert sample_chunk.bridge_id == target.id
    assert sample_chunk.bridge_binding_status == "primary"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/integration/test_chunk_editor.py::test_replace_bridge_links -v
```

**Step 3: Implement `replace_bridge_links`**

Add to `app/services/chunk_editor.py`:

```python
def replace_bridge_links(
    *,
    db: Session,
    chunk: Chunk,
    links: list[dict],
) -> Chunk:
    """Replace all bridge links for a chunk. Updates chunk.bridge_id from primary link."""
    # Delete existing links
    db.query(ChunkBridgeLink).filter(ChunkBridgeLink.chunk_id == chunk.id).delete()

    # Insert new links
    primary_bridge_id = None
    for link_data in links:
        db.add(ChunkBridgeLink(
            chunk_id=chunk.id,
            bridge_id=link_data["bridge_id"],
            role=link_data["role"],
            confidence=link_data["confidence"],
            method=link_data.get("method", "manual"),
        ))
        if link_data["role"] == "primary" and primary_bridge_id is None:
            primary_bridge_id = link_data["bridge_id"]

    # Sync chunk.bridge_id and binding_status
    if primary_bridge_id is not None:
        chunk.bridge_id = primary_bridge_id
        chunk.bridge_binding_status = "primary"
    elif links:
        chunk.bridge_id = None
        chunk.bridge_binding_status = "ambiguous"
    else:
        chunk.bridge_id = None
        chunk.bridge_binding_status = "none"

    db.flush()
    return chunk
```

**Step 4: Wire into PUT endpoint**

In `app/api/v1/chunks.py`, replace the bridge_links placeholder from Task 3:

```python
    # Handle bridge_links replacement
    if "bridge_links" in update_data:
        from app.services.chunk_editor import replace_bridge_links
        bridge_links_data = update_data.pop("bridge_links")
        if bridge_links_data is not None:
            # Validate all bridge_ids exist
            for bl in bridge_links_data:
                bid = bl["bridge_id"] if isinstance(bl, dict) else bl.bridge_id
                if not db.query(Bridge).filter(Bridge.id == bid).first():
                    raise HTTPException(status_code=422, detail=f"Bridge {bid} not found")
            links_dicts = [bl if isinstance(bl, dict) else bl.model_dump() for bl in bridge_links_data]
            replace_bridge_links(db=db, chunk=chunk, links=links_dicts)
```

**Step 5: Run tests**

```bash
pytest tests/integration/test_chunk_editor.py -v
```

Expected: All PASS.

**Step 6: Commit**

```bash
git add app/services/chunk_editor.py app/api/v1/chunks.py \
       tests/integration/test_chunk_editor.py
git commit -m "feat: support bridge_links replacement in PUT /chunks/{id}"
```

---

## Task 5: Backend — Split Endpoint

**Files:**
- Modify: `app/api/v1/chunks.py`
- Modify: `app/services/chunk_editor.py`
- Test: `tests/integration/test_chunk_editor.py`

**Step 1: Write integration test**

Append to `tests/integration/test_chunk_editor.py`:

```python
def test_split_chunk(db_session, sample_chunk, tokenizer):
    """Splitting a chunk should create two new chunks and delete the original."""
    from app.models import Chunk
    from app.services.chunk_editor import split_chunk

    original_id = sample_chunk.id
    original_content = sample_chunk.content  # "赵州桥是一座石拱桥，建于隋代。"
    position = 9  # Split after "赵州桥是一座石拱桥"

    new_chunks = split_chunk(
        db=db_session,
        chunk=sample_chunk,
        position=position,
        tokenizer=tokenizer,
    )

    assert len(new_chunks) == 2
    assert new_chunks[0].content == original_content[:position]
    assert new_chunks[1].content == original_content[position:]
    assert new_chunks[0].lvl1 == "形制与技术"  # inherited
    assert new_chunks[1].lvl1 == "形制与技术"  # inherited
    assert new_chunks[0].needs_reindex is True
    assert new_chunks[1].needs_reindex is True

    # Original chunk should be gone
    assert db_session.query(Chunk).filter(Chunk.id == original_id).first() is None


def test_split_chunk_invalid_position(db_session, sample_chunk, tokenizer):
    """Split at invalid position should raise ValueError."""
    import pytest as _pytest
    from app.services.chunk_editor import split_chunk

    with _pytest.raises(ValueError, match="position"):
        split_chunk(db=db_session, chunk=sample_chunk, position=-1, tokenizer=tokenizer)

    with _pytest.raises(ValueError, match="position"):
        split_chunk(
            db=db_session, chunk=sample_chunk,
            position=len(sample_chunk.content) + 1, tokenizer=tokenizer,
        )
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_chunk_editor.py -k split -v
```

**Step 3: Implement `split_chunk`**

Add to `app/services/chunk_editor.py`:

```python
from app.core.constants import EMBEDDING_DIM


def split_chunk(
    *,
    db: Session,
    chunk: Chunk,
    position: int,
    tokenizer: Tokenizer,
) -> list[Chunk]:
    """Split a chunk at the given character position. Returns [chunk_a, chunk_b]."""
    content = chunk.content
    if position <= 0 or position >= len(content):
        raise ValueError(f"position must be between 1 and {len(content) - 1}, got {position}")

    content_a = content[:position]
    content_b = content[position:]

    # Inherit metadata
    shared_attrs = dict(
        source_id=chunk.source_id,
        section_title=chunk.section_title,
        lvl1=chunk.lvl1,
        lvl2=chunk.lvl2,
        lvl3=chunk.lvl3,
        bridge_id=chunk.bridge_id,
        bridge_binding_status=chunk.bridge_binding_status,
        page_range=chunk.page_range,
        needs_reindex=True,
    )

    # Create two new chunks with zero embeddings (will be recomputed on reindex)
    zero_embedding = [0.0] * EMBEDDING_DIM

    chunk_a = Chunk(content=content_a, embedding=zero_embedding, **shared_attrs)
    chunk_b = Chunk(content=content_b, embedding=zero_embedding, **shared_attrs)

    # Compute search_text + tsv for each
    for new_chunk in (chunk_a, chunk_b):
        new_chunk.search_text = new_chunk.content
        db.add(new_chunk)
    db.flush()

    for new_chunk in (chunk_a, chunk_b):
        tsv_text = tokenizer.to_tsvector_text(new_chunk.search_text)
        db.execute(
            sql_text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
            {"tsv_text": tsv_text, "id": new_chunk.id},
        )

    # Copy bridge_links from original to both new chunks
    original_links = (
        db.query(ChunkBridgeLink)
        .filter(ChunkBridgeLink.chunk_id == chunk.id)
        .all()
    )
    for link in original_links:
        for new_chunk in (chunk_a, chunk_b):
            db.add(ChunkBridgeLink(
                chunk_id=new_chunk.id,
                bridge_id=link.bridge_id,
                role=link.role,
                confidence=link.confidence,
                method=link.method,
            ))

    # Delete original chunk and its links
    db.query(ChunkBridgeLink).filter(ChunkBridgeLink.chunk_id == chunk.id).delete()
    db.delete(chunk)
    db.flush()

    return [chunk_a, chunk_b]
```

**Step 4: Add the API endpoint**

In `app/api/v1/chunks.py`, add after `delete_chunk` (after line 275):

```python
@router.post("/{chunk_id}/split", response_model=ChunkSplitResponse)
def split_chunk_endpoint(
    chunk_id: int,
    body: ChunkSplitRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChunkSplitResponse:
    """Split a chunk at the given character position."""
    from app.services.chunk_editor import split_chunk as do_split
    from app.services.tokenizer import Tokenizer, default_user_dict_path

    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
    try:
        new_chunks = do_split(db=db, chunk=chunk, position=body.position, tokenizer=tokenizer)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()

    AuditService.log(
        db,
        action="split",
        resource_type="chunk",
        user_id=current_user.id,
        resource_id=str(chunk_id),
        detail={"new_chunk_ids": [c.id for c in new_chunks]},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return ChunkSplitResponse(chunks=[get_chunk(c.id, db) for c in new_chunks])
```

Add the import at the top of chunks.py:

```python
from app.api.v1.schemas.chunk import (
    ...
    ChunkSplitRequest,
    ChunkSplitResponse,
)
```

**Step 5: Run tests**

```bash
pytest tests/integration/test_chunk_editor.py -k split -v
pytest tests/test_api_v1_chunks.py::test_chunks_split_endpoint_exists -v
```

Expected: All PASS.

**Step 6: Commit**

```bash
git add app/services/chunk_editor.py app/api/v1/chunks.py \
       tests/integration/test_chunk_editor.py
git commit -m "feat: add POST /chunks/{id}/split endpoint"
```

---

## Task 6: Backend — Merge Endpoint

**Files:**
- Modify: `app/api/v1/chunks.py`
- Modify: `app/services/chunk_editor.py`
- Test: `tests/integration/test_chunk_editor.py`

**Step 1: Write integration test**

Append to `tests/integration/test_chunk_editor.py`:

```python
def test_merge_chunks(db_session, test_source, tokenizer):
    """Merging chunks should combine content and delete extras."""
    from app.models import Chunk
    from app.services.chunk_editor import merge_chunks

    chunks = []
    for i, text in enumerate(["第一段内容。", "第二段内容。", "第三段内容。"]):
        c = Chunk(
            source_id=test_source.id,
            content=text,
            lvl1="形制与技术" if i == 0 else "地域与环境",
            embedding=[0.0] * EMBEDDING_DIM,
            search_text=text,
        )
        db_session.add(c)
    db_session.flush()
    chunks = db_session.query(Chunk).filter(
        Chunk.source_id == test_source.id
    ).order_by(Chunk.id).all()

    ids = [c.id for c in chunks]
    merged = merge_chunks(db=db_session, chunk_ids=ids, tokenizer=tokenizer)

    assert merged.content == "第一段内容。\n\n第二段内容。\n\n第三段内容。"
    assert merged.lvl1 == "形制与技术"  # inherited from first
    assert merged.needs_reindex is True
    assert merged.id == ids[0]  # kept first chunk

    # Others should be deleted
    remaining = db_session.query(Chunk).filter(Chunk.id.in_(ids[1:])).all()
    assert len(remaining) == 0


def test_merge_chunks_cross_source(db_session, test_source, tokenizer):
    """Merging chunks from different sources should raise ValueError."""
    import pytest as _pytest
    from app.models import Chunk, Source
    from app.services.chunk_editor import merge_chunks

    other_source = Source(type="note", title="Other")
    db_session.add(other_source)
    db_session.flush()

    c1 = Chunk(source_id=test_source.id, content="A", embedding=[0.0] * EMBEDDING_DIM)
    c2 = Chunk(source_id=other_source.id, content="B", embedding=[0.0] * EMBEDDING_DIM)
    db_session.add_all([c1, c2])
    db_session.flush()

    with _pytest.raises(ValueError, match="source"):
        merge_chunks(db=db_session, chunk_ids=[c1.id, c2.id], tokenizer=tokenizer)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_chunk_editor.py -k merge -v
```

**Step 3: Implement `merge_chunks`**

Add to `app/services/chunk_editor.py`:

```python
def merge_chunks(
    *,
    db: Session,
    chunk_ids: list[int],
    tokenizer: Tokenizer,
) -> Chunk:
    """Merge multiple chunks into the first one. Deletes the rest."""
    if len(chunk_ids) < 2:
        raise ValueError("At least 2 chunk_ids required for merge")

    chunks = []
    for cid in chunk_ids:
        c = db.query(Chunk).filter(Chunk.id == cid).first()
        if c is None:
            raise ValueError(f"Chunk {cid} not found")
        chunks.append(c)

    # Validate same source
    source_ids = {c.source_id for c in chunks}
    if len(source_ids) > 1:
        raise ValueError("All chunks must belong to the same source")

    # Merge into the first chunk
    primary = chunks[0]
    primary.content = "\n\n".join(c.content for c in chunks)

    # Recompute search_text
    if primary.contextual_text:
        primary.search_text = f"{primary.contextual_text}\n\n{primary.content}"
    else:
        primary.search_text = primary.content

    primary.needs_reindex = True
    db.flush()

    # Recompute tsv
    tsv_text = tokenizer.to_tsvector_text(primary.search_text)
    db.execute(
        sql_text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
        {"tsv_text": tsv_text, "id": primary.id},
    )

    # Delete the other chunks and their bridge links
    other_ids = [c.id for c in chunks[1:]]
    db.query(ChunkBridgeLink).filter(ChunkBridgeLink.chunk_id.in_(other_ids)).delete()
    for c in chunks[1:]:
        db.delete(c)

    db.flush()
    return primary
```

**Step 4: Add API endpoint**

In `app/api/v1/chunks.py`, add after the split endpoint:

```python
@router.post("/merge", response_model=ChunkDetail)
def merge_chunks_endpoint(
    body: ChunkMergeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChunkDetail:
    """Merge multiple chunks into one."""
    from app.services.chunk_editor import merge_chunks as do_merge
    from app.services.tokenizer import Tokenizer, default_user_dict_path

    tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
    try:
        merged = do_merge(db=db, chunk_ids=body.chunk_ids, tokenizer=tokenizer)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()

    AuditService.log(
        db,
        action="merge",
        resource_type="chunk",
        user_id=current_user.id,
        resource_id=str(merged.id),
        detail={"merged_chunk_ids": body.chunk_ids},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return get_chunk(merged.id, db)
```

Add `ChunkMergeRequest` to the imports at top.

**Step 5: Run tests**

```bash
pytest tests/integration/test_chunk_editor.py -k merge -v
pytest tests/test_api_v1_chunks.py::test_chunks_merge_endpoint_exists -v
```

**Step 6: Commit**

```bash
git add app/services/chunk_editor.py app/api/v1/chunks.py \
       tests/integration/test_chunk_editor.py
git commit -m "feat: add POST /chunks/merge endpoint"
```

---

## Task 7: Backend — Batch Endpoint

**Files:**
- Modify: `app/api/v1/chunks.py`
- Test: `tests/test_api_v1_chunks.py`

**Step 1: Add batch endpoint**

In `app/api/v1/chunks.py`, add after the merge endpoint:

```python
@router.patch("/batch", status_code=200)
def batch_chunks(
    body: ChunkBatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Batch update or delete chunks."""
    # Validate all chunk_ids exist
    existing = db.query(Chunk.id).filter(Chunk.id.in_(body.chunk_ids)).all()
    existing_ids = {row.id for row in existing}
    missing = set(body.chunk_ids) - existing_ids
    if missing:
        raise HTTPException(status_code=400, detail=f"Chunks not found: {sorted(missing)}")

    if body.action == "delete":
        db.query(ChunkBridgeLink).filter(
            ChunkBridgeLink.chunk_id.in_(body.chunk_ids)
        ).delete()
        count = db.query(Chunk).filter(Chunk.id.in_(body.chunk_ids)).delete()
        db.flush()

        AuditService.log(
            db,
            action="batch_delete",
            resource_type="chunk",
            user_id=current_user.id,
            detail={"chunk_ids": body.chunk_ids},
            ip_address=get_client_ip(request),
        )
        db.commit()
        return {"deleted": count}

    elif body.action == "update":
        if not body.updates:
            raise HTTPException(status_code=400, detail="updates required for action=update")

        update_data = body.updates.model_dump(exclude_unset=True)
        if "binding_status" in update_data:
            update_data["bridge_binding_status"] = update_data.pop("binding_status")

        # Validate bridge_id if present
        if "bridge_id" in update_data and update_data["bridge_id"] is not None:
            if not db.query(Bridge).filter(Bridge.id == update_data["bridge_id"]).first():
                raise HTTPException(
                    status_code=422, detail=f"Bridge {update_data['bridge_id']} not found"
                )

        count = db.query(Chunk).filter(Chunk.id.in_(body.chunk_ids)).update(
            update_data, synchronize_session="fetch"
        )
        db.flush()

        AuditService.log(
            db,
            action="batch_update",
            resource_type="chunk",
            user_id=current_user.id,
            detail={"chunk_ids": body.chunk_ids, "updates": update_data},
            ip_address=get_client_ip(request),
        )
        db.commit()
        return {"updated": count}
```

Add `ChunkBatchRequest` to the imports.

**Step 2: Run smoke test**

```bash
pytest tests/test_api_v1_chunks.py::test_chunks_batch_endpoint_exists -v
```

Expected: PASS.

**Step 3: Commit**

```bash
git add app/api/v1/chunks.py
git commit -m "feat: add PATCH /chunks/batch endpoint"
```

---

## Task 8: Backend — Reindex Endpoint

**Files:**
- Modify: `app/api/v1/sources.py`
- Test: `tests/test_api_v1_chunks.py` (route test already added in Task 2)
- Test: `tests/integration/test_chunk_editor.py`

**Step 1: Write integration test**

Append to `tests/integration/test_chunk_editor.py`:

```python
def test_reindex_stale_chunks(db_session, test_source, tokenizer):
    """Reindex should update needs_reindex chunks and clear the flag."""
    from app.models import Chunk
    from app.services.chunk_editor import reindex_source_chunks

    # Create a stale chunk
    c = Chunk(
        source_id=test_source.id,
        content="测试内容",
        embedding=[0.0] * EMBEDDING_DIM,
        search_text="测试内容",
        needs_reindex=True,
    )
    db_session.add(c)
    db_session.flush()

    # Reindex (without LLM — skip contextual_text, just recompute tsv + search_text)
    result = reindex_source_chunks(
        db=db_session,
        source_id=test_source.id,
        tokenizer=tokenizer,
        provider=None,  # None = skip embedding + contextual_text
        force=False,
    )

    assert result["chunks_reindexed"] == 1
    db_session.refresh(c)
    assert c.needs_reindex is False
```

**Step 2: Implement `reindex_source_chunks`**

Add to `app/services/chunk_editor.py`:

```python
import asyncio


def reindex_source_chunks(
    *,
    db: Session,
    source_id: int,
    tokenizer: Tokenizer,
    provider,  # LLMProvider | None — None skips embedding/contextual_text
    force: bool = False,
) -> dict:
    """Reindex chunks for a source. Returns {chunks_reindexed, chunks_failed}."""
    query = db.query(Chunk).filter(Chunk.source_id == source_id)
    if not force:
        query = query.filter(Chunk.needs_reindex == True)  # noqa: E712

    chunks = query.all()
    reindexed = 0
    failed = []

    for chunk in chunks:
        try:
            # Recompute search_text
            if chunk.contextual_text:
                chunk.search_text = f"{chunk.contextual_text}\n\n{chunk.content}"
            else:
                chunk.search_text = chunk.content

            # Recompute tsv
            tsv_text = tokenizer.to_tsvector_text(chunk.search_text)
            db.execute(
                sql_text(
                    "UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"
                ),
                {"tsv_text": tsv_text, "id": chunk.id},
            )

            # Recompute embedding if provider available
            if provider is not None:
                embedding_result = asyncio.run(provider.embed([chunk.search_text]))
                chunk.embedding = embedding_result[0]

            chunk.needs_reindex = False
            reindexed += 1
        except Exception:
            failed.append(chunk.id)

    db.flush()
    return {
        "source_id": source_id,
        "chunks_reindexed": reindexed,
        "chunks_failed": failed,
    }
```

**Step 3: Add API endpoint**

In `app/api/v1/sources.py`, add after line 86:

```python
@router.post("/{source_id}/reindex", response_model=ReindexResponse)
def reindex_source(
    source_id: int,
    request: Request,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReindexResponse:
    """Reindex chunks for a source (recompute search_text, tsv, embedding)."""
    from app.api.v1.dependencies import get_client_ip, get_provider
    from app.services.audit_service import AuditService
    from app.services.chunk_editor import reindex_source_chunks
    from app.services.tokenizer import Tokenizer, default_user_dict_path

    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
    provider = get_provider()

    result = reindex_source_chunks(
        db=db,
        source_id=source_id,
        tokenizer=tokenizer,
        provider=provider,
        force=force,
    )

    db.commit()

    AuditService.log(
        db,
        action="reindex",
        resource_type="source",
        user_id=current_user.id,
        resource_id=str(source_id),
        detail={"chunks_reindexed": result["chunks_reindexed"]},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return ReindexResponse(**result)
```

Add required imports at top of `sources.py`:

```python
from fastapi import Request
from app.api.v1.dependencies import get_current_user
from app.api.v1.schemas.chunk import ReindexResponse
from app.models import User
```

**Step 4: Run tests**

```bash
pytest tests/integration/test_chunk_editor.py::test_reindex_stale_chunks -v
pytest tests/test_api_v1_chunks.py::test_sources_reindex_endpoint_exists -v
```

**Step 5: Commit**

```bash
git add app/api/v1/sources.py app/services/chunk_editor.py \
       tests/integration/test_chunk_editor.py
git commit -m "feat: add POST /sources/{id}/reindex endpoint"
```

---

## Task 9: Backend — Background Reindex Cron

**Files:**
- Modify: `app/main.py`
- Create: `app/services/reindex_cron.py`

**Step 1: Create cron service**

Create `app/services/reindex_cron.py`:

```python
"""Background cron job for reindexing stale chunks."""
import asyncio
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.core.logging import logger
from app.services.chunk_editor import reindex_source_chunks
from app.services.tokenizer import Tokenizer, default_user_dict_path


def _next_run_time(hour: int = 3) -> datetime:
    """Calculate next occurrence of the given hour (local time)."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


async def reindex_cron_loop(hour: int = 3):
    """Run reindex for all stale chunks daily at the given hour."""
    while True:
        next_run = _next_run_time(hour)
        wait_seconds = (next_run - datetime.now()).total_seconds()
        logger.info(f"Reindex cron: next run at {next_run} ({wait_seconds:.0f}s from now)")
        await asyncio.sleep(wait_seconds)

        logger.info("Reindex cron: starting stale chunk reindex...")
        try:
            _run_reindex()
        except Exception:
            logger.exception("Reindex cron: failed")
        logger.info("Reindex cron: done")


def _run_reindex():
    """Synchronous reindex of all stale chunks across all sources."""
    from app.models import Chunk
    from sqlalchemy import distinct

    db = SessionLocal()
    tokenizer = Tokenizer(user_dict_path=default_user_dict_path())

    try:
        # Find all sources with stale chunks
        source_ids = (
            db.query(distinct(Chunk.source_id))
            .filter(Chunk.needs_reindex == True)  # noqa: E712
            .all()
        )

        total = 0
        for (source_id,) in source_ids:
            result = reindex_source_chunks(
                db=db,
                source_id=source_id,
                tokenizer=tokenizer,
                provider=None,  # TODO: inject real provider for embedding recomputation
                force=False,
            )
            total += result["chunks_reindexed"]

        db.commit()
        logger.info(f"Reindex cron: reindexed {total} chunks across {len(source_ids)} sources")
    finally:
        db.close()
```

**Step 2: Wire into lifespan**

In `app/main.py`, add the cron task startup in the lifespan (after `init_database()`, before `yield`):

```python
    import asyncio as _asyncio
    from app.services.reindex_cron import reindex_cron_loop
    _asyncio.get_event_loop().create_task(reindex_cron_loop())
    logger.info("Reindex cron task scheduled")
```

Note: This runs inside the async lifespan context, so `get_event_loop()` is available. The task runs in the background and does not block.

**Step 3: Commit**

```bash
git add app/services/reindex_cron.py app/main.py
git commit -m "feat: add daily reindex cron for stale chunks"
```

---

## Task 10: Frontend — Types + API Client Updates

**Files:**
- Modify: `web/src/lib/types.ts:115-162`
- Modify: `web/src/lib/api.ts:170-199`

**Step 1: Update types**

In `web/src/lib/types.ts`, add to `ChunkUpdateRequest` (line 156):

```typescript
export interface ChunkUpdateRequest {
  lvl1?: string | null
  lvl2?: string | null
  lvl3?: string | null
  bridge_id?: number | null
  binding_status?: "none" | "primary" | "ambiguous"
  content?: string | null
  section_title?: string | null
  bridge_links?: BridgeLinkInput[] | null
}

export interface BridgeLinkInput {
  bridge_id: number
  role: "primary" | "secondary" | "candidate"
  confidence?: number
  method?: "hint" | "rule" | "llm" | "manual"
}

export interface ChunkSplitRequest {
  position: number
}

export interface ChunkSplitResponse {
  chunks: ChunkDetail[]
}

export interface ChunkMergeRequest {
  chunk_ids: number[]
}

export interface ChunkBatchUpdate {
  lvl1?: string | null
  lvl2?: string | null
  lvl3?: string | null
  bridge_id?: number | null
  binding_status?: "none" | "primary" | "ambiguous"
}

export interface ChunkBatchRequest {
  chunk_ids: number[]
  action: "update" | "delete"
  updates?: ChunkBatchUpdate
}

export interface ReindexResponse {
  source_id: number
  chunks_reindexed: number
  chunks_failed: number[]
}
```

**Step 2: Add API functions**

In `web/src/lib/api.ts`, after `deleteChunk` (line 199), add:

```typescript
export function splitChunk(
  id: number,
  data: ChunkSplitRequest,
): Promise<ChunkSplitResponse> {
  return post<ChunkSplitResponse>(`/chunks/${id}/split`, data)
}

export function mergeChunks(data: ChunkMergeRequest): Promise<ChunkDetail> {
  return post<ChunkDetail>("/chunks/merge", data)
}

export function batchChunks(data: ChunkBatchRequest): Promise<{ updated?: number; deleted?: number }> {
  return put<{ updated?: number; deleted?: number }>("/chunks/batch", data)
}

export function reindexSource(
  sourceId: number,
  force = false,
): Promise<ReindexResponse> {
  return post<ReindexResponse>(`/sources/${sourceId}/reindex?force=${force}`)
}
```

Add the new types to the import at the top of the file.

**Step 3: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/api.ts
git commit -m "feat: add chunk editor types and API client functions"
```

---

## Task 11: Frontend — ChunkEditorPage Layout + Routing

**Files:**
- Create: `web/src/pages/ChunkEditorPage.tsx`
- Modify: `web/src/router.tsx`

**Step 1: Create page skeleton**

Create `web/src/pages/ChunkEditorPage.tsx`:

```tsx
import { useState } from "react"
import { useNavigate, useParams } from "react-router"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Loader2, RotateCw } from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { useApi } from "@/hooks/useApi"
import { fetchChunks, fetchSource, reindexSource } from "@/lib/api"
import type { ChunkListItem, SourceDetail } from "@/lib/types"

export function Component() {
  const { sourceId } = useParams<{ sourceId: string }>()
  const navigate = useNavigate()
  const sid = Number(sourceId)

  const { data: source } = useApi(() => fetchSource(sid), [sid])
  const { data: chunksData, refetch } = useApi(
    () => fetchChunks({ source_id: sid, page_size: 200 }),
    [sid],
  )
  const chunks = chunksData?.items ?? []

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [reindexing, setReindexing] = useState(false)

  const staleCount = chunks.filter((c) => c.needs_reindex).length

  async function handleReindex() {
    setReindexing(true)
    try {
      await reindexSource(sid)
      await refetch()
    } finally {
      setReindexing(false)
    }
  }

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <>
      <PageHeader title={`校对 Chunks — ${source?.title ?? "..."}`}>
        <Button
          onClick={handleReindex}
          disabled={reindexing || staleCount === 0}
          variant="outline"
        >
          {reindexing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCw className="h-4 w-4" />}
          重新索引{staleCount > 0 ? ` (${staleCount})` : ""}
        </Button>
        <Button onClick={() => navigate(`/sources/${sourceId}`)} variant="outline">
          返回来源
        </Button>
      </PageHeader>

      <main className="flex gap-4 p-6 h-[calc(100vh-4rem)]">
        {/* Left pane: chunk list */}
        <div className="w-80 shrink-0 overflow-y-auto border rounded-lg bg-white">
          {chunks.map((chunk) => (
            <div
              key={chunk.id}
              onClick={() => setSelectedId(chunk.id)}
              className={`flex items-start gap-2 p-3 border-b cursor-pointer hover:bg-slate-50 ${
                selectedId === chunk.id ? "bg-blue-50" : ""
              }`}
            >
              <input
                type="checkbox"
                checked={selectedIds.has(chunk.id)}
                onChange={() => toggleSelect(chunk.id)}
                onClick={(e) => e.stopPropagation()}
                className="mt-1"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1 text-xs text-slate-400">
                  #{chunk.id}
                  {chunk.needs_reindex && (
                    <Badge variant="outline" className="text-orange-500 border-orange-300 text-[10px] px-1">
                      待索引
                    </Badge>
                  )}
                </div>
                <p className="text-sm text-slate-700 line-clamp-2">{chunk.content_preview}</p>
                <div className="flex gap-1 mt-1 flex-wrap">
                  {chunk.lvl1 && <Badge variant="secondary" className="text-[10px]">{chunk.lvl1}</Badge>}
                  {chunk.bridge_name && <Badge variant="outline" className="text-[10px]">{chunk.bridge_name}</Badge>}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Right pane: editor (Task 12) */}
        <div className="flex-1 overflow-y-auto border rounded-lg bg-white p-6">
          {selectedId ? (
            <p className="text-sm text-slate-500">编辑面板 — Chunk #{selectedId} (Task 12 实现)</p>
          ) : (
            <p className="text-sm text-slate-400">请从左侧选择一个 Chunk 进行编辑</p>
          )}
        </div>
      </main>

      {/* Batch toolbar (Task 14) */}
      {selectedIds.size >= 2 && (
        <div className="fixed bottom-0 left-0 right-0 bg-white border-t p-3 flex items-center gap-3 shadow-lg z-50">
          <span className="text-sm text-slate-600">已选 {selectedIds.size} 项</span>
          {/* Batch buttons in Task 14 */}
        </div>
      )}
    </>
  )
}
```

Note: `fetchSource` may need to be added to `api.ts` if not present — check `get_source` usage. The existing `fetchSource` function at `api.ts` should be:

```typescript
export function fetchSource(id: number): Promise<SourceDetail> {
  return get<SourceDetail>(`/sources/${id}`)
}
```

**Step 2: Add route**

In `web/src/router.tsx`, add after line 20 (after `sources/:id`):

```typescript
{ path: "sources/:sourceId/chunks/edit", lazy: () => import("@/pages/ChunkEditorPage") },
```

**Step 3: Verify it builds**

```bash
cd web && npx tsc --noEmit
```

**Step 4: Commit**

```bash
git add web/src/pages/ChunkEditorPage.tsx web/src/router.tsx web/src/lib/api.ts
git commit -m "feat: add ChunkEditorPage skeleton with dual-pane layout"
```

---

## Task 12: Frontend — Right Pane Editor (Content + Metadata)

**Files:**
- Modify: `web/src/pages/ChunkEditorPage.tsx`

**Step 1: Implement the editor panel**

Replace the right pane placeholder with a full editor component. This is the largest frontend task — extract a `ChunkEditPanel` component (can be inline in the same file or a separate component file).

The panel should:
1. Fetch full `ChunkDetail` when `selectedId` changes (`fetchChunk(selectedId)`)
2. Show a `<textarea>` for content editing
3. Show `<input>` for section_title
4. Show lvl1/lvl2/lvl3 dropdowns (fetch taxonomy tree from `/taxonomy/tree` to populate)
5. Show bridge_links table with add/remove rows
6. Show `[保存]` button calling `updateChunk(id, data)`
7. Show `needs_reindex` warning banner at top when true
8. Show `[删除]` button with confirmation

After save, call `refetch()` on the left pane to refresh the list.

**Step 2: Type-check**

```bash
cd web && npx tsc --noEmit
```

**Step 3: Commit**

```bash
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "feat: implement chunk editor right pane (content + metadata)"
```

---

## Task 13: Frontend — Split + Merge UI

**Files:**
- Modify: `web/src/pages/ChunkEditorPage.tsx`

**Step 1: Add split functionality**

In the editor panel, add a `[拆分]` button:
- On click, show a dialog with the chunk content and a slider/input for split position
- Use cursor position in the textarea as default split point
- Call `splitChunk(id, { position })` on confirm
- After split, refresh the left pane list and select the first new chunk

**Step 2: Add merge to batch toolbar**

In the batch toolbar (bottom), add `[合并]` button:
- Only enabled when ≥ 2 chunks selected
- Call `mergeChunks({ chunk_ids: [...selectedIds] })` — sort by id for natural order
- After merge, clear selection, refresh list, select the merged chunk

**Step 3: Type-check and commit**

```bash
cd web && npx tsc --noEmit
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "feat: add split and merge UI to chunk editor"
```

---

## Task 14: Frontend — Batch Operations Toolbar

**Files:**
- Modify: `web/src/pages/ChunkEditorPage.tsx`

**Step 1: Implement batch toolbar**

Fill in the batch toolbar at the bottom:
- `[改 Tag]` button → dialog with lvl1/lvl2/lvl3 selectors → `batchChunks({ chunk_ids, action: "update", updates: { lvl1, ... } })`
- `[改 Bridge]` button → dialog with bridge search/select → `batchChunks({ chunk_ids, action: "update", updates: { bridge_id } })`
- `[删除]` button → confirm dialog → `batchChunks({ chunk_ids, action: "delete" })`
- `[合并]` button (from Task 13)
- After any operation: clear selection, refresh list

**Step 2: Type-check and commit**

```bash
cd web && npx tsc --noEmit
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "feat: add batch operations toolbar to chunk editor"
```

---

## Task 15: Frontend — Entry Points

**Files:**
- Modify: `web/src/components/ingest/IngestPanel.tsx`
- Modify: `web/src/pages/SourceDetailPage.tsx`

**Step 1: Add "去校对" button to IngestPanel**

In `web/src/components/ingest/IngestPanel.tsx`, after line 131 (`<ChunkList ... />`), add:

```tsx
import { useNavigate } from "react-router"
// ... inside component:
const navigate = useNavigate()
// ... in JSX after ChunkList:
<div className="flex justify-end">
  <Button
    onClick={() => navigate(`/sources/${result.source_id}/chunks/edit`)}
    variant="outline"
  >
    去校对
  </Button>
</div>
```

**Step 2: Add "校对 Chunks" button to SourceDetailPage**

In `web/src/pages/SourceDetailPage.tsx`, in the `PageHeader` (line 98), add a button:

```tsx
<Button onClick={() => navigate(`/sources/${id}/chunks/edit`)} variant="outline">
  校对 Chunks
</Button>
```

**Step 3: Type-check and commit**

```bash
cd web && npx tsc --noEmit
git add web/src/components/ingest/IngestPanel.tsx web/src/pages/SourceDetailPage.tsx
git commit -m "feat: add chunk editor entry points from ingest and source pages"
```

---

## Task 16: Run All Tests + Final Verification

**Step 1: Run backend tests**

```bash
pytest tests/ -v
```

All existing + new tests should pass.

**Step 2: Run frontend type check + build**

```bash
cd web && npm run build
```

Should build without errors.

**Step 3: Run migration on dev DB (if available)**

```bash
python3 scripts/migrate_db.py
```

**Step 4: Manual smoke test**

Start the dev server and verify:
1. Navigate to a source → "校对 Chunks" button works
2. Chunk editor loads with dual-pane layout
3. Select a chunk → editor shows content, tags, bridge links
4. Edit content → save → tsv updated, needs_reindex flag set
5. Split a chunk → two new chunks appear
6. Multi-select → merge works
7. Batch update tags works
8. "重新索引" button triggers reindex and clears stale flags

**Step 5: Final commit (if any cleanup needed)**

```bash
git add -A && git commit -m "chore: chunk editor final cleanup"
```
