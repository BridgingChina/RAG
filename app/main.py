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
    if settings.secret_key == "change-me-in-production":
        if os.getenv("ENV") != "development":
            raise RuntimeError(
                "SECRET_KEY must be set before starting in production"
            )
        logger.warning(
            "SECRET_KEY is using the default value! "
            "Set SECRET_KEY in .env for production use."
        )

    try:
        init_database()
        logger.info("Database initialization complete")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    import asyncio as _asyncio
    from app.services.reindex_cron import reindex_cron_loop, uploading_cleanup_loop
    _asyncio.get_event_loop().create_task(reindex_cron_loop())
    _asyncio.get_event_loop().create_task(uploading_cleanup_loop())
    logger.info("Reindex cron task scheduled")
    logger.info("Uploading cleanup task scheduled")

    yield

    # Shutdown (if needed in future)
    logger.info("Shutting down application...")


app = FastAPI(title="Bridge RAG", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from app.api.mobile.v1.error_handlers import register_mobile_error_handlers
register_mobile_error_handlers(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 routes
app.include_router(v1_router, prefix="/api/v1", tags=["v1"])

# Mobile API routes (no auth required)
from app.api.mobile import router as mobile_router
app.include_router(mobile_router, prefix="/api/mobile/v1", tags=["mobile"])


@app.get("/health")
@limiter.exempt
async def health():
    """Health check endpoint for load balancers."""
    return {"status": "ok"}
