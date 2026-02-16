"""V1 API routes."""
from fastapi import APIRouter

from app.api.v1.ask import router as ask_router
from app.api.v1.bridges import router as bridges_router
from app.api.v1.chunks import router as chunks_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.stats import router as stats_router

router = APIRouter()
router.include_router(ask_router)
router.include_router(ingest_router)
router.include_router(stats_router)
router.include_router(chunks_router)
router.include_router(bridges_router)

__all__ = ["router"]
