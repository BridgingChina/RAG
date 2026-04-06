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
