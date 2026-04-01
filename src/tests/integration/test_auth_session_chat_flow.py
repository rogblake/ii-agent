from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.users.service import UserService
from ii_agent.chat.application.chat_service import ChatService
from ii_agent.sessions.service import SessionService
from ii_agent.sessions.title_service import SessionTitleService
from ii_agent.core.config.session_title import SessionTitleConfig

pytestmark = pytest.mark.integration


class UserRepo:
    def __init__(self):
        self.users = {}

    async def create(self, db, **kwargs):
        user = SimpleNamespace(id="u1", is_active=True, **kwargs)
        self.users[user.email] = user
        return user

    async def get_by_email(self, db, email):
        return self.users.get(email)

    async def update_profile(self, db, user, **kwargs):
        for key, value in kwargs.items():
            if value is not None:
                setattr(user, key, value)

    async def get_by_id(self, db, user_id):
        return next((u for u in self.users.values() if u.id == user_id), None)


class APIKeyRepo:
    async def create(self, db, user_id, api_key):
        return SimpleNamespace(api_key=api_key)


class WaitlistRepo:
    async def get_by_email(self, db, email):
        return {"email": email}


class FakeCreditService:
    async def ensure_balance_exists(self, db, user_id, **kwargs):
        from decimal import Decimal

        credits = Decimal(str(kwargs.get("credits", 0)))
        bonus = Decimal(str(kwargs.get("bonus_credits", 0)))
        return (credits, bonus)


class SessionRepo:
    def __init__(self):
        self.sessions = {}

    async def create(self, db, session):
        from datetime import datetime, timezone

        if session.created_at is None:
            session.created_at = datetime.now(timezone.utc)
        if session.updated_at is None:
            session.updated_at = datetime.now(timezone.utc)
        if session.is_public is None:
            session.is_public = False
        self.sessions[session.id] = session
        return session

    async def get_by_id(self, db, session_id):
        return self.sessions.get(session_id)


@pytest.mark.asyncio
async def test_auth_session_chat_flow(settings_factory):
    user_service = UserService(
        user_repo=UserRepo(),
        api_key_repo=APIKeyRepo(),
        waitlist_repo=WaitlistRepo(),
        credit_service=FakeCreditService(),
        config=settings_factory(),
    )

    user = await user_service.find_or_create_oauth_user(
        db=None,
        email="user@example.com",
        first_name="First",
    )

    session_service = SessionService(
        session_repo=SessionRepo(),
        event_repo=SimpleNamespace(),
        run_task_service=SimpleNamespace(),
        file_store=SimpleNamespace(get_download_signed_url=lambda path: f"signed:{path}"),
        sandbox_repo=SimpleNamespace(),
        config=settings_factory(),
    )

    session_info = await session_service.create_new_session(
        db=None,
        session_uuid=uuid4(),
        user_id=user.id,
        api_version="v1",
    )

    chat_service = ChatService(
        file_processor=SimpleNamespace(_config=settings_factory()),
        tool_service=SimpleNamespace(),
        llm_loop=SimpleNamespace(),
        message_history=SimpleNamespace(),
        message_service=SimpleNamespace(),
        session_repo=session_service._session_repo,
        model_setting_service=SimpleNamespace(),
        credit_service=None,
        container=SimpleNamespace(),
        title_service=SessionTitleService(config=SessionTitleConfig(openai_api_key=None)),
    )

    class _DB:
        async def flush(self):
            return None

    await chat_service.update_session_name_if_untitled(
        db=_DB(),
        session_id=str(session_info.id),
        query="Build dashboard app",
    )

    assert str(session_info.id) in session_service._session_repo.sessions
