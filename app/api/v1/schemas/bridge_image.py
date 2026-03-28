"""Bridge image schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ImagePresignRequest(BaseModel):
    file_name: str
    content_type: str = "image/jpeg"


class ImagePresignResponse(BaseModel):
    image_id: UUID
    upload_url: str
    r2_key: str


class ImageConfirmRequest(BaseModel):
    image_id: UUID
    caption: str | None = None
    type: str | None = None  # photo / illustration / map


class ImageReorderRequest(BaseModel):
    image_ids: list[UUID]


class BridgeImageResponse(BaseModel):
    id: UUID
    bridge_id: UUID
    url: str  # public URL or presigned GET
    caption: str | None
    type: str | None
    order_index: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
