from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+psycopg://bridge:bridge@localhost:5433/bridge_rag"
    zhipu_api_key: str = ""
    amap_api_key: str = ""

    # LLM settings
    embedding_model: str = "embedding-3"
    chat_model: str = "glm-4.7"
    use_coding_plan: bool = False
    # httpx read timeout (seconds) for chat completions. glm-4.7 with long
    # tagging/enrichment prompts can take well over 60s; the previous
    # hard-coded 60s was the dominant retry-budget killer.
    chat_read_timeout: float = 180.0
    # httpx read timeout (seconds) for embeddings (typically fast).
    embed_read_timeout: float = 60.0

    # Ingest scheduler (issue #152)
    # Max number of ingest tasks allowed in RUNNING_STATUSES at once.
    # Default 2 keeps Zhipu burst 429s at bay even when user enqueues
    # many retries at once.
    ingest_max_concurrent: int = 2
    # How often the scheduler polls the queue for work to dispatch.
    ingest_scheduler_interval_seconds: float = 5.0
    # Max runtime for a single ingest task before the stale cleanup
    # helper marks it failed. 60 min = 2x the observed real-world p95
    # (程阳永济桥 took 32.8 min to completion).
    ingest_stale_running_minutes: int = 60

    # Retrieval settings
    top_k: int = 5

    # Auth settings
    secret_key: str = "change-me-in-production"
    access_token_expire_hours: int = 4

    # R2 storage settings
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "bridge-rag"
    r2_public_url: str = ""  # optional, for public access

    # Zhipu file parser settings
    zhipu_parser_tool_type: str = "expert"  # lite / expert / prime

    # CORS settings
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Build info (injected via Docker build args)
    git_commit: str = "dev"
    git_date: str = ""


settings = Settings()
