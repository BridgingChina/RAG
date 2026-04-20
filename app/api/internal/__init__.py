"""Internal API surface — called by the auth Worker, NOT public clients.

Mounted under ``/internal/*`` and guarded by ``X-Internal-Token`` (shared
secret injected via the ``INTERNAL_API_SECRET`` env var). Routes here never
accept a user-facing JWT.
"""
from fastapi import APIRouter

from app.api.internal.purge import router as purge_router

router = APIRouter()
router.include_router(purge_router)

__all__ = ["router"]
