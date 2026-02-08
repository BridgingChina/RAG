from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router

app = FastAPI(title="Bridge RAG", version="1.0.0")

# CORS middleware for WebUI development
# WARNING: This configuration is for local development only.
# For production, use environment variables and restrict methods/headers.
# See web/SECURITY.md for deployment guidelines.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # TODO: Use env var for production
    allow_methods=["*"],  # TODO: Restrict to ["GET", "POST"] in production
    allow_headers=["*"],  # TODO: Restrict headers in production
)

# API v1 routes
app.include_router(v1_router, prefix="/api/v1", tags=["v1"])


@app.get("/health")
async def health():
    """Health check endpoint for load balancers."""
    return {"status": "ok"}
