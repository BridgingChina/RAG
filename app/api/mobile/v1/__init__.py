"""Mobile API v1 routes."""
from fastapi import APIRouter

from app.api.mobile.v1 import bridges, config, knowledge, search

router = APIRouter()
router.include_router(config.router)
router.include_router(bridges.router, prefix="/bridges")
router.include_router(knowledge.router, prefix="/knowledge")
router.include_router(search.router)

__all__ = ["router"]
