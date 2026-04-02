from __future__ import annotations

from abc import ABC, abstractmethod

from ii_agent.core.config.settings import Settings
from ii_agent.settings.llm.persisted_settings import PersistedSettings


class SettingsStore(ABC):
    """Abstract base class for storing user settings."""

    @abstractmethod
    async def load(self) -> PersistedSettings | None:
        """Load session init data."""

    @abstractmethod
    async def store(self, settings: PersistedSettings) -> None:
        """Store session init data."""

    @classmethod
    @abstractmethod
    async def get_instance(
        cls, config: Settings, user_id: str | None
    ) -> SettingsStore:
        """Get a store for the user represented by the token given."""
