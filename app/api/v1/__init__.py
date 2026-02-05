"""V1 API routes."""
from fastapi import APIRouter

from app.api.v1.ask import router as ask_router

router = APIRouter()
router.include_router(ask_router)

__all__ = ["router"]
