# Optimistic Locking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add optimistic locking to chunk editor write operations using `updated_at` timestamps, preventing silent overwrites when multiple users edit concurrently.

**Architecture:** Add `updated_at` column to chunks table (schema v5). Single-chunk write endpoints (`PUT /chunks/{id}`, `POST /chunks/{id}/split`, `DELETE /chunks/{id}`) accept an optional `expected_updated_at`; on mismatch return 409. Frontend shows a conflict dialog on 409 with "discard" or "force overwrite" options.

**Tech Stack:** SQLAlchemy (onupdate), Pydantic schemas, React + shadcn/ui AlertDialog

---

### Task 1: Add `updated_at` to Chunk Model

**Files:**
- Modify: `.worktrees/chunk-editor/app/models/chunk.py:1-54`
- Modify: `.worktrees/chunk-editor/app/core/database.py:14` (LATEST_SCHEMA_VERSION)
- Modify: `.worktrees/chunk-editor/app/core/database.py:116-133` (verify_schema_compatibility)

**Step 1: Add `updated_at` column to Chunk model**

In `app/models/chunk.py`, add import and column:

```python
# Add to imports at top:
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text as sql_text

# Add after `needs_reindex` (line 37):
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
    nullable=False,
)
```

**Step 2: Bump LATEST_SCHEMA_VERSION**

In `app/core/database.py:14`, change:

```python
LATEST_SCHEMA_VERSION = 5
```

**Step 3: Add `updated_at` to verify_schema_compatibility**

In `app/core/database.py`, add `"updated_at"` to the `"chunks"` set in `required_schema` (around line 116-133).

**Step 4: Add v4→v5 migration**

In `app/core/database.py`, add after the `if current_version < 4:` block in `_migrate_schema`:

```python
if current_version < 5:
    logger.info("Migrating schema v4 → v5: adding chunks.updated_at column...")
    conn.execute(
        text(
            "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        )
    )
    # Backfill: set updated_at = created_at for existing rows
    conn.execute(text("UPDATE chunks SET updated_at = created_at WHERE updated_at = created_at"))
    set_schema_version(engine, 5, "Add chunk updated_at for optimistic locking", conn=conn)
    logger.info("Migration to v5 complete.")
```

**Step 5: Update init_database description**

In `app/core/database.py`, update the `set_schema_version` call in `init_database` (around line 342-343):

```python
set_schema_version(
    engine, LATEST_SCHEMA_VERSION, "Schema v5 with chunk updated_at for optimistic locking", conn=conn
)
```

**Step 6: Commit**

```bash
git add app/models/chunk.py app/core/database.py
git commit -m "feat: add updated_at column to chunks (schema v5)"
```

---

### Task 2: Add `updated_at` to migrate_db.py

**Files:**
- Modify: `.worktrees/chunk-editor/scripts/migrate_db.py:158,198-205`

**Step 1: Add column spec**

In `scripts/migrate_db.py`, add to `col_specs` list (after the `needs_reindex` entry around line 204):

```python
("chunks", "updated_at", "TIMESTAMPTZ NOT NULL DEFAULT now()"),
```

**Step 2: Add backfill for updated_at**

After the `bridge_binding_status` backfill block (around line 234-247), add:

```python
# Backfill updated_at from created_at for existing rows
if not dry_run and _column_info(conn, table="chunks", column="updated_at"):
    _q(
        conn,
        "UPDATE chunks SET updated_at = created_at WHERE updated_at = (SELECT MIN(created_at) FROM chunks)",
    )
    conn.commit()
```

Actually, simpler approach — the `DEFAULT now()` handles new rows, and for existing rows they all get `now()` on ADD COLUMN which is acceptable.

**Step 3: Update target description**

Change `target_schema_description` (line 158):

```python
target_schema_description = "Schema v5 with chunk updated_at for optimistic locking"
```

**Step 4: Commit**

```bash
git add scripts/migrate_db.py
git commit -m "chore: add updated_at to migrate_db.py column specs"
```

---

### Task 3: Add `updated_at` to Pydantic Schemas

**Files:**
- Modify: `.worktrees/chunk-editor/app/api/v1/schemas/chunk.py:7-18,30-48,57-65,77-78`

**Step 1: Add `updated_at` to response schemas**

