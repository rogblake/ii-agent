"""Configuration for LLM-generated session titles."""

from pydantic_settings import BaseSettings


class SessionTitleConfig(BaseSettings):
    openai_api_key: str | None = None
    model: str = "gpt-5-mini"
    max_tokens: int = 100
    timeout: float = 10.0
    enabled: bool = True
    semantic_min_query_length: int = 100

    class Config:
        env_prefix = "SESSION_TITLE_"
        env_file = ".env"
        extra = "ignore"
