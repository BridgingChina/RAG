"""Mobile API v1 routes."""
from fastapi import APIRouter

from app.api.mobile.v1 import bridges, config, knowledge

router = APIRouter()
router.include_router(config.router)
router.include_router(bridges.router, prefix="/bridges")
router.include_router(knowledge.router, prefix="/knowledge")

__all__ = ["router"]
