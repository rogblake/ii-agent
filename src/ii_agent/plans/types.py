"""Plan domain enums."""

from enum import StrEnum


class MilestoneStatus(StrEnum):
    """Status of a milestone during plan execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

    @staticmethod
    def terminal_states() -> list["MilestoneStatus"]:
        return [MilestoneStatus.COMPLETED, MilestoneStatus.FAILED]
