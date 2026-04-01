"""Agent runs package.

RunTask / TaskLog / RunTaskRepository / RunTaskService live in ``ii_agent.tasks``.
This package keeps agent-specific code: AgentRunMessage, RunContext.
"""

from ii_agent.agents.runs.base import RunContext
from ii_agent.agents.runs.models import AgentRunMessage, SessionSummary
from ii_agent.agents.runs.agent import (  # noqa: F401
    ReasoningDeltaEvent,
    RunContentDeltaEvent,
    RunEvent,
    RunInput,
    RunOutput,
    RunOutputEvent,
)

# Re-exports for backward compatibility
from ii_agent.tasks.models import RunTask, TaskLog  # noqa: F401
from ii_agent.tasks.types import RunStatus, TaskType  # noqa: F401

__all__ = [
    "RunContext",
    "AgentRunMessage",
    "SessionSummary",
    "ReasoningDeltaEvent",
    "RunContentDeltaEvent",
    "RunEvent",
    "RunInput",
    "RunOutput",
    "RunOutputEvent",
    "RunTask",
    "TaskLog",
    "RunStatus",
    "TaskType",
]
