"""Mobile bridge schemas."""
from uuid import UUID

from pydantic import BaseModel


class MobileBridgeListItem(BaseModel):
    id: UUID
    name: str
    aliases: str | None
    bridge_type: str | None
    era: str | None
    region: str | None
    latitude: float | None
    longitude: float | None
    thumbnail: str | None = None
    distance: float | None = None


class BridgeSectionLevel(BaseModel):
    l0: list[dict] = []
    l1: list[dict] = []


class BridgeSections(BaseModel):
    structure: BridgeSectionLevel = BridgeSectionLevel()
    geography: BridgeSectionLevel = BridgeSectionLevel()
    society: BridgeSectionLevel = BridgeSectionLevel()
    history: BridgeSectionLevel = BridgeSectionLevel()


class MobileBridgeDetail(BaseModel):
    id: UUID
    name: str
    aliases: str | None
    bridge_type: str | None
    era: str | None
    region: str | None
    latitude: float | None
    longitude: float | None
    tags: list[str] = []
    images: list[dict] = []
    sections: BridgeSections = BridgeSections()
    related_knowledge_points: list[dict] = []
    sources: list[dict] = []
    sources_count: int = 0
