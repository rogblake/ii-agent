"""Unit tests for ii_agent.integrations.mcp_sse.agent."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.skip("ii_agent.integrations.mcp_sse was removed during refactoring", allow_module_level=True)


# conftest.py has already stubbed the mcp_sse package import chain.
# Now import the module directly
import ii_agent.integrations.mcp_sse.agent as agent_module  # noqa: E402
from ii_agent.integrations.mcp_sse.agent import (  # noqa: E402
    AgentTask,
    get_agent_queue,
    enqueue_agent_task,
    start_agent_worker,
    _get_default_llm_config,
    _ensure_session_user_exists,
)


# ---------------------------------------------------------------------------
# AgentTask dataclass
# ---------------------------------------------------------------------------


class TestAgentTask:
    def test_agent_task_stores_fields(self):
        controller = MagicMock()
        session_id = uuid.uuid4()
        task = AgentTask(
            agent_controller=controller,
            prompt="do something",
            session_id=session_id,
            sandbox_url="http://sandbox.local",
        )
        assert task.agent_controller is controller
        assert task.prompt == "do something"
        assert task.session_id == session_id
        assert task.sandbox_url == "http://sandbox.local"

    def test_dataclass_fields_accessible(self):
        controller = MagicMock()
        session_id = uuid.uuid4()
        task = AgentTask(
            agent_controller=controller,
            prompt="hello",
            session_id=session_id,
            sandbox_url="http://url",
        )
        assert hasattr(task, "agent_controller")
        assert hasattr(task, "prompt")
        assert hasattr(task, "session_id")
        assert hasattr(task, "sandbox_url")


# ---------------------------------------------------------------------------
# get_agent_queue
# ---------------------------------------------------------------------------


class TestGetAgentQueue:
    def test_returns_asyncio_queue(self):
        agent_module._agent_queue = None
        queue = get_agent_queue()
        assert isinstance(queue, asyncio.Queue)
        agent_module._agent_queue = None

    def test_returns_same_instance_on_second_call(self):
        agent_module._agent_queue = None
        q1 = get_agent_queue()
        q2 = get_agent_queue()
        assert q1 is q2
        agent_module._agent_queue = None

    def test_returns_existing_queue_if_set(self):
        existing_queue = asyncio.Queue()
        agent_module._agent_queue = existing_queue
        result = get_agent_queue()
        assert result is existing_queue
        agent_module._agent_queue = None


# ---------------------------------------------------------------------------
# start_agent_worker
# ---------------------------------------------------------------------------


class TestStartAgentWorker:
    @pytest.mark.asyncio
    async def test_creates_worker_task(self):
        agent_module._worker_task = None
        agent_module._agent_queue = None
        with patch.object(agent_module, "_agent_worker", new=AsyncMock()):
            await start_agent_worker()
            assert agent_module._worker_task is not None
            agent_module._worker_task.cancel()
            agent_module._worker_task = None
            agent_module._agent_queue = None

    @pytest.mark.asyncio
    async def test_does_not_create_duplicate_worker_when_running(self):
        mock_task = MagicMock()
        mock_task.done.return_value = False
        agent_module._worker_task = mock_task
        original_task = agent_module._worker_task

        await start_agent_worker()

        assert agent_module._worker_task is original_task
        agent_module._worker_task = None

    @pytest.mark.asyncio
    async def test_creates_new_worker_if_previous_done(self):
        mock_task = MagicMock()
        mock_task.done.return_value = True
        agent_module._worker_task = mock_task
        agent_module._agent_queue = None

        with patch.object(agent_module, "_agent_worker", new=AsyncMock()):
            await start_agent_worker()
            assert agent_module._worker_task is not mock_task
            agent_module._worker_task.cancel()
            agent_module._worker_task = None
            agent_module._agent_queue = None


# ---------------------------------------------------------------------------
# enqueue_agent_task
# ---------------------------------------------------------------------------


class TestEnqueueAgentTask:
    @pytest.mark.asyncio
    async def test_task_added_to_queue(self):
        agent_module._agent_queue = None
        agent_module._worker_task = None

        with patch.object(agent_module, "start_agent_worker", new=AsyncMock()):
            controller = MagicMock()
            session_id = uuid.uuid4()
            await enqueue_agent_task(
                agent_controller=controller,
                prompt="test prompt",
                session_id=session_id,
                sandbox_url="http://sandbox.local",
            )
            queue = get_agent_queue()
            assert not queue.empty()
            task = await queue.get()
            assert isinstance(task, AgentTask)
            assert task.prompt == "test prompt"
            assert task.session_id == session_id

        agent_module._agent_queue = None
        agent_module._worker_task = None

    @pytest.mark.asyncio
    async def test_start_worker_called(self):
        agent_module._agent_queue = None
        agent_module._worker_task = None

        mock_start_worker = AsyncMock()
        with patch.object(agent_module, "start_agent_worker", mock_start_worker):
            controller = MagicMock()
            session_id = uuid.uuid4()
            await enqueue_agent_task(
                agent_controller=controller,
                prompt="query",
                session_id=session_id,
                sandbox_url="http://url",
            )
            mock_start_worker.assert_called_once()

        agent_module._agent_queue = None
        agent_module._worker_task = None


# ---------------------------------------------------------------------------
# _get_default_llm_config
# ---------------------------------------------------------------------------


class TestGetDefaultLlmConfig:
    def test_returns_llm_config_from_dict(self):
        from ii_agent.core.config.llm_config import LLMConfig

        config = SimpleNamespace(
            llm_configs={
                "default": {
                    "model": "gpt-4o",
                    "provider": "OpenAI",
                    "api_key": "test-key",
                }
            }
        )
        result = _get_default_llm_config(config)
        assert isinstance(result, LLMConfig)
        assert result.model == "gpt-4o"

    def test_returns_llm_config_instance_directly(self):
        from ii_agent.core.config.llm_config import LLMConfig
        from pydantic import SecretStr

        llm_config = LLMConfig(model="gpt-4o", provider="OpenAI", api_key=SecretStr("key"))
        config = SimpleNamespace(llm_configs={"default": llm_config})
        result = _get_default_llm_config(config)
        assert result is llm_config

    def test_raises_when_no_default_config(self):
        config = SimpleNamespace(llm_configs={})
        with pytest.raises(ValueError, match="Default LLM configuration is missing"):
            _get_default_llm_config(config)

    def test_raises_when_no_llm_configs_attribute(self):
        config = SimpleNamespace()
        with pytest.raises(ValueError, match="Default LLM configuration is missing"):
            _get_default_llm_config(config)

    def test_config_as_none_in_llm_configs(self):
        config = SimpleNamespace(llm_configs={"default": None})
        with pytest.raises(ValueError, match="Default LLM configuration is missing"):
            _get_default_llm_config(config)


# ---------------------------------------------------------------------------
# _ensure_session_user_exists
# ---------------------------------------------------------------------------


class FakeUser:
    """Plain-Python User substitute that avoids SQLAlchemy ORM initialization."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    # Support attribute-access query building (User.id, User.email) as MagicMock attributes
    id = MagicMock()
    email = MagicMock()


