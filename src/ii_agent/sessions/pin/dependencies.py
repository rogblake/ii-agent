"""FastAPI dependencies for session pins."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.sessions.pin.repository import PinRepository
from ii_agent.sessions.pin.service import SessionPinService


# ==================== Repository Dependencies ====================


def get_pin_repository() -> PinRepository:
    """Provide PinRepository instance."""
    return PinRepository()


PinRepositoryDep = Annotated[PinRepository, Depends(get_pin_repository)]


# ==================== Service Dependencies ====================


def get_pin_service(
    pin_repo: PinRepositoryDep,
    session_repo: SessionRepositoryDep,
) -> SessionPinService:
    """Provide SessionPinService instance with explicit repo injection."""
    return SessionPinService(
        pin_repo=pin_repo,
        session_repo=session_repo,
        config=get_settings(),
    )


PinServiceDep = Annotated[SessionPinService, Depends(get_pin_service)]


__all__ = [
    "get_pin_repository",
    "get_pin_service",
    "PinRepositoryDep",
    "PinServiceDep",
]
