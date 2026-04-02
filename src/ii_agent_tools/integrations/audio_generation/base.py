from abc import ABC, abstractmethod

from pydantic import BaseModel


class AudioGenerationResult(BaseModel):
    url: str
    mime_type: str
    size: int
    cost: float = 0.0
    storage_path: str | None = None
    file_name: str | None = None


class AudioGenerationError(Exception):
    """Custom exception for audio generation errors."""

    pass


class BaseAudioGenerationClient(ABC):
    """Base interface for audio generation clients."""

    @abstractmethod
    async def generate_audio(self, prompt: str, **kwargs) -> AudioGenerationResult:
        """Generate audio from a text prompt."""
        pass
