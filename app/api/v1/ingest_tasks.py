"""Ingest tasks API endpoints -- async multi-stage ingest pipeline."""
import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas import PaginatedResponse
from app.api.v1.pagination import paginate
from app.api.v1.schemas.ingest_task import (
    BatchDeleteFailure,
    BatchDeleteRequest,
    BatchDeleteResponse,
    DownloadUrlResponse,
    IngestTaskCreate,
    IngestTaskDetail,
    IngestTaskListItem,
    PresignRequest,
    PresignResponse,
)
from app.core.database import get_db
from app.models import Chunk, ChunkBridgeLink, Source, User
from app.models.ingest_task import IngestTask
from app.providers import get_provider
from app.providers.file_parser import FileParserProvider
from app.services.audit_service import AuditService
from app.services.ingest_task_service import IngestTaskService
from app.services.r2_storage import R2StorageService

router = APIRouter(prefix="/ingest-tasks")

ALLOWED_FILE_TYPES = {"pdf", "md"}
RUNNING_STATUSES = {"syncing", "parsing", "indexing"}


def _get_r2() -> R2StorageService:
    if not R2StorageService.is_configured():
        raise HTTPException(
            status_code=503,
            detail="R2 storage is not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY in .env",
        )
    return R2StorageService()


def _sanitize_filename(name: str) -> str:
    """Strip path components and limit to safe characters."""
    name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    name = re.sub(r'[^\w\-.\u4e00-\u9fff]', '_', name)
    return name[:200] or "unnamed"


async def _run_sync_and_parse(task_id: UUID, user_id: UUID | None = None, ip_address: str | None = None):
    """BackgroundTask entry: run sync_and_parse in a new DB session."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        r2 = R2StorageService()
        provider = get_provider()
        file_parser = FileParserProvider()
        service = IngestTaskService(
            db=db, r2=r2, provider=provider, file_parser=file_parser,
            user_id=user_id, ip_address=ip_address,
        )
        await service.sync_and_parse(task_id)
    finally:
        db.close()


async def _run_indexing(task_id: UUID, user_id: UUID | None = None, ip_address: str | None = None):
    """BackgroundTask entry: run start_indexing in a new DB session."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        r2 = R2StorageService()
        provider = get_provider()
        service = IngestTaskService(
            db=db, r2=r2, provider=provider,
            user_id=user_id, ip_address=ip_address,
        )
        await service.start_indexing(task_id)
    finally:
        db.close()


def _task_to_detail(task: IngestTask) -> dict:
    return {
        "id": task.id,
        "status": task.status,
        "file_name": task.file_name,
        "file_type": task.file_type,
        "file_size": task.file_size,
        "source_id": task.source_id,
        "chunk_count": task.chunk_count,
        "image_count": task.image_count,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "updated_at": task.updated_at.isoformat() if task.updated_at else "",
    }


class CleanupError(Exception):
    """Raised when _cleanup_task_data cannot complete atomically.

    Wraps the underlying ``SQLAlchemyError`` with task/source context so
    callers can surface an actionable message instead of a bare 500.
    """

    def __init__(self, task_id: UUID, source_id: UUID | None, cause: Exception):
        self.task_id = task_id
        self.source_id = source_id
        self.cause = cause
        super().__init__(
            f"cleanup failed for task {task_id} (source {source_id}): {cause}"
        )


def _cleanup_task_data(db: Session, task: IngestTask) -> None:
    """Detach ``task`` from its source and delete the source + chunks + links.

    Order matters: the task row in ``ingest_tasks`` on disk still holds the
    committed ``source_id``, so a naive ``DELETE FROM sources`` fails the
    (non-deferrable) ``ingest_tasks_source_id_fkey`` foreign key check.
    We must UPDATE ``ingest_tasks.source_id = NULL`` and flush it before the
    Source delete hits the DB.

    Runs inside a ``db.begin_nested()`` savepoint so that any failure
    (flush error, DELETE conflict, deadlock) rolls back ONLY this unit of work
    and surfaces a typed :class:`CleanupError` instead of leaving the outer
    transaction in a half-state with inconsistent in-memory object fields.
    Callers are expected to catch ``CleanupError`` and translate to an HTTP
    error without committing.
    """
    if not task.source_id:
        return

    source_id = task.source_id
    original_source_id = source_id  # for rollback of the ORM attribute
    try:
        with db.begin_nested():
            db.query(ChunkBridgeLink).filter(
                ChunkBridgeLink.chunk_id.in_(
                    db.query(Chunk.id).filter(Chunk.source_id == source_id)
                )
            ).delete(synchronize_session=False)
            db.query(Chunk).filter(Chunk.source_id == source_id).delete(
                synchronize_session=False
            )
            # Detach task from source and flush the UPDATE to the DB
            # before deleting the source itself.
            task.source_id = None
            db.flush()
            db.query(Source).filter(Source.id == source_id).delete(
                synchronize_session=False
            )
    except SQLAlchemyError as exc:
        # Restore the ORM attribute so in-memory state matches the DB
        # after the savepoint rollback.
        task.source_id = original_source_id
        logger.exception(
            "cleanup failed task=%s source=%s", task.id, source_id
        )
        raise CleanupError(task.id, source_id, exc) from exc


# IMPORTANT: literal routes MUST come before parametric routes


