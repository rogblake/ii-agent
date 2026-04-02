from abc import ABC, abstractmethod
from pydantic import BaseModel


class VoiceGenerationResult(BaseModel):
    url: str
    mime_type: str
    size: int
    cost: float = 0.0
    storage_path: str | None = None
    file_name: str | None = None


class VoiceGenerationError(Exception):
    """Custom exception for voice generation errors."""

    pass


class BaseVoiceGenerationClient(ABC):
    """Base interface for voice generation clients."""

    @abstractmethod
    async def generate_voice(self, text: str, **kwargs) -> VoiceGenerationResult:
        """Generate speech audio from text."""
        pass
