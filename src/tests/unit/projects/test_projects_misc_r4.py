"""Unit tests for subdomains router, project repository, session repository, wishlist (r4)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# ProjectRepository tests
# ---------------------------------------------------------------------------


class TestProjectRepositoryR4:
    def _make_repo(self):
        from ii_agent.projects.repository import ProjectRepository

        return ProjectRepository()

    @pytest.mark.asyncio
    async def test_get_by_id_filters_deleted(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_by_id(mock_db, "project-id-1")
        assert result is None
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_returns_project(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_by_id(mock_db, "project-1")
        assert result is mock_project

    @pytest.mark.asyncio
    async def test_get_by_id_and_user_returns_project(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_by_id_and_user(mock_db, "project-1", "user-1")
        assert result is mock_project

    @pytest.mark.asyncio
    async def test_get_by_id_and_user_returns_none_when_not_found(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_by_id_and_user(mock_db, "project-1", "wrong-user")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_session_id_returns_project(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_project
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_by_session_id(mock_db, "session-1")
        assert result is mock_project

    @pytest.mark.asyncio
    async def test_get_owner_user_id_returns_user_id(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "user-123"
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_owner_user_id(mock_db, "project-1")
        assert result == "user-123"

    @pytest.mark.asyncio
    async def test_update_custom_domain_updates_project(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_project.custom_domain_id = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()
        await repo.update_custom_domain(mock_db, "project-1", "domain-id")
        assert mock_project.custom_domain_id == "domain-id"
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_custom_domain_also_updates_production_url(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()
        await repo.update_custom_domain(
            mock_db, "project-1", "domain-id", production_url="https://custom.example.com"
        )
        assert mock_project.production_url == "https://custom.example.com"

    @pytest.mark.asyncio
    async def test_update_custom_domain_no_op_when_project_missing(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()
        # Should not raise
        await repo.update_custom_domain(mock_db, "missing-project", "domain-id")
        mock_db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_production_url(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()
        await repo.update_production_url(mock_db, "project-1", "https://new.example.com")
        assert mock_project.production_url == "https://new.example.com"
        mock_db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# SessionRepository tests
# ---------------------------------------------------------------------------


class TestSessionRepositoryR4:
    def _make_repo(self):
        from ii_agent.sessions.repository import SessionRepository

        return SessionRepository()

    @pytest.mark.asyncio
    async def test_get_by_id_returns_session(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_by_id(mock_db, "session-1")
        assert result is mock_session

    @pytest.mark.asyncio
    async def test_get_by_id_accepts_uuid(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        session_uuid = uuid.uuid4()
        result = await repo.get_by_id(mock_db, session_uuid)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_and_user_filters_deleted(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_by_id_and_user(mock_db, "session-1", "user-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_public_by_id_returns_public_session(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.is_public = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_public_by_id(mock_db, "session-1")
        assert result is mock_session

    @pytest.mark.asyncio
    async def test_get_user_id_returns_none_when_session_missing(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_user_id(mock_db, "session-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_id_returns_user_id(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.user_id = "user-42"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_user_id(mock_db, "session-1")
        assert result == "user-42"

    @pytest.mark.asyncio
    async def test_get_non_deleted_by_ids_empty_input(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        result = await repo.get_non_deleted_by_ids(mock_db, [])
        assert result == []
        # Should not call db
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_non_deleted_by_ids_returns_sessions(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_sessions = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_sessions
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_non_deleted_by_ids(mock_db, ["s1", "s2"])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# WishlistRepository tests
# ---------------------------------------------------------------------------


class TestWishlistRepositoryR4:
    def _make_repo(self):
        from ii_agent.sessions.wishlist.repository import WishlistRepository

        return WishlistRepository()

    @pytest.mark.asyncio
    async def test_get_user_wishlists_returns_list(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_items = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_items
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_user_wishlists(mock_db, "user-1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_by_user_and_session_returns_item(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_item = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_item
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_by_user_and_session(mock_db, "user-1", "session-1")
        assert result is mock_item

    @pytest.mark.asyncio
    async def test_get_by_user_and_session_returns_none(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.get_by_user_and_session(mock_db, "user-1", "session-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_adds_to_db(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_item = MagicMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        result = await repo.create(mock_db, mock_item)
        mock_db.add.assert_called_once_with(mock_item)
        mock_db.flush.assert_called_once()
        assert result is mock_item

    @pytest.mark.asyncio
    async def test_delete_by_user_and_session_returns_true_when_deleted(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.delete_by_user_and_session(mock_db, "user-1", "session-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_by_user_and_session_returns_false_when_not_found(self):
        repo = self._make_repo()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await repo.delete_by_user_and_session(mock_db, "user-1", "session-1")
        assert result is False


# ---------------------------------------------------------------------------
# SessionWishlistService tests
# ---------------------------------------------------------------------------


class TestSessionWishlistServiceR4:
    def _make_service(self):
        from ii_agent.sessions.wishlist.service import SessionWishlistService

        wishlist_repo = MagicMock()
        session_repo = MagicMock()
        config = MagicMock()
        return SessionWishlistService(
            wishlist_repo=wishlist_repo,
            session_repo=session_repo,
            config=config,
        )

    @pytest.mark.asyncio
    async def test_get_user_wishlist_returns_formatted_list(self):
        svc = self._make_service()
        mock_session = MagicMock()
        mock_session.name = "My Session"
        mock_session.last_message_at = None
        item = MagicMock()
        item.id = "wl-1"
        item.session_id = "session-1"
        item.session = mock_session
        item.created_at = None
        svc._wishlist_repo.get_user_wishlists = AsyncMock(return_value=[item])
        result = await svc.get_user_wishlist(AsyncMock(), "user-1")
        assert len(result) == 1
        assert result[0]["session_id"] == "session-1"
        assert result[0]["session_name"] == "My Session"

    @pytest.mark.asyncio
    async def test_add_to_wishlist_returns_true_when_added(self):
        svc = self._make_service()
        mock_session = MagicMock()
        mock_session.user_id = "user-1"
        svc._session_repo.get_by_id = AsyncMock(return_value=mock_session)
        svc._wishlist_repo.get_by_user_and_session = AsyncMock(return_value=None)
        svc._wishlist_repo.create = AsyncMock()
        result = await svc.add_to_wishlist(AsyncMock(), "user-1", "session-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_add_to_wishlist_returns_false_when_already_exists(self):
        svc = self._make_service()
        mock_session = MagicMock()
        mock_session.user_id = "user-1"
        svc._session_repo.get_by_id = AsyncMock(return_value=mock_session)
        svc._wishlist_repo.get_by_user_and_session = AsyncMock(return_value=MagicMock())
        result = await svc.add_to_wishlist(AsyncMock(), "user-1", "session-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_add_to_wishlist_raises_when_session_not_found(self):
        from ii_agent.sessions.exceptions import SessionNotFoundError

        svc = self._make_service()
        svc._session_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(SessionNotFoundError):
            await svc.add_to_wishlist(AsyncMock(), "user-1", "session-1")

    @pytest.mark.asyncio
    async def test_add_to_wishlist_raises_when_wrong_user(self):
        from ii_agent.sessions.exceptions import SessionNotFoundError

        svc = self._make_service()
        mock_session = MagicMock()
        mock_session.user_id = "other-user"
        svc._session_repo.get_by_id = AsyncMock(return_value=mock_session)
        with pytest.raises(SessionNotFoundError):
            await svc.add_to_wishlist(AsyncMock(), "user-1", "session-1")

    @pytest.mark.asyncio
    async def test_remove_from_wishlist_returns_true_when_deleted(self):
        svc = self._make_service()
        svc._wishlist_repo.delete_by_user_and_session = AsyncMock(return_value=True)
        result = await svc.remove_from_wishlist(AsyncMock(), "user-1", "session-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_from_wishlist_returns_false_when_not_found(self):
        svc = self._make_service()
        svc._wishlist_repo.delete_by_user_and_session = AsyncMock(return_value=False)
        result = await svc.remove_from_wishlist(AsyncMock(), "user-1", "session-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_in_wishlist_returns_true(self):
        svc = self._make_service()
        svc._wishlist_repo.get_by_user_and_session = AsyncMock(return_value=MagicMock())
        result = await svc.is_in_wishlist(AsyncMock(), "user-1", "session-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_in_wishlist_returns_false(self):
        svc = self._make_service()
        svc._wishlist_repo.get_by_user_and_session = AsyncMock(return_value=None)
        result = await svc.is_in_wishlist(AsyncMock(), "user-1", "session-1")
        assert result is False


# ---------------------------------------------------------------------------
# Subdomain utils
# ---------------------------------------------------------------------------


class TestSubdomainUtilsR4:
    def test_reserved_subdomains_is_set(self):
        from ii_agent.projects.subdomains.utils import RESERVED_SUBDOMAINS

        assert isinstance(RESERVED_SUBDOMAINS, (set, frozenset))
        assert len(RESERVED_SUBDOMAINS) > 0

    def test_common_names_are_reserved(self):
        from ii_agent.projects.subdomains.utils import RESERVED_SUBDOMAINS

        common = {"www", "api", "admin"}
        overlap = common & RESERVED_SUBDOMAINS
        assert len(overlap) > 0, f"Expected some overlap with {common}, got none"
