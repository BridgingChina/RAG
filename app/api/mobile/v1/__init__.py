"""Mobile API v1 routes."""
from fastapi import APIRouter

from app.api.mobile.v1 import bridges, config

router = APIRouter()
router.include_router(config.router)
router.include_router(bridges.router, prefix="/bridges")

__all__ = ["router"]
