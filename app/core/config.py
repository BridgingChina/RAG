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
    # httpx read timeout (seconds) for chat completions.
    # 90s (was 45s) — empirically 45s caused ReadTimeout cascade during
    # Zhipu's slow-response periods (2026-04-16 晋祠十字桥.pdf RCA): 6×
    # 45s ReadTimeouts exhausted the retry budget faster than Zhipu could
    # recover.  90s lets genuinely-slow responses complete instead of
    # being force-killed.  Worst-case per-call ceiling: 90s × 8 attempts
    # + backoffs ≈ 15 min — still bounded, but resilient to bad days.
    # Per-chunk fallback (see ingest_task_service.start_indexing) stops
    # any single failure from killing the whole task.
    chat_read_timeout: float = 90.0
    # httpx read timeout (seconds) for embeddings.
    # Embeddings are fast (~1-2s p95). 20s is a generous ceiling; anything
    # longer is almost certainly a network stall, not a slow response.
    embed_read_timeout: float = 20.0

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

    # External JWKS-based auth (Phase 2 — Better Auth via auth.bridgingchina.net)
    auth_jwks_url: str = "https://auth.bridgingchina.net/api/auth/jwks"
    auth_worker_base_url: str = "https://auth.bridgingchina.net"
    jwt_issuer: str = "https://auth.bridgingchina.net"
    jwt_audience: str = "fastapi"

    # Internal API (auth Worker → FastAPI webhook calls). Empty string
    # disables all /internal/* endpoints with a 503 for defense-in-depth.
    internal_api_secret: str = ""

    # R2 storage settings
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "bridge-rag"
    r2_public_url: str = ""  # optional, for public access

    # Zhipu file parser settings
    zhipu_parser_tool_type: str = "expert"  # lite / expert / prime

    # CORS settings — dev hosts + the three Phase 2 production subdomains.
    # Anything matching the bridgingchina.net regex in main.py also passes,
    # but listing explicit origins first means preflight responses are stable
    # for Origin header debugging.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://auth.bridgingchina.net",
        "https://console.bridgingchina.net",
        "https://bridgingchina.net",
    ]

    # Build info (injected via Docker build args)
    git_commit: str = "dev"
    git_date: str = ""


settings = Settings()
