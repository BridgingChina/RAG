"""System status schemas."""
from pydantic import BaseModel


class SystemStatus(BaseModel):
    """Read-only system status and configuration."""
    version: str
    git_commit: str = "dev"
    git_date: str = ""
    python_version: str
    db_connected: bool
    schema_version: int | None = None
    vector_dimension: int
    index_type: str
    llm_provider: str
    embedding_model: str
    chat_model: str
    chunk_quota: dict
    rrf_k: int
    api_key_configured: bool


class FacetsResponse(BaseModel):
    """Facet enums sourced from config/facets.yaml.

    Keys mirror the YAML file exactly (plural). Strong typing here so a
    rename on either side trips typecheck instead of silently returning [].
    """
    bridge_types: list[str]
    materials: list[str]
    eras: list[str]
    regions: list[str]
    functions: list[str]
