"""Public recognition schemas."""
from typing import Literal

from pydantic import BaseModel


class RecognitionCandidate(BaseModel):
    bridge_id: str
    name: str
    bridge_type: str
    era: str
    region: str
    thumbnail: str | None
    confidence_hints: list[str]


class RecognitionFallback(BaseModel):
    search_hint: str | None
    region_hint: str | None


class RecognitionData(BaseModel):
    candidates: list[RecognitionCandidate]
    fallback_suggestions: RecognitionFallback | None = None


class RecognitionMeta(BaseModel):
    model: str
    latency_ms: int
    branch: Literal["exact", "fuzzy", "fallback"]
