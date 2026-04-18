"""Common public API schemas."""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, computed_field

T = TypeVar("T")


class PublicResponse(BaseModel, Generic[T]):
    """Wrapper for single-object responses."""
    data: T


class PublicMeta(BaseModel):
    """Pagination metadata for public API."""
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total


class PublicPaginatedResponse(BaseModel, Generic[T]):
    """Wrapper for paginated responses."""
    data: T
    meta: PublicMeta
