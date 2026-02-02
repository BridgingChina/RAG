from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://bridge:bridge@localhost:5433/bridge_rag"
    zhipu_api_key: str = ""

    # LLM settings
    embedding_model: str = "embedding-3"
    chat_model: str = "glm-4"

    # Retrieval settings
    top_k: int = 5

    class Config:
        env_file = ".env"


settings = Settings()
