"""Shared FastAPI dependencies for core infrastructure.

Canonical ``Depends()`` aliases that any domain can import.
Define once here, import everywhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, AsyncGenerator

from fastapi import Depends
from starlette.requests import Request

from ii_agent.core.config.settings import Settings, get_settings

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db import get_db_session_local as get_db

if TYPE_CHECKING:
    from ii_agent.core.container import ApplicationContainer


SettingsDep = Annotated[Settings, Depends(get_settings)]


async def _db_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session scoped to a single request."""

    async with get_db() as db:
        yield db


DBSession = Annotated[AsyncSession, Depends(_db_session_dependency)]


# ---------------------------------------------------------------------------
# Service container (application-scoped, created once in lifespan)
# ---------------------------------------------------------------------------


def _get_container(request: Request) -> ApplicationContainer:
    """Pull the ServiceContainer from app.state (set during lifespan startup)."""
    return request.app.state.container


ContainerDep = Annotated[Any, Depends(_get_container)]
