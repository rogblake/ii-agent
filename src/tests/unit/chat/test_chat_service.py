from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.chat.service import ChatService
from ii_agent.sessions.exceptions import SessionNotFoundError


class FakeSessionRepo:
    def __init__(self, session=None):
        self.session = session

    async def get_by_id(self, db, session_id):
        return self.session

    async def get_public_by_id(self, db, session_id):
        return self.session if self.session and self.session.is_public else None


@pytest.fixture
def chat_service(settings_factory):
    return ChatService(
        file_processor=SimpleNamespace(_config=settings_factory()),
        tool_service=SimpleNamespace(),
        llm_loop=SimpleNamespace(),
        message_history=SimpleNamespace(),
        message_service=SimpleNamespace(),
        session_repo=FakeSessionRepo(),
        agent_run_service=SimpleNamespace(),
        llm_setting_service=SimpleNamespace(),
        credit_service=None,
        container=SimpleNamespace(),
    )


def test_truncate_session_name_limits_length(chat_service):
    text = "x" * 60

    result = chat_service._truncate_session_name(text, max_length=50)

    assert len(result) == 53
    assert result.endswith("...")


@pytest.mark.asyncio
async def test_update_session_name_if_untitled(chat_service):
    session = SimpleNamespace(name="Untitled")
    chat_service._session_repo.session = session

    class _DB:
        async def flush(self):
            return None

    await chat_service.update_session_name_if_untitled(
        db=_DB(),
        session_id="s1",
        query="New title",
    )

    assert session.name == "New title"


@pytest.mark.asyncio
async def test_validate_session_access_denies_non_owner(chat_service):
    chat_service._session_repo.session = SimpleNamespace(user_id="other")

    with pytest.raises(SessionNotFoundError):
        await chat_service.validate_session_access(
            db=None,
            session_id="s1",
            user_id="u1",
        )


@pytest.mark.asyncio
async def test_check_sufficient_credits_defaults_to_allow(chat_service):
    assert await chat_service.check_sufficient_credits(db=None, user_id="u1") is True
