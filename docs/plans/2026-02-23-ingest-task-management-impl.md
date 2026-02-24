# Ingest Task Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the ingest page into a table-based task management UI with soft delete, retry, batch operations, file download, and comprehensive audit logging.

**Architecture:** Backend-first approach — add new endpoints and enhance existing ones, then rebuild the frontend. The backend changes are additive (new endpoints + modify existing), the frontend is a full page rewrite plus a new detail page.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, React, TypeScript, shadcn/ui, Tailwind CSS

**Design doc:** `docs/plans/2026-02-23-ingest-task-management-design.md`

---

### Task 1: Add new audit action constants

**Files:**
- Modify: `app/services/audit_service.py`
- Test: `tests/test_api_v1_ingest_tasks.py`

**Step 1: Add constants to AuditService**

In `app/services/audit_service.py`, add after the existing constants (line 17):

```python
RETRY = "retry_ingest"
INGEST_PARSE_START = "ingest_parse_start"
INGEST_PARSE_DONE = "ingest_parse_done"
INGEST_INDEX_DONE = "ingest_index_done"
INGEST_FAILED = "ingest_failed"
```

**Step 2: Commit**

```bash
git add app/services/audit_service.py
git commit -m "feat(audit): add ingest lifecycle audit action constants"
```

---

### Task 2: Add new Pydantic schemas

**Files:**
- Modify: `app/api/v1/schemas/ingest_task.py`

**Step 1: Add BatchDeleteRequest, BatchDeleteResponse, and DownloadUrlResponse**

Append to `app/api/v1/schemas/ingest_task.py`:

```python
class BatchDeleteRequest(BaseModel):
    task_ids: list[int]


class BatchDeleteResponse(BaseModel):
    deleted: list[int]
    skipped: list[int]


class DownloadUrlResponse(BaseModel):
    url: str
```

**Step 2: Commit**

```bash
git add app/api/v1/schemas/ingest_task.py
git commit -m "feat(schema): add batch-delete and download-url schemas for ingest tasks"
```

---

### Task 3: Enhance ingest_task_service.py with audit logging

**Files:**
- Modify: `app/services/ingest_task_service.py`

This task adds audit logging at every status transition in the background tasks, and passes `ip_address` + `user_id` through.

**Step 1: Add audit helper method and update `__init__`**

Add `ip_address` and `user_id` params to `__init__`:

```python
class IngestTaskService:
    def __init__(
        self,
        db: Session,
        r2: R2StorageService,
        provider: LLMProvider,
        file_parser: FileParserProvider | None = None,
        user_id: int | None = None,
        ip_address: str | None = None,
    ):
        self.db = db
        self.r2 = r2
        self.provider = provider
        self.file_parser = file_parser or FileParserProvider()
        self.user_id = user_id
        self.ip_address = ip_address
```

Add an `_audit` helper after `_fail`:

```python
def _audit(self, task: IngestTask, action: str, detail: dict | None = None) -> None:
    """Log an audit event for this task."""
    from app.services.audit_service import AuditService

    AuditService.log(
        self.db,
        action=action,
        resource_type="ingest_task",
        user_id=self.user_id or task.created_by,
        resource_id=str(task.id),
        detail=detail,
        ip_address=self.ip_address,
    )
```

**Step 2: Add audit calls in `sync_and_parse`**

In `sync_and_parse`, after `task.status = "syncing"` / `self.db.commit()` (line 76), no audit needed (already logged at endpoint level).

In `_parse_pdf`, after `task.status = "parsing"` / `self.db.commit()` (line 102), add:

```python
self._audit(task, AuditService.INGEST_PARSE_START)
self.db.commit()
```

In `sync_and_parse`, after `task.status = "chunked"` / `self.db.commit()` (line 93-94), change to:

```python
task.status = "chunked"
self.db.commit()

self._audit(task, AuditService.INGEST_PARSE_DONE, {"chunk_count": task.chunk_count})
self.db.commit()
```

**Step 3: Add audit calls in `start_indexing`**

After `task.status = "completed"` / `self.db.commit()` (line 330-331), change to:

```python
task.status = "completed"
self.db.commit()

self._audit(task, AuditService.INGEST_INDEX_DONE, {"chunk_count": task.chunk_count})
self.db.commit()
```

