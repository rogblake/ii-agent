from types import SimpleNamespace

import pytest

from ii_agent.chat.application.chat_service import ChatService
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.title_service import SessionTitleService
from ii_agent.core.config.session_title import SessionTitleConfig


class FakeSessionRepo:
    def __init__(self, session=None):
        self.session = session

    async def get_by_id(self, db, session_id):
        return self.session

    async def create(self, db, session):
        self.session = session
        return session

    async def get_public_by_id(self, db, session_id):
        return self.session if self.session and self.session.is_public else None


@pytest.fixture
def title_service():
    config = SessionTitleConfig(openai_api_key=None)
    return SessionTitleService(config=config)


@pytest.fixture
def chat_service(settings_factory, title_service):
    return ChatService(
        file_processor=SimpleNamespace(_config=settings_factory()),
        tool_service=SimpleNamespace(),
        llm_loop=SimpleNamespace(),
        message_history=SimpleNamespace(),
        message_service=SimpleNamespace(),
        session_repo=FakeSessionRepo(),
        model_setting_service=SimpleNamespace(),
        credit_service=None,
        container=SimpleNamespace(),
        title_service=title_service,
    )


def test_truncate_session_name_limits_length():
    text = "x" * 90

    result = SessionTitleService._truncate(text, max_length=80)

    assert len(result) == 83
    assert result.endswith("...")


def test_build_initial_title_marks_pending_when_llm_available(title_service):
    title_service._client = object()

    name, title_pending = title_service.build_initial_title(
        "Generate a project plan with milestones, success metrics, delivery phases, "
        "risk mitigation, staffing assumptions, and launch readiness checkpoints."
    )

    assert name is None
    assert title_pending is True


def test_build_initial_title_uses_truncation_for_short_query_even_when_llm_available(
    title_service,
):
    title_service._client = object()

    name, title_pending = title_service.build_initial_title("Generate a project plan")

    assert name == "Generate a project plan"
    assert title_pending is False


@pytest.mark.asyncio
async def test_generate_title_skips_llm_for_short_query(monkeypatch):
    service = SessionTitleService(
        config=SessionTitleConfig(
            openai_api_key="test-key",
            semantic_min_query_length=100,
        )
    )

    async def _unexpected_llm_call(_query):
        raise AssertionError("LLM title generation should not run for short queries")

    monkeypatch.setattr(service, "_call_llm", _unexpected_llm_call)

    result = await service.generate_title("Generate a project plan")

    assert result == "Generate a project plan"


@pytest.mark.asyncio
async def test_background_title_update_retries_with_truncation_fallback(monkeypatch):
    service = SessionTitleService(
        config=SessionTitleConfig(
            openai_api_key="test-key",
            semantic_min_query_length=100,
        )
    )
    query = "x" * 120
    fallback_title = SessionTitleService._truncate(query, max_length=80)
    attempts: list[str] = []

    async def _fake_generate_title(_query, _max_length=80):
        return "Semantic title"

    async def _fake_persist_title_update(_session_id: str, title: str) -> bool:
        attempts.append(title)
        if len(attempts) == 1:
            raise RuntimeError("commit failed")
        return True

    monkeypatch.setattr(service, "generate_title", _fake_generate_title)
    monkeypatch.setattr(service, "_persist_title_update", _fake_persist_title_update)

    await service._background_title_update("session-1", query, 80)

    assert attempts == ["Semantic title", fallback_title]


@pytest.mark.asyncio
async def test_create_chat_session_commits_before_scheduling_title_update(
    chat_service,
    monkeypatch,
):
    chat_service._title_service._client = object()
    steps: list[str] = []

    class _DB:
        async def commit(self):
            steps.append("commit")

    def _schedule_title_update(_session_id: str, _query: str, _max_length: int = 80):
        steps.append("schedule")

    monkeypatch.setattr(
        chat_service._title_service,
        "schedule_title_update",
        _schedule_title_update,
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.chat_service.Session",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    await chat_service.create_chat_session(
        db=_DB(),
        user_message=(
            "Generate a project plan with milestones, success metrics, delivery phases, "
            "risk mitigation, staffing assumptions, and launch readiness checkpoints."
        ),
        user_id="u1",
        model_id="gpt-5-mini",
    )

    assert steps == ["commit", "schedule"]


def test_set_title_pending_round_trips_metadata():
    metadata = SessionTitleService.set_title_pending({"foo": "bar"}, True)

    assert metadata == {"foo": "bar", "title_pending": True}
    assert SessionTitleService.is_title_pending(metadata) is True
    assert SessionTitleService.set_title_pending(metadata, False) == {"foo": "bar"}


@pytest.mark.asyncio
async def test_update_session_name_if_untitled(chat_service):
    session = SimpleNamespace(name="Untitled")
    chat_service._session_repo.session = session

    class _DB:
        async def commit(self):
            return None

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
