"""LLM configuration domain module."""

from .models import LLMSetting
from .persisted_settings import PersistedSettings
from .store import SettingsStore, FileSettingsStore

__all__ = [
    # Models
    "LLMSetting",
    # Router
    "router",
    # Settings
    "PersistedSettings",
    "SettingsStore",
    "FileSettingsStore",
]


def __getattr__(name: str):
    if name == "router":
        from .router import router

        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
