"""Router package."""

from ii_agent_tools.app.routers import (
    audio,
    database,
    health,
    image,
    voice,
    video,
    web_search,
    web_visit,
)

__all__ = [
    "database",
    "health",
    "audio",
    "image",
    "voice",
    "video",
    "web_search",
    "web_visit",
]
