"""FastAPI dependencies for users domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.users.repository import APIKeyRepository, UserRepository
from ii_agent.users.service import UserService
from ii_agent.users.waitlist_repository import WaitlistRepository


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


def _get_user_service(container: ContainerDep) -> UserService:
    return container.user_service


UserServiceDep = Annotated[UserService, Depends(_get_user_service)]
