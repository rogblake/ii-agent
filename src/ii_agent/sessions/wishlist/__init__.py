"""Session wishlist management submodule.

Import pattern:
    from ii_agent.sessions.wishlist.models import SessionWishlist
    from ii_agent.sessions.wishlist.repository import WishlistRepository
    from ii_agent.sessions.wishlist.service import SessionWishlistService
    from ii_agent.sessions.wishlist.dependencies import WishlistServiceDep
    from ii_agent.sessions.wishlist.schemas import SessionWishlistItem, SessionWishlistResponse
    from ii_agent.sessions.wishlist.router import router
"""

from .router import router

__all__ = [
    "router",
]
