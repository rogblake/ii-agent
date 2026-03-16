"""Deep unit tests for ii_agent.auth.users.service covering remaining branches."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.auth.users.exceptions import UserDisabledException, WaitlistDeniedException
from ii_agent.auth.users.service import VALID_LANGUAGES, UserService
from ii_agent.core.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


class FakeUserRepo:
    def __init__(self):
        self.by_id: dict = {}
        self.by_email: dict = {}
        self.profiles_updated = []
        self.language_set = []
        self.active_set = []

    async def get_by_id(self, db, user_id):
        return self.by_id.get(user_id)

    async def get_by_email(self, db, email):
        return self.by_email.get(email)

    async def create(self, db, **kwargs):
        user = SimpleNamespace(id="user-new", is_active=True, **kwargs)
        self.by_email[kwargs["email"]] = user
        return user

    async def update_profile(self, db, user, **kwargs):
        for k, v in kwargs.items():
            if v is not None:
                setattr(user, k, v)
        self.profiles_updated.append((user, kwargs))

    async def set_language(self, db, user, language):
        user.language = language
        self.language_set.append((user, language))

    async def set_active(self, db, user, is_active):
        user.is_active = is_active
        self.active_set.append((user, is_active))


class FakeAPIKeyRepo:
    def __init__(self, active_key="test-api-key"):
        self.created = []
        self._active_key = active_key

    async def create(self, db, user_id, api_key):
        record = SimpleNamespace(id="key-1", api_key=api_key)
        self.created.append((user_id, api_key))
        return record

    async def get_active_for_user(self, db, user_id):
        return self._active_key


class FakeWaitlistRepo:
    def __init__(self):
        self.allowed: set = set()

    async def get_by_email(self, db, email):
        if email in self.allowed:
            return {"email": email}
        return None


class FakeCreditService:
    def __init__(self):
        self.ensured = []

    async def ensure_balance_exists(self, db, user_id, **kwargs):
        from decimal import Decimal
        credits = Decimal(str(kwargs.get("credits", 0)))
        bonus = Decimal(str(kwargs.get("bonus_credits", 0)))
        self.ensured.append((user_id, credits, bonus))
        return (credits, bonus)


def _make_service(*, waitlist_enabled=False, active_key="test-key") -> UserService:
    config = SimpleNamespace(
        credits=SimpleNamespace(
            default_user_credits=10.0,
            default_subscription_plan="free",
            waitlist_enabled=waitlist_enabled,
        )
    )
    return UserService(
        user_repo=FakeUserRepo(),
        api_key_repo=FakeAPIKeyRepo(active_key=active_key),
        waitlist_repo=FakeWaitlistRepo(),
        credit_service=FakeCreditService(),
        config=config,
    )


# ---------------------------------------------------------------------------
# get_user_by_id
# ---------------------------------------------------------------------------


class TestGetUserById:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        svc = _make_service()
        result = await svc.get_user_by_id(None, "non-existent")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_user_when_found(self):
        svc = _make_service()
        user = SimpleNamespace(id="u-1", email="a@b.com")
        svc._user_repo.by_id["u-1"] = user
        result = await svc.get_user_by_id(None, "u-1")
        assert result is user


# ---------------------------------------------------------------------------
# get_user_by_email
# ---------------------------------------------------------------------------


class TestGetUserByEmail:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        svc = _make_service()
        result = await svc.get_user_by_email(None, "nobody@example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_user_when_found(self):
        svc = _make_service()
        user = SimpleNamespace(id="u-2", email="found@x.com")
        svc._user_repo.by_email["found@x.com"] = user
        result = await svc.get_user_by_email(None, "found@x.com")
        assert result is user


# ---------------------------------------------------------------------------
# get_active_api_key
# ---------------------------------------------------------------------------


class TestGetActiveApiKey:
    @pytest.mark.asyncio
    async def test_returns_key(self):
        svc = _make_service(active_key="sk-active")
        key = await svc.get_active_api_key(None, "u-1")
        assert key == "sk-active"


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_creates_user_with_defaults(self):
        svc = _make_service()
        user = await svc.create_user(None, email="new@test.com")
        assert user.email == "new@test.com"
        assert not hasattr(user, "credits")
        assert not hasattr(user, "subscription_plan")

    @pytest.mark.asyncio
    async def test_creates_api_key_for_user(self):
        svc = _make_service()
        await svc.create_user(None, email="key@test.com")
        assert len(svc._api_key_repo.created) == 1

    @pytest.mark.asyncio
    async def test_passes_all_fields(self):
        svc = _make_service()
        user = await svc.create_user(
            None,
            email="full@test.com",
            first_name="First",
            last_name="Last",
            avatar="https://avatar.url",
            email_verified=True,
            login_provider="google",
        )
        assert user.first_name == "First"
        assert user.last_name == "Last"
        assert user.login_provider == "google"


# ---------------------------------------------------------------------------
# create_api_key
# ---------------------------------------------------------------------------


class TestCreateApiKey:
    @pytest.mark.asyncio
    async def test_creates_and_returns_key(self):
        svc = _make_service()
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "ii_agent.auth.users.service.UserService.create_api_key",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = SimpleNamespace(id="k1", api_key="pfx_abc")
            result = await svc.create_api_key(None, user_id="u-1")
            # Just verify the mock was setup (the real impl calls api_key_repo)
        # Test real implementation via create_user flow
        svc2 = _make_service()
        await svc2.create_user(None, email="testkey@x.com")
        assert len(svc2._api_key_repo.created) == 1
        key_value = svc2._api_key_repo.created[0][1]
        assert isinstance(key_value, str)
        assert len(key_value) > 0


# ---------------------------------------------------------------------------
# update_login_profile
# ---------------------------------------------------------------------------


class TestUpdateLoginProfile:
    @pytest.mark.asyncio
    async def test_updates_provided_fields(self):
        svc = _make_service()
        user = SimpleNamespace(
            id="u-1",
            first_name="Old",
            last_name="Name",
            avatar=None,
            email_verified=False,
            login_provider=None,
        )
        result = await svc.update_login_profile(
            None,
            user,
            first_name="New",
            last_name="Last",
            avatar="https://img.url",
            email_verified=True,
            login_provider="github",
        )
        assert result is user
        assert user.first_name == "New"
        assert user.last_name == "Last"
        assert user.avatar == "https://img.url"
        assert user.email_verified is True
        assert user.login_provider == "github"

    @pytest.mark.asyncio
    async def test_none_fields_not_overwritten(self):
        svc = _make_service()
        user = SimpleNamespace(
            id="u-2",
            first_name="Keep",
            last_name="Me",
            avatar="existing",
            email_verified=True,
            login_provider="google",
        )
        await svc.update_login_profile(None, user, first_name=None)
        # None values should not overwrite
        assert user.first_name == "Keep"


# ---------------------------------------------------------------------------
# check_waitlist
# ---------------------------------------------------------------------------


class TestCheckWaitlist:
    @pytest.mark.asyncio
    async def test_passes_when_waitlist_disabled(self):
        svc = _make_service(waitlist_enabled=False)
        # Should not raise for any email
        await svc.check_waitlist(None, "anyone@example.com")

    @pytest.mark.asyncio
    async def test_passes_for_ii_inc_email_even_when_waitlist_enabled(self):
        svc = _make_service(waitlist_enabled=True)
        # ii.inc emails are always allowed
        await svc.check_waitlist(None, "admin@ii.inc")

    @pytest.mark.asyncio
    async def test_raises_when_email_not_on_waitlist(self):
        svc = _make_service(waitlist_enabled=True)
        with pytest.raises(WaitlistDeniedException):
            await svc.check_waitlist(None, "outsider@example.com")

    @pytest.mark.asyncio
    async def test_passes_when_email_on_waitlist(self):
        svc = _make_service(waitlist_enabled=True)
        svc._waitlist_repo.allowed.add("approved@example.com")
        await svc.check_waitlist(None, "approved@example.com")


# ---------------------------------------------------------------------------
# find_or_create_oauth_user
# ---------------------------------------------------------------------------


class TestFindOrCreateOAuthUser:
    @pytest.mark.asyncio
    async def test_creates_new_user_when_not_found(self):
        svc = _make_service()
        user = await svc.find_or_create_oauth_user(None, email="brand_new@x.com")
        assert user.email == "brand_new@x.com"
        assert len(svc._user_repo.profiles_updated) == 0

    @pytest.mark.asyncio
    async def test_updates_existing_active_user(self):
        svc = _make_service()
        existing = SimpleNamespace(
            id="u-e",
            email="existing@x.com",
            is_active=True,
            first_name="Old",
            last_name="Name",
            avatar=None,
            email_verified=False,
            login_provider=None,
        )
        svc._user_repo.by_email["existing@x.com"] = existing
        user = await svc.find_or_create_oauth_user(
            None, email="existing@x.com", first_name="Updated"
        )
        assert user is existing
        assert user.first_name == "Updated"

    @pytest.mark.asyncio
    async def test_raises_for_disabled_user(self):
        svc = _make_service()
        disabled = SimpleNamespace(id="u-d", email="dis@x.com", is_active=False)
        svc._user_repo.by_email["dis@x.com"] = disabled
        with pytest.raises(UserDisabledException):
            await svc.find_or_create_oauth_user(None, email="dis@x.com")

    @pytest.mark.asyncio
    async def test_creates_with_bonus_credits(self):
        svc = _make_service()
        user = await svc.find_or_create_oauth_user(
            None, email="bonus@x.com", bonus_credits=50.0
        )
        # bonus_credits is now stored in credit_balances, not on the user row
        assert user.email == "bonus@x.com"

    @pytest.mark.asyncio
    async def test_creates_with_login_provider(self):
        svc = _make_service()
        user = await svc.find_or_create_oauth_user(
            None, email="gh@x.com", login_provider="github"
        )
        assert user.login_provider == "github"


# ---------------------------------------------------------------------------
# update_language
# ---------------------------------------------------------------------------


class TestUpdateLanguage:
    @pytest.mark.asyncio
    async def test_valid_language_sets_language(self):
        svc = _make_service()
        user = SimpleNamespace(id="u-1", language=None)
        for lang in VALID_LANGUAGES:
            await svc.update_language(None, user, lang)
            assert user.language == lang

    @pytest.mark.asyncio
    async def test_invalid_language_raises_validation_error(self):
        svc = _make_service()
        user = SimpleNamespace(id="u-1", language=None)
        with pytest.raises(ValidationError):
            await svc.update_language(None, user, "zz")

    @pytest.mark.asyncio
    async def test_empty_language_raises_validation_error(self):
        svc = _make_service()
        user = SimpleNamespace(id="u-1", language=None)
        with pytest.raises(ValidationError):
            await svc.update_language(None, user, "")


# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------


class TestDeleteUser:
    @pytest.mark.asyncio
    async def test_soft_deletes_by_setting_inactive(self):
        svc = _make_service()
        user = SimpleNamespace(id="u-del", is_active=True)
        await svc.delete_user(None, user)
        assert user.is_active is False
        assert len(svc._user_repo.active_set) == 1
        assert svc._user_repo.active_set[0] == (user, False)
