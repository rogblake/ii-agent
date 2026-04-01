"""Configuration for Nano Banana slide detection LLM."""

from pydantic import Field
from pydantic_settings import BaseSettings


class NanoBananaConfig(BaseSettings):
    """LLM configuration for Nano Banana vision-based slide component detection.

    All fields can be set via environment variables with the ``NANO_BANANA_``
    prefix (e.g. ``NANO_BANANA_MODEL``, ``NANO_BANANA_API_KEY``).
    """

    model: str = Field(
        default="gemini-3-flash-preview",
        description="Model identifier for vision detection",
    )
    api_key: str | None = Field(
        default=None,
        description="API key for the detection model provider",
    )
    provider: str = Field(
        default="Google",
        description="Provider name: Google, OpenAI, Anthropic, Custom",
    )
    temperature: float = Field(
        default=0.1,
        description="Sampling temperature for detection",
    )
    base_url: str | None = Field(
        default=None,
        description="Custom base URL (for custom/self-hosted providers)",
    )
    vertex_project_id: str | None = Field(
        default=None,
        description="GCP project ID when using Vertex AI",
    )
    vertex_region: str | None = Field(
        default=None,
        description="GCP region when using Vertex AI (e.g. us-central1)",
    )
    thinking_tokens: int = Field(
        default=0,
        description="Thinking budget (0 = disabled). Detection does not need thinking.",
    )

    class Config:
        env_prefix = "NANO_BANANA_"
        env_file = ".env"
        extra = "ignore"
