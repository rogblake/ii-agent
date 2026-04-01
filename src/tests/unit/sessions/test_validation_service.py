from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.sessions.service import SessionService
from ii_agent.sessions.title_service import SessionTitleService
from ii_agent.core.config.session_title import SessionTitleConfig


class FakeSessionRepo:
    """Minimal repo that returns a pre-configured session ORM object."""

    def __init__(self, session):
        self._session = session

    async def get_by_id_with_project(self, db, session_id):
        return self._session

    async def get_by_id(self, db, session_id):
        return self._session

    async def update(self, db, session):
        pass

    async def create(self, db, session):
        return session


class FakeBalanceRepo:
    def __init__(self, *, credits=10.0, bonus=0.0, status="ok"):
        self._credits = credits
        self._bonus = bonus
        self._status = status

    async def get_balance_state(self, db, user_id):
        return (self._credits, self._bonus, self._status)

    async def get_billing_status(self, db, user_id):
        return self._status


class FakeLLMSettingService:
    def __init__(self, llm_config):
        self.llm_config = llm_config

    async def get_llm_settings(self, db, session, source, model_id):
        return self.llm_config


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, obj):
        return None

    async def commit(self):
        return None


def _make_service(session=None, balance_repo=None):
    return SessionService(
        session_repo=FakeSessionRepo(session),
        event_repo=SimpleNamespace(),
        run_task_service=SimpleNamespace(),
        file_store=SimpleNamespace(),
        sandbox_repo=SimpleNamespace(),
        config=SimpleNamespace(session_title=SimpleNamespace(openai_api_key=None)),
        title_service=SessionTitleService(config=SessionTitleConfig(openai_api_key=None)),
        balance_repo=balance_repo,
    )


@pytest.mark.asyncio
async def test_validate_session_returns_error_when_session_missing():
    service = _make_service(session=None)

    result = await service.validate_and_prepare_session(
        db=FakeDB(),
        session_id=uuid4(),
        llm_setting_service=FakeLLMSettingService(LLMConfig(model="gpt-4o", api_type="openai")),
    )

    assert result.is_valid is False
    assert result.error_type == "unexpected_error"


@pytest.mark.asyncio
async def test_validate_session_bypasses_billing_check_for_user_model(monkeypatch):
    monkeypatch.setattr(
        "ii_agent.sessions.service.SessionService._build_session_info",
        lambda _session, **kw: SimpleNamespace(
            id=str(uuid4()),
            user_id="u1",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            workspace_dir="/workspace",
            is_public=False,
            agent_type=None,
            llm_setting_id=None,
        ),
    )

    session = SimpleNamespace(
        id=str(uuid4()),
        user_id="u1",
        status="active",
        created_at=None,
        updated_at=None,
        api_version="v1",
        name="session",
        agent_type=None,
        llm_setting_id=None,
        session_metadata={},
        is_public=False,
        public_url=None,
        summary_message_id=None,
        parent_session_id=None,
        prompt_tokens=0,
        completion_tokens=0,
        cost=0.0,
    )
    llm_config = LLMConfig(model="gpt-4o", api_type="openai", config_type="user")

    service = _make_service(session=session)

    result = await service.validate_and_prepare_session(
        db=FakeDB(),
        session_id=uuid4(),
        query_text="hello",
        llm_setting_service=FakeLLMSettingService(llm_config),
    )

    assert result.is_valid is True
    assert result.llm_config.config_type == "user"


@pytest.mark.asyncio
async def test_validate_session_rejects_reconciliation_required(monkeypatch):
    """Users with billing_status != 'ok' are blocked before agent work starts."""
    monkeypatch.setattr(
        "ii_agent.sessions.service.SessionService._build_session_info",
        lambda _session, **kw: SimpleNamespace(
            id=str(uuid4()),
            user_id="u1",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            workspace_dir="/workspace",
            is_public=False,
            agent_type=None,
            llm_setting_id=None,
        ),
    )

    session = SimpleNamespace(
        id=str(uuid4()),
        user_id="u1",
        status="active",
        created_at=None,
        updated_at=None,
        api_version="v1",
        name="session",
        agent_type=None,
        llm_setting_id=None,
        session_metadata={},
        is_public=False,
        public_url=None,
        summary_message_id=None,
        parent_session_id=None,
        prompt_tokens=0,
        completion_tokens=0,
        cost=0.0,
    )
    llm_config = LLMConfig(model="gpt-4o", api_type="openai")

    service = _make_service(
        session=session,
        balance_repo=FakeBalanceRepo(credits=100, bonus=0, status="reconciliation_required"),
    )

    result = await service.validate_and_prepare_session(
        db=FakeDB(),
        session_id=uuid4(),
        query_text="hello",
        llm_setting_service=FakeLLMSettingService(llm_config),
    )

    assert result.is_valid is False
    assert result.error_type == "billing_reconciliation_required"


@pytest.mark.asyncio
async def test_validate_session_does_not_precheck_credit_amount(monkeypatch):
    """Low balances should still reach the runtime reservation gate when status is healthy."""
    monkeypatch.setattr(
        "ii_agent.sessions.service.SessionService._build_session_info",
        lambda _session, **kw: SimpleNamespace(
            id=str(uuid4()),
            user_id="u1",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            workspace_dir="/workspace",
            is_public=False,
            agent_type=None,
            llm_setting_id=None,
        ),
    )

    session = SimpleNamespace(
        id=str(uuid4()),
        user_id="u1",
        status="active",
        created_at=None,
        updated_at=None,
        api_version="v1",
        name="session",
        agent_type=None,
        llm_setting_id=None,
        session_metadata={},
        is_public=False,
        public_url=None,
        summary_message_id=None,
        parent_session_id=None,
        prompt_tokens=0,
        completion_tokens=0,
        cost=0.0,
    )
    llm_config = LLMConfig(model="gpt-4o", api_type="openai")

    service = _make_service(
        session=session,
        balance_repo=FakeBalanceRepo(credits=0, bonus=0, status="ok"),
    )

    result = await service.validate_and_prepare_session(
        db=FakeDB(),
        session_id=uuid4(),
        query_text="hello",
        llm_setting_service=FakeLLMSettingService(llm_config),
    )

    assert result.is_valid is True
    assert result.error_type is None