In `app/api/v1/schemas/chunk.py`:

`ChunkListItem` — add after `needs_reindex: bool` (line 18):

```python
updated_at: datetime
```

`ChunkDetail` — add after `needs_reindex: bool` (line 47):

```python
updated_at: datetime
```

**Step 2: Add `expected_updated_at` to request schemas**

`ChunkUpdate` — add after `bridge_links` (line 65):

```python
expected_updated_at: datetime | None = None
```

`ChunkSplitRequest` — add after `position: int` (line 78):

```python
expected_updated_at: datetime | None = None
```

**Step 3: Commit**

```bash
git add app/api/v1/schemas/chunk.py
git commit -m "feat: add updated_at to chunk schemas"
```

---

### Task 4: Write Failing Test for `check_optimistic_lock`

**Files:**
- Create: `.worktrees/chunk-editor/tests/test_optimistic_lock.py`

**Step 1: Write the failing test**

```python
"""Unit tests for optimistic locking."""
from datetime import datetime, timezone

import pytest


def test_check_optimistic_lock_none_skips():
    """When expected is None, no exception is raised."""
    from app.services.chunk_editor import check_optimistic_lock

    # Create a mock chunk with updated_at
    class FakeChunk:
        id = 1
        updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # Should not raise
    check_optimistic_lock(FakeChunk(), expected=None)


def test_check_optimistic_lock_match_passes():
    """When expected matches updated_at, no exception is raised."""
    from app.services.chunk_editor import check_optimistic_lock

    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    class FakeChunk:
        id = 42
        updated_at = ts

    check_optimistic_lock(FakeChunk(), expected=ts)


def test_check_optimistic_lock_mismatch_raises_409():
    """When expected does not match updated_at, raise HTTPException 409."""
    from fastapi import HTTPException

    from app.services.chunk_editor import check_optimistic_lock

    class FakeChunk:
        id = 42
        updated_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(HTTPException) as exc_info:
        check_optimistic_lock(
            FakeChunk(),
            expected=datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        )

    assert exc_info.value.status_code == 409
    assert "chunk_id" in str(exc_info.value.detail)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_optimistic_lock.py -v`
Expected: FAIL — `ImportError: cannot import name 'check_optimistic_lock'`

**Step 3: Commit failing test**

```bash
git add tests/test_optimistic_lock.py
git commit -m "test: add failing tests for check_optimistic_lock"
```

---

### Task 5: Implement `check_optimistic_lock`

**Files:**
- Modify: `.worktrees/chunk-editor/app/services/chunk_editor.py:1-18`

**Step 1: Write minimal implementation**

In `app/services/chunk_editor.py`, add after imports (before `get_tokenizer`):

```python
from datetime import datetime

from fastapi import HTTPException


def check_optimistic_lock(chunk, expected: datetime | None) -> None:
    """Raise 409 if chunk was modified since the expected timestamp."""
    if expected is None:
        return
    if chunk.updated_at != expected:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "Chunk has been modified by another user",
                "current_updated_at": chunk.updated_at.isoformat(),
                "chunk_id": chunk.id,
            },
        )
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_optimistic_lock.py -v`
Expected: 3 PASSED

**Step 3: Commit**

```bash
git add app/services/chunk_editor.py tests/test_optimistic_lock.py
git commit -m "feat: implement check_optimistic_lock function"
```

---

### Task 6: Wire Optimistic Lock into API Endpoints

**Files:**
- Modify: `.worktrees/chunk-editor/app/api/v1/chunks.py:6-16,180-277,279-308,404-437`

**Step 1: Update imports**

In `app/api/v1/chunks.py`, add `check_optimistic_lock` to the import from `chunk_editor`:

```python
from app.services.chunk_editor import check_optimistic_lock, get_tokenizer
```

**Step 2: Wire into `update_chunk` (PUT)**

In the `update_chunk` function (line ~192), right after fetching the chunk and the 404 check, add:

```python
# Optimistic lock check
expected = body.expected_updated_at
check_optimistic_lock(chunk, expected)
```

Also pop `expected_updated_at` from `update_data` so it doesn't get set on the model:

After `update_data = body.model_dump(exclude_unset=True)` (line ~195), add:

```python
update_data.pop("expected_updated_at", None)
```

