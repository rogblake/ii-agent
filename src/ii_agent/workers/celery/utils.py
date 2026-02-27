"""
Utilities for integrating Celery with async endpoints.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Optional

from celery.result import AsyncResult

from ii_agent.workers.celery.app import celery_app

_executor = ThreadPoolExecutor(max_workers=10)


async def get_task_result(task_id: str, timeout: Optional[float] = None) -> Any:
    """Asynchronously wait for and get a Celery task result."""
    loop = asyncio.get_event_loop()
    result = AsyncResult(task_id, app=celery_app)
    func = partial(result.get, timeout=timeout, propagate=True)
    return await loop.run_in_executor(_executor, func)


async def get_task_status(task_id: str) -> dict[str, Any]:
    """Get the current status of a Celery task."""
    result = AsyncResult(task_id, app=celery_app)
    response = {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else None,
    }

    if result.ready():
        try:
            response["result"] = result.get(propagate=False)
        except Exception as e:
            response["error"] = str(e)
    elif result.status == "PROGRESS":
        response["progress"] = result.info

    return response


async def revoke_task(
    task_id: str,
    terminate: bool = False,
    signal: str = "SIGTERM",
) -> dict[str, Any]:
    """Revoke (cancel) a Celery task."""
    celery_app.control.revoke(task_id, terminate=terminate, signal=signal)
    return {
        "task_id": task_id,
        "revoked": True,
        "terminated": terminate,
    }


def queue_task(
    task_name: str,
    *args: Any,
    queue: Optional[str] = None,
    countdown: Optional[int] = None,
    eta: Optional[Any] = None,
    expires: Optional[int] = None,
    headers: Optional[dict[str, Any]] = None,
    **kwargs: Any,
) -> str:
    """Queue a Celery task by name and return the task ID."""
    task = celery_app.send_task(
        task_name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        countdown=countdown,
        eta=eta,
        expires=expires,
        headers=headers,
    )
    return task.id
