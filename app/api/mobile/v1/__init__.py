"""Mobile API v1 routes."""
from fastapi import APIRouter

from app.api.mobile.v1 import bridges, config, favorites, history, knowledge, qa, review, search

router = APIRouter()
router.include_router(config.router)
router.include_router(bridges.router, prefix="/bridges")
router.include_router(favorites.router, prefix="/favorites")
router.include_router(history.router, prefix="/history")
router.include_router(knowledge.router, prefix="/knowledge")
router.include_router(qa.router, prefix="/qa")
router.include_router(review.router, prefix="/review")
router.include_router(search.router)

__all__ = ["router"]
