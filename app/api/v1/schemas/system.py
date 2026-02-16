"""System status schemas."""
from pydantic import BaseModel


class SystemStatus(BaseModel):
    """Read-only system status and configuration."""
    version: str
    python_version: str
    db_connected: bool
    db_version: str | None = None
    schema_version: int | None = None
    vector_dimension: int
    index_type: str
    llm_provider: str
    embedding_model: str
    chat_model: str
    chunk_quota: dict
    rrf_k: int
    api_key_configured: bool
