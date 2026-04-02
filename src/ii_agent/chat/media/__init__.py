"""Media generation module.

This module provides a unified, extensible interface for media generation.
"""

from .orchestrator import MediaOrchestrator, MediaContext

# Import handlers to trigger registration decorators
from .handlers import image_handler  # noqa: F401
from .handlers import infographic_handler  # noqa: F401
from .handlers import poster_handler  # noqa: F401
from .handlers import storybook_handler  # noqa: F401

__all__ = [
    "MediaOrchestrator",
    "MediaContext",
]
