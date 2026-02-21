"""Ingest tasks API endpoints -- async multi-stage ingest pipeline."""
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas import PaginatedResponse
from app.api.v1.schemas.ingest_task import (
    IngestTaskCreate,
    IngestTaskDetail,
    IngestTaskListItem,
    PresignRequest,
    PresignResponse,
)
from app.core.database import get_db
from app.models import User
from app.models.ingest_task import IngestTask
from app.providers import ZhipuProvider
from app.providers.file_parser import FileParserProvider
from app.services.audit_service import AuditService
from app.services.ingest_task_service import IngestTaskService
from app.services.r2_storage import R2StorageService

router = APIRouter(prefix="/ingest-tasks")

ALLOWED_FILE_TYPES = {"pdf", "md"}


def _get_r2() -> R2StorageService:
    if not R2StorageService.is_configured():
        raise HTTPException(
            status_code=503,
            detail="R2 storage is not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY in .env",
        )
    return R2StorageService()


def _run_sync_and_parse(task_id: int):
    """BackgroundTask entry: run sync_and_parse in a new DB session."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        r2 = R2StorageService()
        provider = ZhipuProvider()
        file_parser = FileParserProvider()
        service = IngestTaskService(db=db, r2=r2, provider=provider, file_parser=file_parser)
        asyncio.run(service.sync_and_parse(task_id))
    finally:
        db.close()


def _run_indexing(task_id: int):
    """BackgroundTask entry: run start_indexing in a new DB session."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        r2 = R2StorageService()
        provider = ZhipuProvider()
        service = IngestTaskService(db=db, r2=r2, provider=provider)
        asyncio.run(service.start_indexing(task_id))
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

    # Create task record first to get an ID for the R2 key
    task = IngestTask(
        status="uploading",
        file_name=body.file_name,
        file_type=body.file_type,
        file_size=body.file_size,
        created_by=current_user.id,
    )
    db.add(task)
    db.flush()

    r2_key = f"raw/{task.id}/{body.file_name}"
    task.r2_raw_key = r2_key
    db.commit()

    upload_url = r2.generate_presigned_upload_url(r2_key, body.content_type)

    return PresignResponse(upload_url=upload_url, r2_key=r2_key)


@router.post("", response_model=IngestTaskDetail)
def create_ingest_task(
    body: IngestTaskCreate,
    background_tasks: BackgroundTasks,
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
        .filter(
            IngestTask.r2_raw_key == body.r2_key,
            IngestTask.created_by == current_user.id,
        )
        .first()
    )

    if task is None:
        raise HTTPException(404, "No matching upload task found for this r2_key")

    if task.status != "uploading":
        raise HTTPException(
            400, f"Task is in '{task.status}' state, expected 'uploading'"
        )

    task.status = "syncing"
    db.commit()

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

    background_tasks.add_task(_run_sync_and_parse, task.id)

    return IngestTaskDetail(**_task_to_detail(task))


@router.get("", response_model=PaginatedResponse[IngestTaskListItem])
def list_ingest_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List ingest tasks for the current user."""
    query = db.query(IngestTask).filter(IngestTask.created_by == current_user.id)

    if status:
        query = query.filter(IngestTask.status == status)

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


# Parametric routes below literal routes


@router.get("/{task_id}", response_model=IngestTaskDetail)
def get_ingest_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get ingest task detail (used for polling status)."""
    task = db.get(IngestTask, task_id)
    if task is None or task.created_by != current_user.id:
        raise HTTPException(404, "Task not found")
    return IngestTaskDetail(**_task_to_detail(task))


@router.post("/{task_id}/confirm", response_model=IngestTaskDetail)
def confirm_ingest_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """User confirms chunks are ready -- start indexing (embedding + tagging)."""
    task = db.get(IngestTask, task_id)
    if task is None or task.created_by != current_user.id:
        raise HTTPException(404, "Task not found")

    if task.status != "chunked":
        raise HTTPException(
            400, f"Task is in '{task.status}' state, expected 'chunked'"
        )

    task.status = "indexing"
    db.commit()

    AuditService.log(
        db,
        action="confirm_ingest",
        resource_type="ingest_task",
        user_id=current_user.id,
        resource_id=str(task.id),
        ip_address=get_client_ip(request),
    )
    db.commit()

    background_tasks.add_task(_run_indexing, task.id)

    return IngestTaskDetail(**_task_to_detail(task))


@router.delete("/{task_id}")
def delete_ingest_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel/delete an ingest task."""
    task = db.get(IngestTask, task_id)
    if task is None or task.created_by != current_user.id:
        raise HTTPException(404, "Task not found")

    if task.status in ("syncing", "parsing", "indexing"):
        raise HTTPException(
            400,
            f"Cannot delete task in '{task.status}' state -- wait for completion or failure",
        )

    # Capture R2 keys before deleting the task
    r2_raw_key = task.r2_raw_key
    r2_parsed_prefix = task.r2_parsed_prefix
    task_id_for_cleanup = task.id

    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="ingest_task",
        user_id=current_user.id,
        resource_id=str(task.id),
        detail={"file_name": task.file_name},
        ip_address=get_client_ip(request),
    )
    db.delete(task)
    db.commit()

    # Clean up R2 files (best-effort, after commit)
    try:
        if R2StorageService.is_configured():
            r2 = R2StorageService()
            if r2_raw_key:
                r2.delete_prefix(f"raw/{task_id_for_cleanup}/")
            if r2_parsed_prefix:
                r2.delete_prefix(r2_parsed_prefix)
    except Exception:
        pass  # R2 cleanup is best-effort

    return {"ok": True}
