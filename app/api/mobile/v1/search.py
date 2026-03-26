"""Mobile API: Unified search endpoint.

TODO (Batch 2 #14): Implement bridge + knowledge_point search with category filter.
"""
from fastapi import APIRouter, Query

from app.api.mobile.v1.schemas.common import MobileMeta, MobilePaginatedResponse

router = APIRouter()


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    type: str = "all",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> MobilePaginatedResponse[dict]:
    """Unified search across bridges and knowledge points.

    TODO (Batch 2 #14): Implement actual search logic.
    """
    return MobilePaginatedResponse(
        data={"results": [], "suggestions": []},
        meta=MobileMeta(total=0, page=page, page_size=page_size),
    )
