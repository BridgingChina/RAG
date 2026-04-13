from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+psycopg://bridge:bridge@localhost:5433/bridge_rag"
    zhipu_api_key: str = ""
    amap_api_key: str = ""

    # LLM settings
    embedding_model: str = "embedding-3"
    chat_model: str = "glm-4.7"
    # Faster model for latency-sensitive QA (facet extraction + generation).
    # glm-4-flash: ~4s vs glm-4.7: ~20s per call.
    qa_chat_model: str = "glm-4-flash"
    use_coding_plan: bool = False
    # httpx read timeout (seconds) for chat completions. glm-4.7 with long
    # tagging/enrichment prompts can take well over 60s; the previous
    # hard-coded 60s was the dominant retry-budget killer.
    chat_read_timeout: float = 180.0
    # httpx read timeout (seconds) for embeddings (typically fast).
    embed_read_timeout: float = 60.0

    # Ingest scheduler (issue #152)
    # Max number of ingest tasks allowed in RUNNING_STATUSES at once.
    # Default 1 — production observation (2026-04-11 20:00-20:35) showed
    # that MAX_CONCURRENT=2 lets two tasks retry simultaneously against the
    # SAME Zhipu rate-limit cooldown window, compounding the problem instead
    # of serialising it. A single task doing ~30 sequential LLM calls is
    # also sustainable within Zhipu's per-second limits (verified by
    # 程阳永济桥.md completing in ~33 min with only 3 ReadTimeouts). Raise
    # via env var only if the rate limit budget has been verified.
    ingest_max_concurrent: int = 1
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
