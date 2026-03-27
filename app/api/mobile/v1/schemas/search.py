"""Mobile search schemas."""
from uuid import UUID
from pydantic import BaseModel


class SearchResultItem(BaseModel):
    type: str
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
