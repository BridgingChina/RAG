"""Pydantic schemas for the admin translation审校 API (i18n Phase 3)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TranslationReviewItem(BaseModel):
    """Single translation review row rendered for the审校 UI."""
    id: UUID
    table_name: str
    row_id: UUID
    field_name: str
    source_text: str
    ai_translation: str | None
    reviewed_translation: str | None
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime


class GenerateSingleRequest(BaseModel):
    """Body for POST /api/v1/translations/generate."""
    table_name: str = Field(..., min_length=1, max_length=50)
    row_id: UUID
    field_name: str = Field(..., min_length=1, max_length=50)


class BatchGenerateRequest(BaseModel):
    """Body for POST /api/v1/translations/batch-generate."""
    table_name: str = Field(..., min_length=1, max_length=50)
    field_name: str = Field(..., min_length=1, max_length=50)
    limit: int = Field(default=100, ge=1, le=500)


class BatchGenerateResponse(BaseModel):
    started: int
    already_queued: int
    total_pending: int


class ReviewActionRequest(BaseModel):
    """Body for PUT /api/v1/translations/{id}/review."""
    action: Literal["approve", "edit", "reject"]
    text: str | None = None


class CoverageRow(BaseModel):
    table: str
    field: str
    total: int
    translated: int
    pct: float


class CoverageResponse(BaseModel):
    tables: list[CoverageRow]
