from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.database import init_database
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan event handler for startup/shutdown tasks."""
    # Startup: Initialize database
    logger.info("Starting application...")
    try:
        init_database()
        logger.info("Database initialization complete")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    yield

    # Shutdown (if needed in future)
    logger.info("Shutting down application...")


app = FastAPI(title="Bridge RAG", version="1.0.0", lifespan=lifespan)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 routes
app.include_router(v1_router, prefix="/api/v1", tags=["v1"])


@app.get("/health")
async def health():
    """Health check endpoint for load balancers."""
    return {"status": "ok"}
