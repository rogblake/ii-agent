from pydantic.fields import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from ii_agent_tools.integrations.audio_generation import AudioGenerateConfig
from ii_agent_tools.integrations.database import DatabaseConfig
from ii_agent_tools.integrations.image_generation import ImageGenerateConfig
from ii_agent_tools.integrations.image_search import ImageSearchConfig
from ii_agent_tools.integrations.video_generation import VideoGenerateConfig
from ii_agent_tools.integrations.voice_generation import VoiceGenerateConfig
from ii_agent_tools.integrations.web_search import WebSearchConfig
from ii_agent_tools.integrations.web_visit import WebVisitConfig
from ii_agent_tools.llm import LLMConfig
from ii_agent_tools.storage import StorageConfig


class ToolClientSettings(BaseSettings):
    web_search_config: WebSearchConfig = Field(default_factory=WebSearchConfig)
    web_visit_config: WebVisitConfig = Field(default_factory=WebVisitConfig)
    image_search_config: ImageSearchConfig = Field(default_factory=ImageSearchConfig)
    audio_generate_config: AudioGenerateConfig = Field(
        default_factory=AudioGenerateConfig
    )
    video_generate_config: VideoGenerateConfig = Field(
        default_factory=VideoGenerateConfig
    )
    image_generate_config: ImageGenerateConfig = Field(
        default_factory=ImageGenerateConfig
    )
    voice_generate_config: VoiceGenerateConfig = Field(
        default_factory=VoiceGenerateConfig
    )
    database_config: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage_config: StorageConfig = Field(default_factory=StorageConfig)
    llm_config: LLMConfig = Field(default_factory=LLMConfig)

    model_config = SettingsConfigDict(
        env_prefix="TOOL__",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )
