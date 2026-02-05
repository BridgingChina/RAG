"""V1 API routes."""
from fastapi import APIRouter

from app.api.v1.ask import router as ask_router
from app.api.v1.ingest import router as ingest_router

router = APIRouter()
router.include_router(ask_router)
router.include_router(ingest_router)

__all__ = ["router"]