**Step 4: Add audit call in `_fail`**

Update `_fail` method:

```python
def _fail(self, task: IngestTask, error: str) -> None:
    try:
        task.status = "failed"
        task.error_message = error
        self.db.commit()

        self._audit(task, AuditService.INGEST_FAILED, {"error": error[:500]})
        self.db.commit()
    except Exception:
        self.db.rollback()
    logger.error(f"IngestTask {task.id} failed: {error}")
```

**Step 5: Add import**

Add at top of file:

```python
from app.services.audit_service import AuditService
```

**Step 6: Commit**

```bash
git add app/services/ingest_task_service.py
git commit -m "feat(audit): add lifecycle audit logging to ingest task service"
```

---

### Task 4: Update background task wrappers to pass user_id and ip_address

**Files:**
- Modify: `app/api/v1/ingest_tasks.py`

**Step 1: Update `_run_sync_and_parse` and `_run_indexing`**

```python
async def _run_sync_and_parse(task_id: int, user_id: int | None = None, ip_address: str | None = None):
    """BackgroundTask entry: run sync_and_parse in a new DB session."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        r2 = R2StorageService()
        provider = ZhipuProvider()
        file_parser = FileParserProvider()
        service = IngestTaskService(
            db=db, r2=r2, provider=provider, file_parser=file_parser,
            user_id=user_id, ip_address=ip_address,
        )
        await service.sync_and_parse(task_id)
    finally:
        db.close()


async def _run_indexing(task_id: int, user_id: int | None = None, ip_address: str | None = None):
    """BackgroundTask entry: run start_indexing in a new DB session."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        r2 = R2StorageService()
        provider = ZhipuProvider()
        service = IngestTaskService(
            db=db, r2=r2, provider=provider,
            user_id=user_id, ip_address=ip_address,
        )
        await service.start_indexing(task_id)
    finally:
        db.close()
```

**Step 2: Update callers to pass user_id and ip_address**

In `create_ingest_task` (line 179):

```python
background_tasks.add_task(_run_sync_and_parse, task.id, current_user.id, get_client_ip(request))
```

In `confirm_ingest_task` (line 262):

```python
background_tasks.add_task(_run_indexing, task.id, current_user.id, get_client_ip(request))
```

**Step 3: Commit**

```bash
git add app/api/v1/ingest_tasks.py
git commit -m "feat: pass user_id and ip_address to background ingest tasks"
```

---

### Task 5: Remove user ownership filter from all endpoints

**Files:**
- Modify: `app/api/v1/ingest_tasks.py`

**Step 1: Update all endpoints**

In `create_ingest_task` (line 148-155), remove `IngestTask.created_by == current_user.id` from the filter:

```python
task = (
    db.query(IngestTask)
    .filter(IngestTask.r2_raw_key == body.r2_key)
    .first()
)
```

In `list_ingest_tasks` (line 193), remove the user filter:

```python
query = db.query(IngestTask)
```

In `get_ingest_task` (line 226), change to:

```python
task = db.get(IngestTask, task_id)
if task is None:
    raise HTTPException(404, "Task not found")
```

In `confirm_ingest_task` (line 240-242), change to:

```python
task = db.get(IngestTask, task_id)
if task is None:
    raise HTTPException(404, "Task not found")
```

In `delete_ingest_task` (line 275-277), change to:

```python
task = db.get(IngestTask, task_id)
if task is None:
    raise HTTPException(404, "Task not found")
```

**Step 2: Commit**

```bash
git add app/api/v1/ingest_tasks.py
git commit -m "feat: remove user ownership filter from ingest task endpoints"
```

---

### Task 6: Enhance list endpoint with file_name search and deleted exclusion

**Files:**
- Modify: `app/api/v1/ingest_tasks.py`

**Step 1: Add file_name param and default exclude deleted**

Update `list_ingest_tasks`:

