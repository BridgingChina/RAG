"""Bridge image schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ImageType = Literal["photo", "illustration", "map"]


class ImagePresignRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="image/jpeg", pattern=r"^image/(jpeg|png|webp|gif|svg\+xml)$")


class ImagePresignResponse(BaseModel):
    image_id: UUID
    upload_url: str
    r2_key: str


class ImageConfirmRequest(BaseModel):
    image_id: UUID
    caption: str | None = None
    type: ImageType | None = None


class ImageReorderRequest(BaseModel):
    image_ids: list[UUID] = Field(min_length=1)


class BridgeImageResponse(BaseModel):
    id: UUID
    bridge_id: UUID
    url: str  # public URL or presigned GET
    caption: str | None
    type: ImageType | None
    order_index: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