**Step 3: Wire into `delete_chunk` (DELETE)**

Add `expected_updated_at` as an optional query parameter:

```python
@router.delete("/{chunk_id}", status_code=204)
def delete_chunk(
    chunk_id: int,
    request: Request,
    expected_updated_at: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
```

Add import at top of file: `from datetime import datetime`

After the 404 check, add:

```python
check_optimistic_lock(chunk, expected_updated_at)
```

**Step 4: Wire into `split_chunk_endpoint` (POST split)**

After the 404 check (line ~417), add:

```python
check_optimistic_lock(chunk, body.expected_updated_at)
```

**Step 5: Update `get_chunk` to return `updated_at`**

In the `get_chunk` function, add `updated_at=chunk.updated_at` to the `ChunkDetail(...)` constructor.

**Step 6: Update `list_chunks` to return `updated_at`**

Add `Chunk.updated_at` to the query columns, and `updated_at=row.updated_at` to each `ChunkListItem(...)`.

**Step 7: Ensure batch update refreshes `updated_at`**

In `batch_chunks` for the `update` action, add `"updated_at": func.now()` to the update_data dict. Add import: `from sqlalchemy import func`.

**Step 8: Commit**

```bash
git add app/api/v1/chunks.py
git commit -m "feat: wire optimistic lock into chunk API endpoints"
```

---

### Task 7: Write Integration Test for Optimistic Lock

**Files:**
- Modify: `.worktrees/chunk-editor/tests/integration/test_chunk_editor.py`

**Step 1: Write the integration test**

Add to the end of `tests/integration/test_chunk_editor.py`:

```python
def test_optimistic_lock_conflict(db_session, sample_chunk, tokenizer):
    """Updating a chunk with stale expected_updated_at should raise 409."""
    from datetime import datetime, timezone
    from fastapi import HTTPException
    from app.services.chunk_editor import check_optimistic_lock, update_chunk_content

    # Record the original updated_at
    original_updated_at = sample_chunk.updated_at

    # First update succeeds
    update_chunk_content(
        db=db_session,
        chunk=sample_chunk,
        new_content="第一次修改",
        tokenizer=tokenizer,
    )
    db_session.flush()

    # The chunk's updated_at should still match original because
    # onupdate only triggers on commit; but needs_reindex was set.
    # Simulate a stale timestamp by using a known old value.
    import pytest
    stale_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    sample_chunk.updated_at = datetime(2026, 2, 18, tzinfo=timezone.utc)
    db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        check_optimistic_lock(sample_chunk, expected=stale_ts)

    assert exc_info.value.status_code == 409
```

**Step 2: Run test**

Run: `pytest tests/integration/test_chunk_editor.py::test_optimistic_lock_conflict -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_chunk_editor.py
git commit -m "test: add integration test for optimistic lock conflict"
```

---

### Task 8: Update Frontend Types

**Files:**
- Modify: `.worktrees/chunk-editor/web/src/lib/types.ts:115-206`

**Step 1: Add `updated_at` to response types**

In `ChunkListItem`, add after `needs_reindex: boolean` (line 127):

```typescript
updated_at: string
```

In `ChunkDetail`, add after `needs_reindex: boolean` (line 156):

```typescript
updated_at: string
```

**Step 2: Add `expected_updated_at` to request types**

In `ChunkUpdateRequest`, add after `bridge_links` (line 167):

```typescript
expected_updated_at?: string
```

In `ChunkSplitRequest`, add after `position: number` (line 177):

```typescript
expected_updated_at?: string
```

**Step 3: Commit**

```bash
git add web/src/lib/types.ts
git commit -m "feat: add updated_at to frontend chunk types"
```

---

### Task 9: Update Frontend API Client

**Files:**
- Modify: `.worktrees/chunk-editor/web/src/lib/api.ts:121-135,221-223`

**Step 1: Update `deleteChunk` to accept optional `expected_updated_at`**

Replace the `deleteChunk` function:

```typescript
export function deleteChunk(
  id: number,
  expectedUpdatedAt?: string,
): Promise<void> {
  const params = expectedUpdatedAt
    ? `?expected_updated_at=${encodeURIComponent(expectedUpdatedAt)}`
    : ""
  return del(`/chunks/${id}${params}`)
}
```

