from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+psycopg://bridge:bridge@localhost:5433/bridge_rag"
    zhipu_api_key: str = ""

    # LLM settings
    embedding_model: str = "embedding-3"
    chat_model: str = "glm-4"

    # Retrieval settings
    top_k: int = 5


settings = Settings()