```python
@router.get("", response_model=PaginatedResponse[IngestTaskListItem])
def list_ingest_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    file_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List ingest tasks with optional filters."""
    query = db.query(IngestTask)

    if status:
        query = query.filter(IngestTask.status == status)
    else:
        # Default: exclude deleted tasks
        query = query.filter(IngestTask.status != "deleted")

    if file_name:
        query = query.filter(IngestTask.file_name.ilike(f"%{file_name}%"))

    total = query.count()
    tasks = (
        query.order_by(IngestTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedResponse(
        items=[IngestTaskListItem(**_task_to_detail(t)) for t in tasks],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )
```

**Step 2: Commit**

```bash
git add app/api/v1/ingest_tasks.py
git commit -m "feat: add file_name search and default exclude deleted from task list"
```

---

### Task 7: Convert delete endpoint to soft delete

**Files:**
- Modify: `app/api/v1/ingest_tasks.py`

**Step 1: Rewrite delete_ingest_task**

Extract cleanup logic into a helper `_cleanup_task_data` and rewrite delete:

```python
def _cleanup_task_data(db: Session, task: IngestTask) -> None:
    """Clean up chunks, bridge links, and source associated with a task."""
    if task.source_id:
        db.query(ChunkBridgeLink).filter(
            ChunkBridgeLink.chunk_id.in_(
                db.query(Chunk.id).filter(Chunk.source_id == task.source_id)
            )
        ).delete(synchronize_session=False)
        db.query(Chunk).filter(Chunk.source_id == task.source_id).delete(
            synchronize_session=False
        )
        db.query(Source).filter(Source.id == task.source_id).delete(
            synchronize_session=False
        )
        task.source_id = None


@router.delete("/{task_id}")
def delete_ingest_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete an ingest task (keeps task record and R2 files)."""
    task = db.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")

    if task.status in ("syncing", "parsing", "indexing"):
        raise HTTPException(
            400,
            f"Cannot delete task in '{task.status}' state -- wait for completion or failure",
        )

    _cleanup_task_data(db, task)

    task.status = "deleted"

    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="ingest_task",
        user_id=current_user.id,
        resource_id=str(task.id),
        detail={"file_name": task.file_name},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return {"ok": True}
```

**Step 2: Commit**

```bash
git add app/api/v1/ingest_tasks.py
git commit -m "feat: convert ingest task delete to soft delete"
```

---

### Task 8: Add retry endpoint

**Files:**
- Modify: `app/api/v1/ingest_tasks.py`

**Step 1: Add retry endpoint**

