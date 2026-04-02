"""Domain exceptions for the tasks module."""

import uuid


class TaskConflictException(Exception):
    """Raised when an active task for (task_type, session_id) already exists."""

    def __init__(self, task_type: str, session_id: uuid.UUID) -> None:
        self.task_type = task_type
        self.session_id = session_id
        super().__init__(f"Task already claimed: type={task_type}, session={session_id}")
