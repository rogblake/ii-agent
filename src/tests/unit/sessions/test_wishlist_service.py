from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.wishlist.service import SessionWishlistService


@pytest.mark.asyncio
async def test_add_to_wishlist_enforces_session_ownership(settings_factory):
    session_repo = AsyncMock()
    wishlist_repo = AsyncMock()

    session_repo.get_by_id.return_value = SimpleNamespace(id="s1", user_id="owner")

    service = SessionWishlistService(
        wishlist_repo=wishlist_repo,
        session_repo=session_repo,
        config=settings_factory(),
    )

    with pytest.raises(SessionNotFoundError):
        await service.add_to_wishlist(db=None, user_id="other-user", session_id="s1")

    wishlist_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_add_to_wishlist_duplicate_returns_false_without_create(settings_factory):
    session_repo = AsyncMock()
    wishlist_repo = AsyncMock()

    session_repo.get_by_id.return_value = SimpleNamespace(id="s1", user_id="u1")
    wishlist_repo.get_by_user_and_session.return_value = SimpleNamespace(id="w1")

    service = SessionWishlistService(
        wishlist_repo=wishlist_repo,
        session_repo=session_repo,
        config=settings_factory(),
    )

    result = await service.add_to_wishlist(db=None, user_id="u1", session_id="s1")

    assert result is False
    wishlist_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_remove_from_wishlist_returns_false_when_missing(settings_factory):
    session_repo = AsyncMock()
    wishlist_repo = AsyncMock()
    wishlist_repo.delete_by_user_and_session.return_value = False

    service = SessionWishlistService(
        wishlist_repo=wishlist_repo,
        session_repo=session_repo,
        config=settings_factory(),
    )

    result = await service.remove_from_wishlist(
        db=None,
        user_id="u1",
        session_id="missing",
    )

    assert result is False