@router.post("/presign", response_model=PresignResponse)
def presign(
    body: PresignRequest,
    r2: R2StorageService = Depends(_get_r2),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a presigned URL for direct file upload to R2."""
    if body.file_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            400,
            f"Unsupported file_type: {body.file_type}. Allowed: {sorted(ALLOWED_FILE_TYPES)}",
        )

    safe_name = _sanitize_filename(body.file_name)

    # Create task record first to get an ID for the R2 key
    task = IngestTask(
        status="uploading",
        file_name=safe_name,
        file_type=body.file_type,
        file_size=body.file_size,
        created_by=current_user.id,
    )
    db.add(task)
    db.flush()

    r2_key = f"raw/{task.id}/{safe_name}"
    task.r2_raw_key = r2_key

    try:
        upload_url = r2.generate_presigned_upload_url(r2_key, body.content_type)
    except Exception:
        db.rollback()
        raise HTTPException(500, "Failed to generate upload URL")

    db.commit()

    return PresignResponse(upload_url=upload_url, r2_key=r2_key)


@router.post("", response_model=IngestTaskDetail)
def create_ingest_task(
    body: IngestTaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm upload complete and start parsing.

    Called after the frontend finishes uploading to R2 via the presigned URL.
    """
    # Find existing task by r2_key
    task = (
        db.query(IngestTask)
        .filter(IngestTask.r2_raw_key == body.r2_key)
        .first()
    )

    if task is None:
        raise HTTPException(404, "No matching upload task found for this r2_key")

    if task.status != "uploading":
        raise HTTPException(
            400, f"Task is in '{task.status}' state, expected 'uploading'"
        )

    # Enqueue only — the ingest scheduler (issue #152) picks up queued
    # tasks respecting the global concurrency budget and dispatches
    # _run_sync_and_parse when capacity allows.
    task.status = "queued"
    db.flush()

    AuditService.log(
        db,
        action=AuditService.INGEST,
        resource_type="ingest_task",
        user_id=current_user.id,
        resource_id=str(task.id),
        detail={"file_name": task.file_name, "file_type": task.file_type},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return IngestTaskDetail(**_task_to_detail(task))


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

    return paginate(
        query.order_by(IngestTask.id.desc()),
        page,
        page_size,
        lambda t: IngestTaskListItem(**_task_to_detail(t)),
    )


@router.post("/batch-delete", response_model=BatchDeleteResponse)
def batch_delete_ingest_tasks(
    body: BatchDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete multiple ingest tasks.

    Each task is cleaned inside ``_cleanup_task_data``'s own savepoint, so
    a failure on one task no longer nukes the rest of the batch. Tasks that
    cleanup fails on are reported via the ``failed`` field with a human
    reason; ``skipped`` is reserved for "not found" / "still running".
    """
    deleted: list[UUID] = []
    skipped: list[UUID] = []
    failed: list[BatchDeleteFailure] = []

    for tid in body.task_ids:
        task = db.get(IngestTask, tid)
        if task is None:
            skipped.append(tid)
            continue
        if task.status in RUNNING_STATUSES:
            skipped.append(tid)
            continue

        try:
            _cleanup_task_data(db, task)
        except CleanupError as exc:
            failed.append(BatchDeleteFailure(task_id=tid, reason=str(exc.cause)))
            continue

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
    return BatchDeleteResponse(deleted=deleted, skipped=skipped, failed=failed)


# Parametric routes below literal routes


@router.get("/{task_id}", response_model=IngestTaskDetail)
def get_ingest_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get ingest task detail (used for polling status)."""
    task = db.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    return IngestTaskDetail(**_task_to_detail(task))


@router.post("/{task_id}/confirm", response_model=IngestTaskDetail)
def confirm_ingest_task(
    task_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """User confirms chunks are ready -- enqueue for indexing.

    The actual ``_run_indexing`` dispatch happens in the ingest scheduler
    (issue #152) when capacity allows.
    """
    task = db.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")

    if task.status != "chunked":
        raise HTTPException(
            400, f"Task is in '{task.status}' state, expected 'chunked'"
        )

    task.status = "queued_for_indexing"
    db.flush()

    AuditService.log(
        db,
        action="confirm_ingest",
        resource_type="ingest_task",
        user_id=current_user.id,
        resource_id=str(task.id),
        ip_address=get_client_ip(request),
    )
    db.commit()

    return IngestTaskDetail(**_task_to_detail(task))


@router.get("/{task_id}/download-url", response_model=DownloadUrlResponse)
def get_download_url(
    task_id: UUID,
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


@router.post("/{task_id}/retry", response_model=IngestTaskDetail)
def retry_ingest_task(
    task_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reset a failed/deleted task and re-enqueue the pipeline.

    The cleanup runs inline (savepoint-protected) but the actual
    ``_run_sync_and_parse`` dispatch is handled by the ingest scheduler
    (issue #152) so concurrent retries are serialised through the
    global concurrency budget instead of saturating Zhipu's rate limit.
    """
    task = db.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")

    if task.status not in ("failed", "deleted"):
        raise HTTPException(
            400,
            f"Cannot retry task in '{task.status}' state -- only failed or deleted tasks can be retried",
        )

    try:
        _cleanup_task_data(db, task)
    except CleanupError as exc:
        raise HTTPException(500, str(exc)) from exc

    task.status = "queued"
    task.error_message = None
    task.chunk_count = None
    task.parsed_content = None
    task.image_count = 0
    db.flush()

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

    return IngestTaskDetail(**_task_to_detail(task))


@router.delete("/{task_id}", status_code=204)
def delete_ingest_task(
    task_id: UUID,
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

    try:
        _cleanup_task_data(db, task)
    except CleanupError as exc:
        raise HTTPException(500, str(exc)) from exc

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

    return None
