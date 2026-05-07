"""Admin API for i18n translation审校 (Phase 3, Task Group 3.D).

Mounted under ``/api/v1/translations`` and protected by
``get_current_user`` (admin-only) via the v1 router. See
``docs/plans/2026-04-20-i18n-phase3-db-review.md`` §3.D for the original
endpoint contract; the inline-审校 redesign
(``docs/plans/2026-05-08-inline-translation-review-design.md``) added
``/by-row`` for batched per-business-row reads.

Endpoints:

* ``GET  /translations``                 — list审校 rows with filters + pagination
* ``GET  /translations/by-row``          — all reviews for one or more rows
                                           (powers inline TranslationCell)
* ``POST /translations/generate``        — AI translate a single row/field
* ``POST /translations/batch-generate``  — batch AI translate pending rows
* ``PUT  /translations/{id}/review``     — approve / edit / reject one review
* ``GET  /translations/coverage``        — per-(table,field) translation coverage

The backing service is :mod:`app.services.translation_service`; this module
stays thin and focuses on HTTP concerns.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.pagination import paginate
from app.api.v1.schemas.common import PaginatedResponse
from app.api.v1.schemas.translation import (
    BatchGenerateRequest,
    BatchGenerateResponse,
    CoverageResponse,
    CoverageRow,
    GenerateSingleRequest,
    ReviewActionRequest,
    TranslationReviewItem,
)
from app.core.database import get_db
from app.models.translation_review import (
    TRANSLATION_STATUS_HUMAN_REVIEWED,
    TRANSLATION_STATUS_PENDING_AI,
    VALID_TRANSLATION_STATUSES,
    TranslationReview,
)
from app.services.audit_service import AuditService
from app.services.translation_service import (
    TRANSLATABLE_FIELDS,
    approve_review,
    batch_generate_for_field,
    generate_for_row,
    reject_review,
)
from app.models.current_user import CurrentUser
from app.api.v1.dependencies import get_current_user
from app.models import (
    Bridge,
    Flashcard,
    KnowledgePoint,
    KnowledgePointKeyPoint,
    TaxonomyNode,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/translations", tags=["translations"])


_MODEL_BY_TABLE = {
    "bridges": Bridge,
    "knowledge_points": KnowledgePoint,
    "flashcards": Flashcard,
    "taxonomy_nodes": TaxonomyNode,
    "knowledge_point_key_points": KnowledgePointKeyPoint,
}


def _validate_table_field(table_name: str, field_name: str) -> None:
    fields = TRANSLATABLE_FIELDS.get(table_name)
    if fields is None:
        raise HTTPException(400, detail=f"Unknown translatable table: {table_name}")
    if field_name not in {target for _src, target in fields}:
        raise HTTPException(
            400, detail=f"{field_name} is not a translatable field of {table_name}"
        )


def _to_item(row: TranslationReview) -> TranslationReviewItem:
    return TranslationReviewItem(
        id=row.id,
        table_name=row.table_name,
        row_id=row.row_id,
        field_name=row.field_name,
        source_text=row.source_text,
        ai_translation=row.ai_translation,
        reviewed_translation=row.reviewed_translation,
        status=row.status,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
    )


@router.get("", response_model=PaginatedResponse[TranslationReviewItem])
def list_translations(
    status: str | None = None,
    table: str | None = None,
    field: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[TranslationReviewItem]:
    """List审校 rows with filters."""
    if status is not None and status not in VALID_TRANSLATION_STATUSES:
        raise HTTPException(400, detail=f"Invalid status: {status}")

    query = db.query(TranslationReview)
    if status is not None:
        query = query.filter(TranslationReview.status == status)
    if table is not None:
        query = query.filter(TranslationReview.table_name == table)
    if field is not None:
        query = query.filter(TranslationReview.field_name == field)
    query = query.order_by(TranslationReview.created_at.desc())
    return paginate(query, page, size, _to_item)


@router.get("/by-row", response_model=list[TranslationReviewItem])
def list_by_row(
    table: str = Query(..., min_length=1),
    row_id: str = Query(
        ...,
        description="A single UUID, or a comma-separated list of UUIDs (max 50)",
    ),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[TranslationReviewItem]:
    """Return all translation_reviews rows for one or more business rows.

    Powers the inline ``<TranslationCell>`` UX: a Bridge / KP detail page
    fetches every review for its rows in one shot rather than N separate
    requests. Also auto-upserts a synthetic ``human_reviewed`` review for
    each business row whose ``*_en`` column is already populated but lacks
    a review record (legacy data, pre-审校-table). The synthetic record is
    persisted (not just ephemeral) under the ``(table, row, field)`` unique
    constraint so subsequent calls don't repeat the work; ``reviewed_by``
    is set to ``"legacy"`` so audit trails can distinguish.

    See docs/plans/2026-05-08-inline-translation-review-design.md §6.1.
    """
    if table not in _MODEL_BY_TABLE:
        raise HTTPException(400, detail=f"Unknown translatable table: {table}")

    try:
        ids = [UUID(s.strip()) for s in row_id.split(",") if s.strip()]
    except ValueError:
        raise HTTPException(400, detail="Invalid row_id — expected UUID(s)")
    if not ids or len(ids) > 50:
        raise HTTPException(400, detail="row_id must be 1..50 UUIDs")

    existing = (
        db.query(TranslationReview)
        .filter(
            TranslationReview.table_name == table,
            TranslationReview.row_id.in_(ids),
        )
        .all()
    )
    by_key: set[tuple[UUID, str]] = {(r.row_id, r.field_name) for r in existing}

    # Legacy upsert: any (row, *_en) where the business row's *_en column is
    # populated but no translation_review row exists → create a virtual
    # human_reviewed record so the UI renders 🟢 instead of 🔴.
    model_cls = _MODEL_BY_TABLE[table]
    field_pairs = TRANSLATABLE_FIELDS[table]
    business_rows = db.query(model_cls).filter(model_cls.id.in_(ids)).all()

    upserted_any = False
    for biz in business_rows:
        for source_field, target_field in field_pairs:
            if (biz.id, target_field) in by_key:
                continue
            target_value = getattr(biz, target_field, None)
            if not target_value:
                continue  # truly pending — leave for the client to render 🔴
            db.add(TranslationReview(
                table_name=table,
                row_id=biz.id,
                field_name=target_field,
                source_text=getattr(biz, source_field, None) or "",
                ai_translation=None,
                reviewed_translation=target_value,
                status=TRANSLATION_STATUS_HUMAN_REVIEWED,
                reviewed_by="legacy",
                reviewed_at=datetime.now(timezone.utc),
            ))
            upserted_any = True

    if upserted_any:
        try:
            db.commit()
        except IntegrityError:
            # Another request raced us — roll back and re-read; the existing
            # row will satisfy the read path either way.
            db.rollback()

    rows = (
        db.query(TranslationReview)
        .filter(
            TranslationReview.table_name == table,
            TranslationReview.row_id.in_(ids),
        )
        .order_by(TranslationReview.field_name)
        .all()
    )
    return [_to_item(r) for r in rows]


@router.post("/generate", response_model=TranslationReviewItem)
async def generate_single(
    body: GenerateSingleRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TranslationReviewItem:
    """AI translate a single (table, row_id, field) triple."""
    _validate_table_field(body.table_name, body.field_name)

    model_cls = _MODEL_BY_TABLE[body.table_name]
    row = db.query(model_cls).filter(model_cls.id == body.row_id).one_or_none()
    if row is None:
        raise HTTPException(
            404, detail=f"{body.table_name} row {body.row_id} not found"
        )

    # Resolve the Chinese source column for this _en target.
    source_field = None
    for src, tgt in TRANSLATABLE_FIELDS[body.table_name]:
        if tgt == body.field_name:
            source_field = src
            break
    if source_field is None:
        raise HTTPException(400, detail="No source field mapping")

    source_text = getattr(row, source_field, None)
    if not source_text:
        raise HTTPException(
            400,
            detail=f"{body.table_name}.{source_field} is empty — nothing to translate",
        )

    review = await generate_for_row(
        db,
        table_name=body.table_name,
        row_id=body.row_id,
        field_name=body.field_name,
        source_text=source_text,
    )
    AuditService.log(
        db,
        action="translate_generate",
        resource_type="translation_review",
        resource_id=str(review.id),
        user_id=current_user.id,
        detail={
            "table": body.table_name,
            "field": body.field_name,
            "row_id": str(body.row_id),
            "status": review.status,
        },
    )
    db.commit()
    return _to_item(review)


@router.post("/batch-generate", response_model=BatchGenerateResponse)
async def batch_generate(
    body: BatchGenerateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> BatchGenerateResponse:
    """Kick off AI translation for up to ``limit`` pending rows in one (table,
    field) pair. Uses an advisory lock to serialise with another concurrent
    batch run — see ``translation_service.batch_generate_for_field``.
    """
    _validate_table_field(body.table_name, body.field_name)
    stats = await batch_generate_for_field(
        db,
        table_name=body.table_name,
        field_name=body.field_name,
        limit=body.limit,
    )
    AuditService.log(
        db,
        action="translate_batch_generate",
        resource_type="translation_review",
        user_id=current_user.id,
        detail={
            "table": body.table_name,
            "field": body.field_name,
            **stats,
        },
    )
    db.commit()
    return BatchGenerateResponse(**stats)


@router.put("/{review_id}/review", response_model=TranslationReviewItem)
async def review_translation(
    review_id: UUID,
    body: ReviewActionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TranslationReviewItem:
    """Approve / edit / reject a translation review.

    - ``approve``: ``reviewed_translation = ai_translation``, status
      ``human_reviewed``, writes to business table.
    - ``edit``:    ``reviewed_translation = body.text``, status
      ``human_reviewed``, writes to business table.
    - ``reject``:  status ``rejected``, no write to business table.
    """
    review = db.query(TranslationReview).filter(
        TranslationReview.id == review_id
    ).one_or_none()
    if review is None:
        raise HTTPException(404, detail="Review not found")

    try:
        if body.action == "approve":
            result = await approve_review(
                db,
                review_id=review_id,
                reviewer_id=current_user.id,
            )
        elif body.action == "edit":
            if not body.text:
                raise HTTPException(400, detail="edit action requires `text`")
            result = await approve_review(
                db,
                review_id=review_id,
                reviewer_id=current_user.id,
                reviewed_translation=body.text,
            )
        elif body.action == "reject":
            result = reject_review(
                db, review_id=review_id, reviewer_id=current_user.id,
            )
        else:  # pragma: no cover — Literal already validated by pydantic
            raise HTTPException(400, detail=f"Unknown action: {body.action}")
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    AuditService.log(
        db,
        action=f"translate_{body.action}",
        resource_type="translation_review",
        resource_id=str(review_id),
        user_id=current_user.id,
        detail={
            "table": result.table_name,
            "field": result.field_name,
            "row_id": str(result.row_id),
            "status": result.status,
        },
    )
    db.commit()
    return _to_item(result)


@router.get("/coverage", response_model=CoverageResponse)
def coverage(db: Session = Depends(get_db)) -> CoverageResponse:
    """Translation coverage per (table, field).

    For each entry in :data:`TRANSLATABLE_FIELDS`, return how many business rows
    have the target ``_en`` column populated.
    """
    rows: list[CoverageRow] = []
    for table_name, fields in TRANSLATABLE_FIELDS.items():
        model_cls = _MODEL_BY_TABLE[table_name]
        for source_field, target_field in fields:
            source_col = getattr(model_cls, source_field)
            target_col = getattr(model_cls, target_field)
            total = db.query(func.count()).select_from(model_cls).filter(
                source_col.isnot(None)
            ).scalar() or 0
            translated = db.query(func.count()).select_from(model_cls).filter(
                target_col.isnot(None)
            ).scalar() or 0
            pct = (translated / total * 100.0) if total else 0.0
            rows.append(CoverageRow(
                table=table_name,
                field=target_field,
                total=int(total),
                translated=int(translated),
                pct=round(pct, 2),
            ))
    return CoverageResponse(tables=rows)