`updateChunk` and `splitChunk` don't need changes — they already pass the full request body which now includes `expected_updated_at` from types.

**Step 2: Add a `ConflictError` class for 409 detection**

Add near the top of `api.ts`, after the `authHeaders` function:

```typescript
export class ConflictError extends Error {
  currentUpdatedAt: string
  chunkId: number

  constructor(currentUpdatedAt: string, chunkId: number) {
    super("Chunk has been modified by another user")
    this.name = "ConflictError"
    this.currentUpdatedAt = currentUpdatedAt
    this.chunkId = chunkId
  }
}
```

**Step 3: Update error handling in `put` and `post` and `del` to detect 409**

In each HTTP helper (`get`, `post`, `put`, `del`, `patch`), add 409 detection before the generic error throw:

```typescript
if (res.status === 409) {
  const data = await res.json()
  throw new ConflictError(data.current_updated_at, data.chunk_id)
}
```

Add this after the `if (res.status === 401)` block in each function.

**Step 4: Commit**

```bash
git add web/src/lib/api.ts
git commit -m "feat: add ConflictError and updated_at support to API client"
```

---

### Task 10: Add Conflict Dialog to ChunkEditorPage

**Files:**
- Modify: `.worktrees/chunk-editor/web/src/pages/ChunkEditorPage.tsx`

**Step 1: Import ConflictError**

Add to imports:

```typescript
import { ConflictError } from "../lib/api"
```

**Step 2: Add conflict dialog state**

In the page component, add state:

```typescript
const [conflictOpen, setConflictOpen] = useState(false)
const [conflictRetryFn, setConflictRetryFn] = useState<(() => void) | null>(null)
```

**Step 3: Create conflict handler**

Add a helper function inside the component:

```typescript
function handleConflictError(err: unknown, retryWithoutLock: () => void): boolean {
  if (err instanceof ConflictError) {
    setConflictRetryFn(() => retryWithoutLock)
    setConflictOpen(true)
    return true
  }
  return false
}
```

**Step 4: Update save handler**

In the save/update handler, wrap the `updateChunk` call:
- Pass `expected_updated_at: selectedChunkDetail.updated_at` in the request body
- In the `catch` block, call `handleConflictError(err, () => { /* retry without expected_updated_at */ })`

**Step 5: Update split handler**

Same pattern: pass `expected_updated_at` in split request, catch 409.

**Step 6: Update delete handler**

Pass `expectedUpdatedAt` to `deleteChunk`, catch 409.

**Step 7: Add AlertDialog JSX**

Add at the end of the component JSX (before the closing fragment):

```tsx
<AlertDialog open={conflictOpen} onOpenChange={setConflictOpen}>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>编辑冲突</AlertDialogTitle>
      <AlertDialogDescription>
        该 Chunk 已被其他用户修改。您可以强制覆盖或放弃本次更改。
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel onClick={() => { setConflictOpen(false); refetchChunks(); }}>
        放弃修改
      </AlertDialogCancel>
      <AlertDialogAction onClick={() => { setConflictOpen(false); conflictRetryFn?.(); }}>
        强制覆盖
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

Add imports for AlertDialog components from `@/components/ui/alert-dialog`.

**Step 8: Run TypeScript check**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 9: Commit**

```bash
git add web/src/pages/ChunkEditorPage.tsx
git commit -m "feat: add conflict dialog for optimistic lock on chunk editor"
```

---

### Task 11: Run All Tests and Verify

**Step 1: Run unit tests**

Run: `pytest tests/test_optimistic_lock.py tests/test_api_v1_chunks.py -v`
Expected: All PASS

**Step 2: Run frontend type check**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 3: Run integration tests (if DB available)**

Run: `pytest tests/integration/test_chunk_editor.py -v`
Expected: All PASS (or skip if no DB)

**Step 4: Final commit if any fixes needed**

```bash
git add -A && git commit -m "fix: address test/type issues from optimistic lock"
```

---

### Task 12: Update CLAUDE.md Schema Version

**Files:**
- Modify: `.worktrees/chunk-editor/CLAUDE.md`

**Step 1: Update schema version reference**

Find `Current version: 3` (or 4) and change to:

```
- Current version: 5 (adds updated_at to chunks for optimistic locking)
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md schema version to 5"
```
