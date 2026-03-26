"""Common mobile API schemas."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class MobileResponse(BaseModel, Generic[T]):
    """Wrapper for single-object responses."""
    data: T


class MobileMeta(BaseModel):
    """Pagination metadata for mobile API."""
    total: int
    page: int
    page_size: int
    has_more: bool


class MobilePaginatedResponse(BaseModel, Generic[T]):
    """Wrapper for paginated responses."""
    data: T
    meta: MobileMeta
