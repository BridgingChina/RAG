"""V1 API routes."""

from fastapi import APIRouter, Depends

from app.api.v1.auth import router as auth_router
from app.api.v1.audit import router as audit_router
from app.api.v1.ask import router as ask_router
from app.api.v1.bridges import router as bridges_router
from app.api.v1.chunks import router as chunks_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.sources import router as sources_router
from app.api.v1.stats import router as stats_router
from app.api.v1.system import router as system_router
from app.api.v1.taxonomy import router as taxonomy_router
from app.api.v1.ingest_tasks import router as ingest_tasks_router
from app.api.v1.dependencies import get_current_user

router = APIRouter()

# Public routes (no auth required)
router.include_router(auth_router)

# Protected routes (auth required)
protected = APIRouter(dependencies=[Depends(get_current_user)])
protected.include_router(audit_router)
protected.include_router(ask_router)
protected.include_router(bridges_router)
protected.include_router(chunks_router)
protected.include_router(ingest_router)
protected.include_router(ingest_tasks_router)
protected.include_router(sources_router)
protected.include_router(stats_router)
protected.include_router(system_router)
protected.include_router(taxonomy_router)

router.include_router(protected)

__all__ = ["router"]
