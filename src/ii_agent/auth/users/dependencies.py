"""FastAPI dependencies for users domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.auth.users.repository import APIKeyRepository, UserRepository
from ii_agent.auth.users.service import UserService
from ii_agent.auth.users.waitlist_repository import WaitlistRepository


# ==================== Repository Dependencies ====================


def get_user_repository() -> UserRepository:
    """Provide UserRepository instance."""
    return UserRepository()


def get_api_key_repository() -> APIKeyRepository:
    """Provide APIKeyRepository instance."""
    return APIKeyRepository()


def get_waitlist_repository() -> WaitlistRepository:
    """Provide WaitlistRepository instance."""
    return WaitlistRepository()


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
APIKeyRepositoryDep = Annotated[APIKeyRepository, Depends(get_api_key_repository)]
WaitlistRepositoryDep = Annotated[WaitlistRepository, Depends(get_waitlist_repository)]


# ==================== Service Dependencies ====================


def get_user_service(
    user_repo: UserRepositoryDep,
    api_key_repo: APIKeyRepositoryDep,
    waitlist_repo: WaitlistRepositoryDep,
) -> UserService:
    """Provide UserService instance with explicit repo injection."""
    return UserService(
        user_repo=user_repo,
        api_key_repo=api_key_repo,
        waitlist_repo=waitlist_repo,
        config=get_settings(),
    )


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


__all__ = [
    "get_user_repository",
    "get_api_key_repository",
    "get_waitlist_repository",
    "get_user_service",
    "UserRepositoryDep",
    "APIKeyRepositoryDep",
    "WaitlistRepositoryDep",
    "UserServiceDep",
]
