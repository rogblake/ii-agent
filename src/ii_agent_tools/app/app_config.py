from functools import lru_cache
from typing import Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ii_agent_tools.integrations.database import DatabaseConfig
from ii_agent_tools.integrations.audio_generation import AudioGenerateConfig
from ii_agent_tools.integrations.image_generation import ImageGenerateConfig
from ii_agent_tools.integrations.image_search import ImageSearchConfig
from ii_agent_tools.integrations.video_generation import VideoGenerateConfig
from ii_agent_tools.integrations.voice_generation import VoiceGenerateConfig
from ii_agent_tools.integrations.web_search import WebSearchConfig
from ii_agent_tools.integrations.web_visit import WebVisitConfig
from ii_agent_tools.llm import LLMConfig
from ii_agent_tools.storage import StorageConfig


class Settings(BaseSettings):
    # Environment configuration
    environment: str = Field(
        default="development",
        description="Environment: development, staging, production",
    )

    # Database configuration
    database_url: Optional[str] = None

    # Security configuration
    auth_secret_key: str = Field(
        ...,
        min_length=32,
        description="JWT secret key (min 32 chars). Required for security.",
    )

    # CORS configuration
    cors_allowed_origins: Union[str, list[str]] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins. Restrict in production! Can be comma-separated string or JSON array.",
    )

    # Service authorization
    allowed_services: Union[str, list[str]] = Field(
        default=["service-a", "service-c"],
        description="Allowed services for API access. Can be comma-separated string or JSON array.",
    )

    # Integration configurations
    web_search_config: WebSearchConfig = WebSearchConfig()
    web_visit_config: WebVisitConfig = WebVisitConfig()
    image_search_config: ImageSearchConfig = ImageSearchConfig()
    audio_generate_config: AudioGenerateConfig = AudioGenerateConfig()
    video_generate_config: VideoGenerateConfig = VideoGenerateConfig()
    image_generate_config: ImageGenerateConfig = ImageGenerateConfig()
    voice_generate_config: VoiceGenerateConfig = VoiceGenerateConfig()
    database_config: DatabaseConfig = DatabaseConfig()
    storage_config: StorageConfig = StorageConfig()
    llm_config: LLMConfig = LLMConfig()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @field_validator("allowed_services", "cors_allowed_origins", mode="before")
    @classmethod
    def parse_comma_separated_lists(cls, v: Union[str, list[str]]) -> list[str]:
        """Parse comma-separated string values to list."""
        if isinstance(v, str):
            # Handle comma-separated string from env var
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("auth_secret_key")
    @classmethod
    def validate_auth_secret_key(cls, v: str, info) -> str:
        """Validate that auth secret key is secure and not the default value."""
        if v == "your-secret-key":
            raise ValueError(
                "AUTH_SECRET_KEY must be set! Default value 'your-secret-key' is insecure. "
                "Generate a secure key with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        return v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value."""
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"Environment must be one of: {allowed}")
        return v

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_origins(cls, v: list[str], info) -> list[str]:
        """Warn if using wildcard CORS in production."""
        env = info.data.get("environment", "development")
        if env == "production" and "*" in v:
            raise ValueError(
                "CORS wildcard '*' is not allowed in production! "
                "Set specific origins via CORS_ALLOWED_ORIGINS environment variable."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
