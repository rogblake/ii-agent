"""Plan domain exceptions."""


class PlanNotFoundError(Exception):
    """Raised when session has no plan in metadata."""

    def __init__(self, session_id: object) -> None:
        super().__init__(f"No plan found for session {session_id}")
        self.session_id = session_id


class MilestoneNotFoundError(Exception):
    """Raised when requested milestone IDs don't exist in the plan."""

    def __init__(self, milestone_ids: list[str]) -> None:
        super().__init__(f"Milestones not found: {milestone_ids}")
        self.milestone_ids = milestone_ids
