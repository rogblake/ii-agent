import functools
from typing import Any, Callable, TypeVar

from celery import Task

from ii_agent.core.logger import logger

F = TypeVar("F", bound=Callable[..., Any])


def with_task_context(func: F) -> F:
    """
    Decorator to set logging context for Celery tasks.

    Reads context from task request headers (session_id, user_id, run_id) and uses
    the Celery task_id as request_id for log correlation.
    """

    @functools.wraps(func)
    def wrapper(self: Task, *args: Any, **kwargs: Any) -> Any:
        request = self.request
        headers = request.headers or {}

        ctx = {
            k: v
            for k, v in {
                "request_id": request.id,
                "session_id": headers.get("session_id"),
                "user_id": headers.get("user_id"),
                "run_id": headers.get("run_id"),
                "celery_task_id": request.id,
            }.items()
            if v is not None
        }

        with logger.contextualize(**ctx):
            return func(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]
