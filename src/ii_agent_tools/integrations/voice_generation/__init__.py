from ii_agent_tools.integrations.voice_generation.factory import (
    create_voice_generation_client,
)
from ii_agent_tools.integrations.voice_generation.config import VoiceGenerateConfig
from ii_agent_tools.integrations.voice_generation.base import (
    BaseVoiceGenerationClient,
    VoiceGenerationResult,
    VoiceGenerationError,
)
from ii_agent_tools.integrations.voice_generation.registry import (
    register_provider,
    get_provider,
    list_providers,
)
from ii_agent_tools.integrations.voice_generation.constants import (
    VoiceGenerationProvider,
    PROVIDER_ALIASES,
)
from ii_agent_tools.integrations.voice_generation.service import VoiceGenerationService

# Import providers to register them
from ii_agent_tools.integrations.voice_generation import elevenlabs  # noqa: F401
from ii_agent_tools.integrations.voice_generation import gemini  # noqa: F401
from ii_agent_tools.integrations.voice_generation import fal  # noqa: F401

__all__ = [
    "create_voice_generation_client",
    "VoiceGenerateConfig",
    "BaseVoiceGenerationClient",
    "VoiceGenerationResult",
    "VoiceGenerationError",
    "register_provider",
    "get_provider",
    "list_providers",
    "VoiceGenerationProvider",
    "PROVIDER_ALIASES",
    "VoiceGenerationService",
]
