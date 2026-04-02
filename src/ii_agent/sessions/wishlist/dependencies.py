"""FastAPI dependencies for session wishlist."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.sessions.wishlist.repository import WishlistRepository
from ii_agent.sessions.wishlist.service import SessionWishlistService


# ==================== Repository Dependencies ====================


def get_wishlist_repository() -> WishlistRepository:
    """Provide WishlistRepository instance."""
    return WishlistRepository()


WishlistRepositoryDep = Annotated[WishlistRepository, Depends(get_wishlist_repository)]


# ==================== Service Dependencies ====================


def get_wishlist_service(
    wishlist_repo: WishlistRepositoryDep,
    session_repo: SessionRepositoryDep,
) -> SessionWishlistService:
    """Provide SessionWishlistService instance with explicit repo injection."""
    return SessionWishlistService(
        wishlist_repo=wishlist_repo,
        session_repo=session_repo,
        config=get_settings(),
    )


WishlistServiceDep = Annotated[SessionWishlistService, Depends(get_wishlist_service)]


__all__ = [
    "get_wishlist_repository",
    "get_wishlist_service",
    "WishlistRepositoryDep",
    "WishlistServiceDep",
]
