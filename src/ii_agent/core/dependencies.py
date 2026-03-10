"""Shared FastAPI dependencies for the II-Agent application.

This module provides core infrastructure dependencies: database session
and settings. These are cross-cutting concerns used by all domains.

For authentication dependencies (CurrentUser, get_current_user), use:
    from ii_agent.auth.dependencies import CurrentUser, DBSession

Repository dependencies live in their owning domain:
    from ii_agent.sessions.dependencies import get_session_repository, SessionRepositoryDep
    from ii_agent.auth.users.dependencies import get_user_repository, UserRepositoryDep
    from ii_agent.projects.dependencies import get_project_repository, ProjectRepositoryDep
    from ii_agent.agent.events.dependencies import get_event_repository, EventRepositoryDep
    from ii_agent.agent.sandboxes.dependencies import get_sandbox_repository, SandboxRepositoryDep

Service dependencies live in their owning domain:
    from ii_agent.files.dependencies import FileServiceDep
    from ii_agent.sessions.dependencies import SessionServiceDep
    from ii_agent.billing.dependencies import BillingServiceDep
    from ii_agent.auth.users.dependencies import UserServiceDep
    from ii_agent.sessions.wishlist.dependencies import WishlistServiceDep
"""

from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.db.manager import get_db_session_local


# ==================== Settings ====================


SettingsDep = Annotated[Settings, Depends(get_settings)]


# ==================== Database Session ====================


async def _db_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-compatible wrapper around get_db_session_local.

    FastAPI Depends() expects a raw async generator, but get_db_session_local
    is wrapped with @asynccontextmanager. This bridges the two.
    """
    async with get_db_session_local() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(_db_session_dependency)]