Add BEFORE the parametric routes section (before `@router.get("/{task_id}")`), after batch-delete (which we'll add in Task 9). For now add it between existing literal and parametric routes:

```python
@router.post("/{task_id}/retry", response_model=IngestTaskDetail)
def retry_ingest_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reset a failed/deleted task and re-run the pipeline."""
    task = db.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")

    if task.status not in ("failed", "deleted"):
        raise HTTPException(
            400,
            f"Cannot retry task in '{task.status}' state -- only failed or deleted tasks can be retried",
        )

    _cleanup_task_data(db, task)

    task.status = "syncing"
    task.error_message = None
    task.chunk_count = None
    task.parsed_content = None
    task.image_count = 0
    db.commit()

    AuditService.log(
        db,
        action=AuditService.RETRY,
        resource_type="ingest_task",
        user_id=current_user.id,
        resource_id=str(task.id),
        detail={"file_name": task.file_name},
        ip_address=get_client_ip(request),
    )
    db.commit()

    background_tasks.add_task(_run_sync_and_parse, task.id, current_user.id, get_client_ip(request))

    return IngestTaskDetail(**_task_to_detail(task))
```

**Step 2: Commit**

```bash
git add app/api/v1/ingest_tasks.py
git commit -m "feat: add retry endpoint for ingest tasks"
```

---

### Task 9: Add batch-delete endpoint

**Files:**
- Modify: `app/api/v1/ingest_tasks.py`
- Modify: `app/api/v1/schemas/ingest_task.py` (already done in Task 2)

**Step 1: Add import for new schemas**

Update the import at the top of `ingest_tasks.py`:

```python
from app.api.v1.schemas.ingest_task import (
    BatchDeleteRequest,
    BatchDeleteResponse,
    IngestTaskCreate,
    IngestTaskDetail,
    IngestTaskListItem,
    PresignRequest,
    PresignResponse,
)
```

**Step 2: Add batch-delete endpoint**

Add BEFORE parametric routes, after the list endpoint:

```python
RUNNING_STATUSES = {"syncing", "parsing", "indexing"}


@router.post("/batch-delete", response_model=BatchDeleteResponse)
def batch_delete_ingest_tasks(
    body: BatchDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete multiple ingest tasks."""
    deleted: list[int] = []
    skipped: list[int] = []

    for tid in body.task_ids:
        task = db.get(IngestTask, tid)
        if task is None:
            skipped.append(tid)
            continue
        if task.status in RUNNING_STATUSES:
            skipped.append(tid)
            continue

        _cleanup_task_data(db, task)
        task.status = "deleted"

        AuditService.log(
            db,
            action=AuditService.DELETE,
            resource_type="ingest_task",
            user_id=current_user.id,
            resource_id=str(task.id),
            detail={"file_name": task.file_name},
            ip_address=get_client_ip(request),
        )
        deleted.append(tid)

    db.commit()
    return BatchDeleteResponse(deleted=deleted, skipped=skipped)
```

**Step 3: Commit**

```bash
git add app/api/v1/ingest_tasks.py
git commit -m "feat: add batch-delete endpoint for ingest tasks"
```

---

### Task 10: Add download-url endpoint

**Files:**
- Modify: `app/api/v1/ingest_tasks.py`

**Step 1: Add download-url endpoint**

Add AFTER the confirm endpoint, before delete (it's a parametric route `/{task_id}/download-url`):

```python
from app.api.v1.schemas.ingest_task import DownloadUrlResponse  # add to imports

@router.get("/{task_id}/download-url", response_model=DownloadUrlResponse)
def get_download_url(
    task_id: int,
    type: str = Query(..., pattern="^(raw|parsed)$"),
    r2: R2StorageService = Depends(_get_r2),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a presigned download URL for task files."""
    task = db.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")

    if type == "raw":
        if not task.r2_raw_key:
            raise HTTPException(404, "No raw file available")
        url = r2.generate_presigned_download_url(task.r2_raw_key)
    else:  # parsed
        if not task.r2_parsed_prefix:
            raise HTTPException(404, "No parsed file available")
        url = r2.generate_presigned_download_url(f"{task.r2_parsed_prefix}result.md")

    return DownloadUrlResponse(url=url)
```

**Step 2: Commit**

```bash
git add app/api/v1/ingest_tasks.py
git commit -m "feat: add download-url endpoint for ingest task files"
```

---

### Task 11: Update smoke tests

**Files:**
- Modify: `tests/test_api_v1_ingest_tasks.py`

**Step 1: Add route assertions for new endpoints**

```python
"""Smoke tests for ingest-tasks API endpoints."""
from app.main import app


def test_ingest_tasks_endpoints_exist():
    """Verify ingest-task routes are registered."""
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/ingest-tasks/presign" in route_paths
    assert "/api/v1/ingest-tasks" in route_paths
    assert "/api/v1/ingest-tasks/batch-delete" in route_paths
    assert "/api/v1/ingest-tasks/{task_id}" in route_paths
    assert "/api/v1/ingest-tasks/{task_id}/confirm" in route_paths
    assert "/api/v1/ingest-tasks/{task_id}/retry" in route_paths
    assert "/api/v1/ingest-tasks/{task_id}/download-url" in route_paths
```

**Step 2: Run tests**

```bash
pytest tests/test_api_v1_ingest_tasks.py -v
```

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_api_v1_ingest_tasks.py
git commit -m "test: update smoke tests for new ingest task endpoints"
```

---

### Task 12: Verify route ordering

**Files:**
- Modify: `app/api/v1/ingest_tasks.py` (if needed)

**Important:** FastAPI requires literal routes before parametric routes. Verify the final route order is:

1. `POST /presign` (literal)
2. `POST /` (literal — create)
3. `GET /` (literal — list)
4. `POST /batch-delete` (literal)
5. `GET /{task_id}` (parametric)
6. `POST /{task_id}/confirm` (parametric)
7. `POST /{task_id}/retry` (parametric)
8. `GET /{task_id}/download-url` (parametric)
9. `DELETE /{task_id}` (parametric)

**Step 1: Reorder if necessary**

Check that `batch-delete` is BEFORE any `{task_id}` routes. The endpoint order in the file must match the order above.

**Step 2: Run tests to confirm**

```bash
pytest tests/test_api_v1_ingest_tasks.py -v
```

**Step 3: Commit if changes were made**

```bash
git add app/api/v1/ingest_tasks.py
git commit -m "fix: ensure correct route ordering for ingest task endpoints"
```

---

### Task 13: Update frontend types

**Files:**
- Modify: `web/src/lib/types.ts`

**Step 1: Add `deleted` to IngestTaskStatus**

Change the type (around line 75):

```typescript
export type IngestTaskStatus =
  | "uploading"
  | "syncing"
  | "parsing"
  | "chunked"
  | "indexing"
  | "completed"
  | "failed"
  | "deleted"
```

**Step 2: Add new types**

After `IngestTaskCreateRequest` (around line 115):

```typescript
export interface BatchDeleteRequest {
  task_ids: number[]
}

export interface BatchDeleteResponse {
  deleted: number[]
  skipped: number[]
}

export interface DownloadUrlResponse {
  url: string
}
```

**Step 3: Commit**

```bash
git add web/src/lib/types.ts
git commit -m "feat(web): add deleted status and new ingest task types"
```

---

### Task 14: Add new API functions

**Files:**
- Modify: `web/src/lib/api.ts`

**Step 1: Add imports for new types**

Add `BatchDeleteRequest`, `BatchDeleteResponse`, `DownloadUrlResponse` to the import block at top.

**Step 2: Add new functions after the existing ingest task functions**

```typescript
export function retryIngestTask(id: number): Promise<IngestTaskItem> {
  return post<IngestTaskItem>(`/ingest-tasks/${id}/retry`, {})
}

export function batchDeleteIngestTasks(
  taskIds: number[],
): Promise<BatchDeleteResponse> {
  return post<BatchDeleteResponse>("/ingest-tasks/batch-delete", {
    task_ids: taskIds,
  })
}

export function getIngestTaskDownloadUrl(
  id: number,
  type: "raw" | "parsed",
): Promise<DownloadUrlResponse> {
  return get<DownloadUrlResponse>(`/ingest-tasks/${id}/download-url`, { type })
}
```

**Step 3: Update fetchIngestTasks to support file_name param**

```typescript
export function fetchIngestTasks(params?: {
  page?: number
  page_size?: number
  status?: string
  file_name?: string
}): Promise<PaginatedResponse<IngestTaskItem>> {
  return get<PaginatedResponse<IngestTaskItem>>("/ingest-tasks", params)
}
```

**Step 4: Commit**

```bash
git add web/src/lib/api.ts
git commit -m "feat(web): add retry, batch-delete, download-url API functions"
```

---

### Task 15: Rewrite IngestPage with table view

**Files:**
- Rewrite: `web/src/pages/IngestPage.tsx`
- Delete content of: `web/src/components/ingest/IngestTaskList.tsx` (no longer used as separate component — inline in page)

**Step 1: Rewrite IngestPage.tsx**

The new page includes:
- Status filter tabs (全部 / 进行中 / 待确认 / 已完成 / 失败)
- File name search input
- "新建任务" button (opens upload dialog)
- Table with columns: checkbox, ID, file_name, type, status, source, created_at, actions
- Batch delete bar
- Pagination
- Auto-polling for running tasks

This is a large component. Key implementation notes:
- Use `useState` for: `tasks`, `loading`, `page`, `total`, `totalPages`, `statusFilter`, `searchQuery`, `selectedIds`, `r2Available`
- Status filter maps: `"running"` → backend query `status` param not set, filter client-side for `uploading|syncing|parsing|indexing`. Actually simpler: pass no status filter and filter display. But since backend already supports `status` param for single status, for "running" group, just don't pass status and filter locally — OR make 4 separate queries. **Best approach:** "running" tab sends no status filter, then uses `useMemo` to filter only running ones from the full list. **Simpler approach:** for "全部" send no status, for "进行中" don't use backend filter (fetch all, filter locally), for specific statuses use backend filter. **Simplest:** don't filter "进行中" on backend — just fetch all non-deleted tasks and filter in the UI based on active tab. The backend already defaults to excluding deleted.

Actually the cleanest approach:
- "全部" tab: `fetchIngestTasks({ page, page_size })` — backend excludes deleted by default
- "进行中" tab: `fetchIngestTasks({ page, page_size })` then filter locally for running statuses — BUT this breaks pagination. Better: fetch with no status filter and page_size large enough, or add backend support for multiple statuses.

**Simplest correct approach:** The tabs filter locally on the fetched page of data. Fetch all (non-deleted) from backend with pagination, and the tabs just highlight/dim rows. OR: backend `status` param supports comma-separated values.

**Decision:** Keep it simple — use backend `status` param for exact-match filters (chunked, completed, failed). For "进行中" tab, make 4 fetches... no, that's bad. **Best: add `status_group` param or just filter locally.** Given task count is small (page_size up to 100), **filter locally** is fine.

Implementation:
- Fetch all non-deleted tasks with current page + page_size + file_name search
- UI tabs filter the displayed results client-side
- "已删除" is a separate tab that sends `status=deleted` to backend

Here's the component structure (not writing full JSX — the implementer should use shadcn Table component pattern consistent with ChunkListPage/BridgeListPage):

```typescript
// Key state
const [tasks, setTasks] = useState<IngestTaskItem[]>([])
const [page, setPage] = useState(1)
const [totalPages, setTotalPages] = useState(0)
const [total, setTotal] = useState(0)
const [statusFilter, setStatusFilter] = useState<string>("all")
const [searchQuery, setSearchQuery] = useState("")
const [debouncedSearch, setDebouncedSearch] = useState("")
const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
const [loading, setLoading] = useState(true)
const [r2Available, setR2Available] = useState(true)
const [uploadDialogOpen, setUploadDialogOpen] = useState(false)

// Fetch logic
const loadTasks = useCallback(async () => {
  try {
    const params: Record<string, unknown> = { page, page_size: 20 }
    if (statusFilter === "deleted") params.status = "deleted"
    else if (statusFilter !== "all" && statusFilter !== "running") params.status = statusFilter
    if (debouncedSearch) params.file_name = debouncedSearch
    const res = await fetchIngestTasks(params)
    setTasks(res.items)
    setTotal(res.total)
    setTotalPages(res.total_pages)
  } catch { /* handle R2 fallback */ }
  finally { setLoading(false) }
}, [page, statusFilter, debouncedSearch])

// Displayed tasks (filter "running" tab locally)
const displayedTasks = useMemo(() => {
  if (statusFilter === "running") {
    return tasks.filter(t => ["uploading","syncing","parsing","indexing"].includes(t.status))
  }
  return tasks
}, [tasks, statusFilter])

// Auto-poll
useEffect(() => {
  if (tasks.some(t => ["uploading","syncing","parsing","indexing"].includes(t.status))) {
    const interval = setInterval(loadTasks, 3000)
    return () => clearInterval(interval)
  }
}, [tasks, loadTasks])
```

Status tabs: `["all", "running", "chunked", "completed", "failed", "deleted"]` with labels `["全部", "进行中", "待确认", "已完成", "失败", "已删除"]`.

Action buttons per row (reuse `TaskStatusBadge` from existing `IngestTaskList.tsx`, move helpers `formatTime`, `formatSize`, `isInProgress`, `STATUS_LABELS` into the page or a shared util):

- `chunked`: 校对 + 确认
- `failed` / `completed` / `deleted`: 重运行 (calls `retryIngestTask`)
- Non-running: 删除 (calls `deleteIngestTask`)

Batch bar: when `selectedIds.size > 0`, show a bar with count and "批量删除" button.

Consistent with the project's existing pages (e.g. `ChunkListPage`, `BridgeListPage`) for table styling.

**Step 2: Update STATUS_LABELS to include deleted**

```typescript
const STATUS_LABELS: Record<IngestTaskStatus, string> = {
  uploading: "上传中",
  syncing: "同步中",
  parsing: "解析中",
  chunked: "待确认",
  indexing: "标识中",
  completed: "已完成",
  failed: "失败",
  deleted: "已删除",
}
```

**Step 3: Run dev server and verify**

```bash
cd web && npx tsc --noEmit
```

Expected: no type errors

**Step 4: Commit**

```bash
git add web/src/pages/IngestPage.tsx web/src/components/ingest/IngestTaskList.tsx
git commit -m "feat(web): rewrite IngestPage as table view with filters and batch ops"
```

---

### Task 16: Create upload dialog component

**Files:**
- Create: `web/src/components/ingest/UploadDialog.tsx`

**Step 1: Create the dialog**

Wraps existing `FileUploadZone` logic in a shadcn `Dialog`. Props:

```typescript
interface UploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onTaskCreated: () => void  // triggers table refresh
}
```

The dialog contains the FileUploadZone component. On successful upload (`onTaskCreated` callback from FileUploadZone), close the dialog and call `onTaskCreated` to refresh the table.

**Step 2: Commit**

```bash
git add web/src/components/ingest/UploadDialog.tsx
git commit -m "feat(web): create upload dialog for ingest task creation"
```

---

### Task 17: Create IngestTaskDetailPage

**Files:**
- Create: `web/src/pages/IngestTaskDetailPage.tsx`
- Modify: `web/src/router.tsx` — add route
- Modify: `web/src/lib/api.ts` — add `fetchAuditLogs` with params (if not already exported)

**Step 1: Check if fetchAuditLogs exists**

Look in `api.ts` for existing audit log fetch function. If it exists, reuse it. If not, add:

```typescript
export function fetchAuditLogs(params?: {
  page?: number
  page_size?: number
  resource_type?: string
  resource_id?: string
}): Promise<PaginatedResponse<AuditLogItem>> {
  return get<PaginatedResponse<AuditLogItem>>("/audit-logs", params)
}
```

**Step 2: Create IngestTaskDetailPage**

The page fetches task detail + audit logs. Layout:

1. **Header** — PageHeader with back button, title = `任务 #${id}`
2. **Info card** — Grid showing: file_name, file_type, file_size, status badge, source link, created_at, updated_at, error_message
3. **Action buttons** — Same logic as table row actions (delete, retry, confirm, 校对)
4. **File download section** — Two buttons: "下载原始文件" and "下载解析结果". Each calls `getIngestTaskDownloadUrl(id, type)` and opens the returned URL in a new tab. Disable "下载解析结果" if task hasn't been parsed yet (status is uploading/syncing).
5. **Audit log timeline** — Fetch `GET /audit-logs?resource_type=ingest_task&resource_id={id}&page_size=50`. Display as a vertical timeline list, each entry shows: timestamp, action label, username, detail summary.

Action label map for audit display:

```typescript
const AUDIT_ACTION_LABELS: Record<string, string> = {
  ingest: "创建任务",
  confirm_ingest: "确认入库",
  delete: "删除",
  retry_ingest: "重运行",
  ingest_parse_start: "开始解析",
  ingest_parse_done: "解析完成",
  ingest_index_done: "索引完成",
  ingest_failed: "任务失败",
}
```

**Step 3: Add route in router.tsx**

Add after the ingest route (line 23):

```typescript
{ path: "ingest-tasks/:id", lazy: () => import("@/pages/IngestTaskDetailPage") },
```

**Step 4: Type check**

```bash
cd web && npx tsc --noEmit
```

**Step 5: Commit**

```bash
git add web/src/pages/IngestTaskDetailPage.tsx web/src/router.tsx web/src/lib/api.ts
git commit -m "feat(web): add IngestTaskDetailPage with file download and audit timeline"
```

---

### Task 18: Final integration test

**Step 1: Run all backend tests**

```bash
pytest tests/ -v --ignore=tests/integration
```

Expected: all PASS

**Step 2: Run frontend type check**

```bash
cd web && npx tsc --noEmit
```

Expected: no errors

**Step 3: Run frontend lint**

```bash
cd web && npm run lint
```

Expected: no errors (or only pre-existing ones)

**Step 4: Manual smoke test (if dev server available)**

Start backend and frontend, navigate to /ingest, verify:
- Table renders
- Status tabs filter
- Search works
- Upload dialog opens
- Task detail page loads
- Audit timeline shows

**Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address integration issues in ingest task management"
```
