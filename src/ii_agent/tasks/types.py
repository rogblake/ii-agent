"""Task-related enums — RunStatus and TaskType."""

from enum import StrEnum


class TaskType(StrEnum):
    """Discriminator for the kind of work a run_task represents."""

    AGENT_RUN = "agent_run"
    CHAT_RUN = "chat_run"
    MEDIA_GENERATION = "media_generation"


class RunStatus(StrEnum):
    """Unified run status for all task types.

    State machine::

        PENDING → RUNNING → COMPLETED
                         → FAILED
                         → ABORTING → CANCELLED
                → PAUSED → RUNNING (resume)
                         → CANCELLED
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"
    ABORTING = "aborting"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @staticmethod
    def active_states() -> list["RunStatus"]:
        """States that represent an active (non-terminal) run."""
        return [RunStatus.RUNNING, RunStatus.PENDING, RunStatus.PAUSED, RunStatus.ABORTING]

    @staticmethod
    def terminal_states() -> list["RunStatus"]:
        """States that represent a finished run."""
        return [RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.FAILED]

    @staticmethod
    def active_status_sql() -> str:
        """SQL fragment for partial unique index WHERE clause."""
        values = ", ".join(f"'{s.value}'" for s in RunStatus.active_states())
        return f"status IN ({values})"
