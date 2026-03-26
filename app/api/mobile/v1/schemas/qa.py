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
