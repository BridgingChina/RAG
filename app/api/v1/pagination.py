"""Pagination helper to eliminate boilerplate in list endpoints."""
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Query

from app.api.v1.schemas.common import PaginatedResponse

T = TypeVar("T")


def paginate(
    query: Query,
    page: int,
    page_size: int,
    item_mapper: Callable | None = None,
) -> PaginatedResponse:
    """Apply pagination to a SQLAlchemy query and return a PaginatedResponse.

    The caller must apply ``order_by`` to the query before calling this function.

    Args:
        query: SQLAlchemy query with filters and order_by already applied.
        page: 1-based page number.
        page_size: Number of items per page.
        item_mapper: Optional callable to transform each row into a response
            schema instance. If None, rows are used as-is.

    Returns:
        PaginatedResponse with items, total, page, page_size, total_pages.
    """
    total = query.count()
    offset = (page - 1) * page_size
    results = query.offset(offset).limit(page_size).all()

    items = [item_mapper(row) for row in results] if item_mapper else results

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
