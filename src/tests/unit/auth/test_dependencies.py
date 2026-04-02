from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from ii_agent.auth import dependencies
from ii_agent.auth.exceptions import InvalidTokenException, UserNotFoundException
from ii_agent.auth.users.exceptions import UserDisabledException


class FakeUserRepo:
    def __init__(self, user):
        self.user = user

    async def get_by_id(self, db, user_id):
        return self.user


@pytest.mark.asyncio
async def test_get_current_user_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr(dependencies.jwt_handler, "verify_access_token", lambda _t: None)

    with pytest.raises(InvalidTokenException):
        await dependencies.get_current_user(
            db=None,
            user_repo=FakeUserRepo(user=None),
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad"),
        )


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_user(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        dependencies.jwt_handler,
        "verify_access_token",
        lambda _t: {
            "user_id": "u1",
            "email": "x@y.com",
            "role": "user",
            "type": "access",
            "exp": now + timedelta(minutes=5),
            "iat": now,
        },
    )

    with pytest.raises(UserNotFoundException):
        await dependencies.get_current_user(
            db=None,
            user_repo=FakeUserRepo(user=None),
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
        )


@pytest.mark.asyncio
async def test_get_current_user_rejects_disabled_user(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        dependencies.jwt_handler,
        "verify_access_token",
        lambda _t: {
            "user_id": "u1",
            "email": "x@y.com",
            "role": "user",
            "type": "access",
            "exp": now + timedelta(minutes=5),
            "iat": now,
        },
    )

    disabled_user = SimpleNamespace(id="u1", is_active=False)
    with pytest.raises(UserDisabledException):
        await dependencies.get_current_user(
            db=None,
            user_repo=FakeUserRepo(user=disabled_user),
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
        )
