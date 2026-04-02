from ii_agent_tools.integrations.slide_generation.base import (
    BaseSlideGenerationClient,
    SlideGenerationResult,
)
from ii_agent_tools.integrations.slide_generation.config import SlideGenerationConfig
from ii_agent_tools.integrations.slide_generation.factory import (
    create_slide_generation_client,
)
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


class SlideGenerationService:
    """Lazy-initialized slide generation service."""

    def __init__(self, config: SlideGenerationConfig):
        self._config = config
        self._client_instance: BaseSlideGenerationClient | None = None

    def _get_client(self) -> BaseSlideGenerationClient:
        if self._client_instance is None:
            self._client_instance = create_slide_generation_client(self._config)
        return self._client_instance

    async def generate_slide(self, full_prompt: str) -> SlideGenerationResult:
        try:
            return await self._get_client().generate_slide(full_prompt=full_prompt)
        except ValueError:
            raise
        except Exception:
            logger.exception("Slide generation failed")
            raise
