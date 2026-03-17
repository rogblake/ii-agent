"""Media generation module.

This module provides a unified, extensible interface for media generation.

Handler registration is deferred until first use — the orchestrator calls
``_ensure_handlers_registered()`` lazily so that importing this package
does not pull in heavyweight handler dependencies at startup.
"""

from .orchestrator import MediaOrchestrator, MediaContext

__all__ = [
    "MediaOrchestrator",
    "MediaContext",
]
