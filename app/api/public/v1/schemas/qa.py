"""Public QA schemas."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class QAContext(BaseModel):
    type: Literal["bridge", "knowledge_point", "search", "map"] | None = None
    id: UUID | None = None
    filters: dict | None = None


class QARequest(BaseModel):
    question: str = Field(min_length=1)
    context: QAContext | None = None
