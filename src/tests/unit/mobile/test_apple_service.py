from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from ii_agent.mobile.apple.models import AppleAuthStateEnum
from ii_agent.mobile.apple.service import AppleCredentialService


class FakeAppleRepo:
    def __init__(self):
        self.exact = None
        self.pending = None
        self.latest = None
        self.latest_authenticated = None

    async def get_by_user_and_apple_id(self, db, user_id, apple_id):
        if apple_id == "pending":
            return self.pending
        return self.exact

    async def get_latest_by_user(self, db, user_id):
        return self.latest

    async def get_latest_authenticated_by_user(self, db, user_id):
        return self.latest_authenticated


class FakeDB:
    def __init__(self):
        self.added = []
        self.deleted = []
        self.refreshed = []
        self.expunged = []
        self.flushed = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)

    def expunge(self, obj):
        self.expunged.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)


@pytest.mark.asyncio
async def test_save_or_update_credential_uses_pending_and_updates_fields(monkeypatch):
    repo = FakeAppleRepo()
    pending = SimpleNamespace(
        apple_id="pending",
        auth_state=AppleAuthStateEnum.PENDING_LOGIN.value,
        encrypted_session_data=None,
        selected_team_id=None,
        team_name=None,
        available_teams=None,
        session_expiry=None,
        updated_at=None,
    )
    repo.pending = pending
    service = AppleCredentialService(repo=repo)

    db = FakeDB()

    @asynccontextmanager
    async def _db_cm():
        yield db

    monkeypatch.setattr("ii_agent.mobile.apple.service.get_db_session_local", _db_cm)
    monkeypatch.setattr(
        "ii_agent.mobile.apple.service.encryption_manager.encrypt",
        lambda payload: f"enc:{payload}",
    )

    expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    result = await service.save_or_update_credential(
        user_id="u1",
        apple_id="real@apple.com",
        auth_state=AppleAuthStateEnum.AUTHENTICATED.value,
        session_data={"session": "abc"},
        team_id="team-1",
        team_name="Main Team",
        available_teams=[{"id": "team-1"}],
        session_expiry=expiry,
    )

    assert result is pending
    assert pending.apple_id == "real@apple.com"
    assert pending.auth_state == AppleAuthStateEnum.AUTHENTICATED.value
    assert pending.encrypted_session_data.startswith("enc:")
    assert pending.selected_team_id == "team-1"
    assert pending.team_name == "Main Team"
    assert pending.available_teams == [{"id": "team-1"}]
    assert pending.session_expiry == expiry
    assert db.flushed == 1
    assert db.refreshed == [pending]


@pytest.mark.asyncio
async def test_get_active_session_marks_expired_and_returns_none(monkeypatch):
    repo = FakeAppleRepo()
    expired = SimpleNamespace(
        auth_state=AppleAuthStateEnum.AUTHENTICATED.value,
        session_expiry=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    repo.latest_authenticated = expired
    service = AppleCredentialService(repo=repo)

    db = FakeDB()

    @asynccontextmanager
    async def _db_cm():
        yield db

    monkeypatch.setattr("ii_agent.mobile.apple.service.get_db_session_local", _db_cm)

    result = await service.get_active_session("u1")

    assert result is None
    assert expired.auth_state == AppleAuthStateEnum.EXPIRED.value
    assert db.flushed == 1


def test_get_decrypted_session_data_handles_null_and_parse_failures(monkeypatch):
    repo = FakeAppleRepo()
    service = AppleCredentialService(repo=repo)

    decrypted_map = {
        "enc-good": '{"token": "ok"}',
        "enc-bad": "{",
        "enc-empty": None,
    }
    monkeypatch.setattr(
        "ii_agent.mobile.apple.service.encryption_manager.decrypt",
        lambda value: decrypted_map.get(value),
    )

    assert service.get_decrypted_session_data(SimpleNamespace(encrypted_session_data=None)) is None
    assert service.get_decrypted_session_data(SimpleNamespace(encrypted_session_data="enc-empty")) is None
    assert service.get_decrypted_session_data(SimpleNamespace(encrypted_session_data="enc-bad")) is None
    assert service.get_decrypted_session_data(
        SimpleNamespace(encrypted_session_data="enc-good")
    ) == {"token": "ok"}


@pytest.mark.asyncio
async def test_save_and_get_expo_token_paths(monkeypatch):
    repo = FakeAppleRepo()
    repo.latest = None
    service = AppleCredentialService(repo=repo)

    db = FakeDB()

    @asynccontextmanager
    async def _db_cm():
        yield db

    monkeypatch.setattr("ii_agent.mobile.apple.service.get_db_session_local", _db_cm)
    monkeypatch.setattr(
        "ii_agent.mobile.apple.service.encryption_manager.encrypt",
        lambda value: f"enc:{value}",
    )
    monkeypatch.setattr(
        "ii_agent.mobile.apple.service.encryption_manager.decrypt",
        lambda value: value.replace("enc:", "", 1),
    )
    monkeypatch.setattr(
        "ii_agent.mobile.apple.service.AppleCredential",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    saved = await service.save_expo_token("u1", "ExponentPushToken[abc]")

    assert saved is True
    assert len(db.added) == 1
    created = db.added[0]
    assert created.apple_id == "pending"
    assert created.encrypted_expo_token == "enc:ExponentPushToken[abc]"
    assert service.get_decrypted_expo_token(created) == "ExponentPushToken[abc]"


@pytest.mark.asyncio
async def test_save_and_get_app_specific_password_paths(monkeypatch):
    repo = FakeAppleRepo()
    repo.latest = None
    service = AppleCredentialService(repo=repo)

    db = FakeDB()

    @asynccontextmanager
    async def _db_cm():
        yield db

    monkeypatch.setattr("ii_agent.mobile.apple.service.get_db_session_local", _db_cm)
    monkeypatch.setattr(
        "ii_agent.mobile.apple.service.encryption_manager.encrypt",
        lambda value: f"enc:{value}",
    )
    monkeypatch.setattr(
        "ii_agent.mobile.apple.service.encryption_manager.decrypt",
        lambda value: value.replace("enc:", "", 1),
    )
    monkeypatch.setattr(
        "ii_agent.mobile.apple.service.AppleCredential",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    saved = await service.save_app_specific_password("u1", "pass-1234")

    assert saved is True
    assert len(db.added) == 1
    created = db.added[0]
    assert created.apple_id == "pending"
    assert created.encrypted_app_specific_password == "enc:pass-1234"
    assert service.get_decrypted_app_specific_password(created) == "pass-1234"
