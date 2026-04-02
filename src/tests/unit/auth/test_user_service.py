from types import SimpleNamespace

import pytest

from ii_agent.auth.users.exceptions import UserDisabledException
from ii_agent.auth.users.service import UserService


class FakeUserRepo:
    def __init__(self):
        self.created = []
        self.updated = []
        self.by_email = {}

    async def get_by_id(self, db, user_id):
        return None

    async def get_by_email(self, db, email):
        return self.by_email.get(email)

    async def create(self, db, **kwargs):
        user = SimpleNamespace(id="user-1", is_active=True, **kwargs)
        self.created.append(kwargs)
        self.by_email[kwargs["email"]] = user
        return user

    async def update_profile(self, db, user, **kwargs):
        for key, value in kwargs.items():
            if value is not None:
                setattr(user, key, value)
        self.updated.append((user, kwargs))

    async def set_language(self, db, user, language):
        user.language = language

    async def set_active(self, db, user, is_active):
        user.is_active = is_active


class FakeAPIKeyRepo:
    def __init__(self):
        self.created = []

    async def create(self, db, user_id, api_key):
        self.created.append((user_id, api_key))
        return SimpleNamespace(id="key-1", api_key=api_key)

    async def get_active_for_user(self, db, user_id):
        return "active-key"


class FakeWaitlistRepo:
    def __init__(self):
        self.allowed = set()

    async def get_by_email(self, db, email):
        if email in self.allowed:
            return {"email": email}
        return None


@pytest.fixture
def user_service(settings_factory):
    config = settings_factory()
    return UserService(
        user_repo=FakeUserRepo(),
        api_key_repo=FakeAPIKeyRepo(),
        waitlist_repo=FakeWaitlistRepo(),
        config=config,
    )


@pytest.mark.asyncio
async def test_create_user_applies_defaults_and_creates_api_key(user_service):
    user = await user_service.create_user(
        db=None,
        email="demo@example.com",
        first_name="Demo",
    )

    assert user.email == "demo@example.com"
    assert len(user_service._user_repo.created) == 1
    assert user_service._user_repo.created[0]["credits"] == 10.0
    assert user_service._user_repo.created[0]["subscription_plan"] == "free"
    assert len(user_service._api_key_repo.created) == 1


@pytest.mark.asyncio
async def test_find_or_create_oauth_user_updates_existing_profile(user_service):
    existing = SimpleNamespace(
        id="u-1",
        email="demo@example.com",
        is_active=True,
        first_name="Old",
        last_name="Name",
        avatar=None,
        email_verified=False,
        login_provider=None,
    )
    user_service._user_repo.by_email[existing.email] = existing

    user = await user_service.find_or_create_oauth_user(
        db=None,
        email="demo@example.com",
        first_name="New",
        last_name="User",
    )

    assert user is existing
    assert user.first_name == "New"
    assert len(user_service._user_repo.created) == 0


@pytest.mark.asyncio
async def test_find_or_create_oauth_user_raises_for_disabled_user(user_service):
    user_service._user_repo.by_email["disabled@example.com"] = SimpleNamespace(
        id="u-2", email="disabled@example.com", is_active=False
    )

    with pytest.raises(UserDisabledException):
        await user_service.find_or_create_oauth_user(
            db=None,
            email="disabled@example.com",
        )
