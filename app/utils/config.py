from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )
    openai_embedding_dimensions: int = Field(
        default=1536, alias="OPENAI_EMBEDDING_DIMENSIONS", gt=0
    )
    database_url: str = Field(
        default="postgresql://steady:steady@localhost:5432/steady_current",
        alias="DATABASE_URL",
    )
    retrieval_top_k: int = Field(default=5, alias="RETRIEVAL_TOP_K")
    gradio_server_name: str = Field(default="0.0.0.0", alias="GRADIO_SERVER_NAME")
    gradio_server_port: int = Field(default=7870, alias="GRADIO_SERVER_PORT")
    app_user_id: str = Field(default="default-user", alias="APP_USER_ID")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
