from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.agent.application.validation_service import SessionValidationService
from ii_agent.sessions.title_service import SessionTitleService
from ii_agent.sessions.title_config import SessionTitleConfig


class FakeSessionService:
    def __init__(self, session):
        self.session = session

    async def get_session_by_id(self, db, session_id):
        return self.session


class FakeBalanceRepo:
    def __init__(self, *, credits=10.0, bonus=0.0, status="ok"):
        self._credits = credits
        self._bonus = bonus
        self._status = status

    async def get_balance_state(self, db, user_id):
        return (self._credits, self._bonus, self._status)

    async def get_billing_status(self, db, user_id):
        return self._status


# Note: FakeBalanceRepo stores status as a plain string. BillingStatus is a
# str enum, so ``BillingStatus.OK == "ok"`` is True — both sides compare fine.


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


@pytest.mark.asyncio
async def test_validate_session_returns_error_when_session_missing():
    service = SessionValidationService(
        session_service=FakeSessionService(session=None),
        title_service=SessionTitleService(config=SessionTitleConfig(openai_api_key=None)),
    )

    result = await service.validate_and_prepare_session(
        db=FakeDB(),
        session_id=uuid4(),
        llm_setting_service=FakeLLMSettingService(
            LLMConfig(model="gpt-4o", api_type="openai")
        ),
    )

    assert result.is_valid is False
    assert result.error_type == "unexpected_error"


@pytest.mark.asyncio
async def test_validate_session_bypasses_billing_check_for_user_model(settings_factory, monkeypatch):
    monkeypatch.setattr(
        "ii_agent.agent.application.validation_service.SessionService._build_session_info",
        lambda _session: SimpleNamespace(
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
        agent_state_path="/workspace/state",
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

    service = SessionValidationService(
        session_service=FakeSessionService(session=session),
        title_service=SessionTitleService(config=SessionTitleConfig(openai_api_key=None)),
    )

    result = await service.validate_and_prepare_session(
        db=FakeDB(),
        session_id=uuid4(),
        query_text="hello",
        llm_setting_service=FakeLLMSettingService(llm_config),
    )

    assert result.is_valid is True
    assert result.llm_config.config_type == "user"


@pytest.mark.asyncio
async def test_validate_session_rejects_reconciliation_required(settings_factory, monkeypatch):
    """Users with billing_status != 'ok' are blocked before agent work starts."""
    monkeypatch.setattr(
        "ii_agent.agent.application.validation_service.SessionService._build_session_info",
        lambda _session: SimpleNamespace(
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
        agent_state_path="/workspace/state",
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

    service = SessionValidationService(
        session_service=FakeSessionService(session=session),
        balance_repo=FakeBalanceRepo(credits=100, bonus=0, status="reconciliation_required"),
        title_service=SessionTitleService(config=SessionTitleConfig(openai_api_key=None)),
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
async def test_validate_session_does_not_precheck_credit_amount(settings_factory, monkeypatch):
    """Low balances should still reach the runtime reservation gate when status is healthy."""
    monkeypatch.setattr(
        "ii_agent.agent.application.validation_service.SessionService._build_session_info",
        lambda _session: SimpleNamespace(
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
        agent_state_path="/workspace/state",
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

    service = SessionValidationService(
        session_service=FakeSessionService(session=session),
        balance_repo=FakeBalanceRepo(credits=0, bonus=0, status="ok"),
        title_service=SessionTitleService(config=SessionTitleConfig(openai_api_key=None)),
    )

    result = await service.validate_and_prepare_session(
        db=FakeDB(),
        session_id=uuid4(),
        query_text="hello",
        llm_setting_service=FakeLLMSettingService(llm_config),
    )

    assert result.is_valid is True
    assert result.error_type is None
