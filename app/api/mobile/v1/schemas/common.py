"""Common mobile API schemas."""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, computed_field

T = TypeVar("T")


class MobileResponse(BaseModel, Generic[T]):
    """Wrapper for single-object responses."""
    data: T


class MobileMeta(BaseModel):
    """Pagination metadata for mobile API."""
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total


class MobilePaginatedResponse(BaseModel, Generic[T]):
    """Wrapper for paginated responses."""
    data: T
    meta: MobileMeta
