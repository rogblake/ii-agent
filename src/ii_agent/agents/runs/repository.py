"""Backward-compatibility re-export.

RunTaskRepository has moved to ``ii_agent.tasks.repository``.
"""

from ii_agent.tasks.repository import RunTaskRepository  # noqa: F401

__all__ = ["RunTaskRepository"]
