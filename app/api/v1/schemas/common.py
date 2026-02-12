"""Common schemas for pagination and shared types."""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar('T')


class PageParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
