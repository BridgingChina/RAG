"""Mobile API v1 routes."""
from fastapi import APIRouter

from app.api.mobile.v1 import config

router = APIRouter()
router.include_router(config.router)

__all__ = ["router"]
