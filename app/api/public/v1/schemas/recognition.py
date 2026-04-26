"""Public recognition schemas."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class RecognitionCandidate(BaseModel):
    bridge_id: UUID
    name: str
    bridge_type: str
    era: str
    region: str
    thumbnail: str | None = None
    confidence_hints: list[str]


class RecognitionFallback(BaseModel):
    search_hint: str | None = None
    region_hint: str | None = None


class RecognitionData(BaseModel):
    candidates: list[RecognitionCandidate]
    fallback_suggestions: RecognitionFallback | None = None


class RecognitionMeta(BaseModel):
    model: str
    latency_ms: int
    branch: Literal["exact", "fuzzy", "fallback"]
