"""Mobile search schemas."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    type: Literal["bridge", "knowledge_point"]
    id: UUID
    name: str
    aliases: str | None
    highlight: str
    bridge_type: str | None = None
    era: str | None = None
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    line: str | None = None
    thumbnail: str | None = None
