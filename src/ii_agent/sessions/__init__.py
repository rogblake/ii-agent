"""Session lifecycle management domain module."""

from ii_agent.sessions.title_config import SessionTitleConfig

__all__ = [
    "SessionTitleConfig",
    "SessionTitleService",
]


def __getattr__(name: str):
    if name == "SessionTitleService":
        from ii_agent.sessions.title_service import SessionTitleService

        return SessionTitleService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