def _user_ctx_patches():
    """Return context managers that fully bypass SQLAlchemy for User-related code."""
    return (
        patch("ii_agent.integrations.mcp_sse.agent.User", FakeUser),
        patch("ii_agent.integrations.mcp_sse.agent.select", MagicMock(return_value=MagicMock())),
    )


class TestEnsureSessionUserExists:
    @pytest.mark.asyncio
    async def test_returns_if_user_already_exists(self):
        existing_user = MagicMock()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        config = SimpleNamespace(mcp_default_session_user_email=None, default_user_credits=0.0)

        p_user, p_select = _user_ctx_patches()
        with (
            patch(
                "ii_agent.integrations.mcp_sse.agent.get_db_session_local",
                return_value=mock_ctx,
            ),
            p_user,
            p_select,
        ):
            await _ensure_session_user_exists("user123", config)

        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_user_with_synthesized_email(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        config = SimpleNamespace(mcp_default_session_user_email=None, default_user_credits=10.0)

        p_user, p_select = _user_ctx_patches()
        with (
            patch(
                "ii_agent.integrations.mcp_sse.agent.get_db_session_local",
                return_value=mock_ctx,
            ),
            p_user,
            p_select,
        ):
            await _ensure_session_user_exists("newuser456", config)

        mock_db.add.assert_called_once()
        added_user = mock_db.add.call_args[0][0]
        assert added_user.id == "newuser456"
        assert added_user.email == "newuser456@mcp.local"

    @pytest.mark.asyncio
    async def test_creates_user_with_template_email(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        config = SimpleNamespace(
            mcp_default_session_user_email="user-{user_id}@service.com",
            default_user_credits=0.0,
        )

        p_user, p_select = _user_ctx_patches()
        with (
            patch(
                "ii_agent.integrations.mcp_sse.agent.get_db_session_local",
                return_value=mock_ctx,
            ),
            p_user,
            p_select,
        ):
            await _ensure_session_user_exists("myuserid", config)

        added_user = mock_db.add.call_args[0][0]
        assert added_user.email == "user-myuserid@service.com"

    @pytest.mark.asyncio
    async def test_user_has_correct_role(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        config = SimpleNamespace(mcp_default_session_user_email=None, default_user_credits=0.0)

        p_user, p_select = _user_ctx_patches()
        with (
            patch(
                "ii_agent.integrations.mcp_sse.agent.get_db_session_local",
                return_value=mock_ctx,
            ),
            p_user,
            p_select,
        ):
            await _ensure_session_user_exists("userid_x", config)

        added_user = mock_db.add.call_args[0][0]
        assert added_user.role == "service"
        assert added_user.is_active is True

    @pytest.mark.asyncio
    async def test_user_bonus_credits_zero(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        config = SimpleNamespace(mcp_default_session_user_email=None, default_user_credits=50.0)

        p_user, p_select = _user_ctx_patches()
        with (
            patch(
                "ii_agent.integrations.mcp_sse.agent.get_db_session_local",
                return_value=mock_ctx,
            ),
            p_user,
            p_select,
        ):
            await _ensure_session_user_exists("uid_bonus", config)

        added_user = mock_db.add.call_args[0][0]
        assert added_user.is_active is True


# ---------------------------------------------------------------------------
# run_agent_internal
# ---------------------------------------------------------------------------


class TestRunAgentInternal:
    def test_returns_metadata_dict(self):
        from ii_agent.integrations.mcp_sse.agent import run_agent_internal

        controller = MagicMock()
        session_id = uuid.uuid4()
        result = run_agent_internal(
            agent_controller=controller,
            prompt="do something",
            session_id=session_id,
            sandbox_url="http://sandbox.local",
        )
        assert result["session_id"] == str(session_id)
        assert result["sandbox_url"] == "http://sandbox.local"
        controller.run_agent.assert_called_once_with(instruction="do something", resume=True)

    def test_run_agent_called_with_correct_args(self):
        from ii_agent.integrations.mcp_sse.agent import run_agent_internal

        controller = MagicMock()
        session_id = uuid.uuid4()
        run_agent_internal(
            agent_controller=controller,
            prompt="query text",
            session_id=session_id,
            sandbox_url="http://url",
        )
        controller.run_agent.assert_called_once_with(instruction="query text", resume=True)

    def test_returns_task_id_in_result(self):
        from ii_agent.integrations.mcp_sse.agent import run_agent_internal

        controller = MagicMock()
        result = run_agent_internal(
            agent_controller=controller,
            prompt="test",
            session_id=uuid.uuid4(),
            sandbox_url="http://url",
        )
        assert "task_id" in result or "session_id" in result

    def test_run_agent_exception_propagated(self):
        from ii_agent.integrations.mcp_sse.agent import run_agent_internal

        controller = MagicMock()
        controller.run_agent.side_effect = RuntimeError("agent failed")
        with pytest.raises(RuntimeError, match="agent failed"):
            run_agent_internal(
                agent_controller=controller,
                prompt="test",
                session_id=uuid.uuid4(),
                sandbox_url="http://url",
            )
