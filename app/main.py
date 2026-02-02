from fastapi import FastAPI

from app.api import ask_router

app = FastAPI(title="Bridge RAG", version="0.1.0")

app.include_router(ask_router, tags=["ask"])


@app.get("/health")
async def health():
    return {"status": "ok"}
