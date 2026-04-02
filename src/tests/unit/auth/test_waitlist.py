import pytest

from ii_agent.auth.users.exceptions import WaitlistDeniedException
from ii_agent.auth.users.service import UserService


class _Repo:
    async def get_by_email(self, db, email):
        return None


class _WaitlistRepo:
    def __init__(self, allowed=None):
        self.allowed = set(allowed or [])

    async def get_by_email(self, db, email):
        return {"email": email} if email in self.allowed else None


@pytest.mark.asyncio
async def test_waitlist_disabled_allows_all(settings_factory):
    service = UserService(
        user_repo=_Repo(),
        api_key_repo=_Repo(),
        waitlist_repo=_WaitlistRepo(),
        config=settings_factory(credits={"waitlist_enabled": False}),
    )

    await service.check_waitlist(None, "user@example.com")


@pytest.mark.asyncio
async def test_waitlist_allows_internal_domain(settings_factory):
    service = UserService(
        user_repo=_Repo(),
        api_key_repo=_Repo(),
        waitlist_repo=_WaitlistRepo(),
        config=settings_factory(credits={"waitlist_enabled": True}),
    )

    await service.check_waitlist(None, "employee@ii.inc")


@pytest.mark.asyncio
async def test_waitlist_rejects_non_whitelisted_email(settings_factory):
    service = UserService(
        user_repo=_Repo(),
        api_key_repo=_Repo(),
        waitlist_repo=_WaitlistRepo(),
        config=settings_factory(credits={"waitlist_enabled": True}),
    )

    with pytest.raises(WaitlistDeniedException):
        await service.check_waitlist(None, "blocked@example.com")
