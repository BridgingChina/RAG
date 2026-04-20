import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1 import router as v1_router
from app.core.config import settings
from app.core.database import init_database
from app.core.logging import logger
from app.core.rate_limit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan event handler for startup/shutdown tasks."""
    # Startup: Initialize database
    logger.info("Starting application...")

    # Phase 2 production sanity: auth Worker URL must be set unless running
    # in dev (where unit tests accept the default). The JWT verifier will
    # fail closed if auth_jwks_url can't be fetched, but an earlier fast-fail
    # is friendlier to ops.
    if settings.auth_jwks_url.startswith("https://auth.bridgingchina.net"):
        if os.getenv("ENV") == "production" and not settings.internal_api_secret:
            logger.warning(
                "INTERNAL_API_SECRET is empty — /internal/* endpoints will "
                "refuse every request. Set it before routing the auth "
                "Worker webhook here."
            )

    try:
        init_database()
        logger.info("Database initialization complete")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    import asyncio as _asyncio
    from app.services.ingest_scheduler import ingest_scheduler_loop
    from app.services.reconcile_orphans import reconcile_orphans_loop
    from app.services.reindex_cron import reindex_cron_loop, uploading_cleanup_loop
    _asyncio.get_event_loop().create_task(reindex_cron_loop())
    _asyncio.get_event_loop().create_task(uploading_cleanup_loop())
    _asyncio.get_event_loop().create_task(reconcile_orphans_loop())

    # Scheduler loop: wire a done-callback so a silent coroutine death
    # surfaces as a CRITICAL log (instead of the entire ingest pipeline
    # stalling unnoticed — see PR #153 silent-failure review C3).
    scheduler_task = _asyncio.get_event_loop().create_task(ingest_scheduler_loop())

    def _on_scheduler_done(t: _asyncio.Task) -> None:
        if t.cancelled():
            logger.info("Ingest scheduler cancelled (shutdown)")
            return
        exc = t.exception()
        logger.critical(
            "INGEST SCHEDULER LOOP DIED -- queued tasks will NOT be dispatched "
            "until the process restarts. Investigate immediately.",
            exc_info=exc,
        )

    scheduler_task.add_done_callback(_on_scheduler_done)

    logger.info("Reindex cron task scheduled")
    logger.info("Uploading cleanup task scheduled")
    logger.info("Ingest scheduler task scheduled")
    logger.info("Reconcile orphans task scheduled")

    yield

    # Shutdown (if needed in future)
    logger.info("Shutting down application...")


app = FastAPI(title="Bridge RAG", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from app.api.public.v1.error_handlers import register_public_error_handlers
register_public_error_handlers(app)

# Public cache middleware (must be added before CORS so it runs after CORS in the response chain)
from app.core.cache_middleware import PublicCacheMiddleware
app.add_middleware(PublicCacheMiddleware)

# Locale middleware — resolves request.state.locale for C-end /v1/* requests
# (i18n Phase 3). Admin / internal / health default to zh-CN.
from app.core.locale_middleware import LocaleMiddleware
app.add_middleware(LocaleMiddleware)

# CORS middleware — explicit list (settings.cors_origins) + regex for prod web domains
# regex matches: bridgingchina.net (+ any subdomain) and bridge-web.user-unauthorized.workers.dev (+ any subdomain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https://([a-z0-9-]+\.)?bridgingchina\.net$|^https://([a-z0-9-]+\.)?bridge-web\.user-unauthorized\.workers\.dev$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 routes
app.include_router(v1_router, prefix="/api/v1", tags=["v1"])

# Public API routes (no auth required for anonymous reads; per-user endpoints
# require a JWT via require_user)
from app.api.public import router as public_router
app.include_router(public_router, prefix="/v1", tags=["public"])

# Internal API routes (auth Worker webhook calls; X-Internal-Token gated)
from app.api.internal import router as internal_router
app.include_router(internal_router, prefix="/internal", tags=["internal"])


@app.get("/health")
@limiter.exempt
async def health():
    """Health check endpoint for load balancers."""
    return {"status": "ok"}
