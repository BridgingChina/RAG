from fastapi import FastAPI

from app.api.v1 import router as v1_router

app = FastAPI(title="Bridge RAG", version="1.0.0")

# API v1 routes
app.include_router(v1_router, prefix="/api/v1", tags=["v1"])


@app.get("/health")
async def health():
    """Health check endpoint for load balancers."""
    return {"status": "ok"}
