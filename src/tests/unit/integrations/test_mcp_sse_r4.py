"""Unit tests for mcp_sse agent and widgets (r4)."""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# mcp_sse/agent.py
# ===========================================================================

class TestGetAgentQueue:
    def test_returns_asyncio_queue(self):
        import asyncio
        # Reset global state
        import ii_agent.integrations.mcp_sse.agent as agent_mod
        original = agent_mod._agent_queue
        try:
            agent_mod._agent_queue = None
            queue = agent_mod.get_agent_queue()
            assert isinstance(queue, asyncio.Queue)
        finally:
            agent_mod._agent_queue = original

    def test_returns_same_queue_on_second_call(self):
        import ii_agent.integrations.mcp_sse.agent as agent_mod
        original = agent_mod._agent_queue
        try:
            agent_mod._agent_queue = None
            q1 = agent_mod.get_agent_queue()
            q2 = agent_mod.get_agent_queue()
            assert q1 is q2
        finally:
            agent_mod._agent_queue = original


class TestStartAgentWorker:
    @pytest.mark.asyncio
    async def test_creates_worker_task(self):
        import asyncio
        import ii_agent.integrations.mcp_sse.agent as agent_mod
        original = agent_mod._worker_task
        try:
            agent_mod._worker_task = None
            await agent_mod.start_agent_worker()
            assert agent_mod._worker_task is not None
            agent_mod._worker_task.cancel()
            try:
                await agent_mod._worker_task
            except (asyncio.CancelledError, Exception):
                pass
        finally:
            agent_mod._worker_task = original

    @pytest.mark.asyncio
    async def test_does_not_create_duplicate_worker(self):
        import asyncio
        import ii_agent.integrations.mcp_sse.agent as agent_mod
        original = agent_mod._worker_task
        try:
            agent_mod._worker_task = None
            await agent_mod.start_agent_worker()
            task1 = agent_mod._worker_task
            await agent_mod.start_agent_worker()
            task2 = agent_mod._worker_task
            assert task1 is task2
            task1.cancel()
            try:
                await task1
            except (asyncio.CancelledError, Exception):
                pass
        finally:
            agent_mod._worker_task = original


class TestEnqueueAgentTask:
    @pytest.mark.asyncio
    async def test_puts_task_in_queue(self):
        import asyncio
        import ii_agent.integrations.mcp_sse.agent as agent_mod

        mock_controller = MagicMock()
        session_id = uuid.uuid4()
        original_queue = agent_mod._agent_queue
        original_worker = agent_mod._worker_task

        try:
            agent_mod._agent_queue = asyncio.Queue()
            agent_mod._worker_task = MagicMock()
            agent_mod._worker_task.done.return_value = False

            await agent_mod.enqueue_agent_task(
                agent_controller=mock_controller,
                prompt="test prompt",
                session_id=session_id,
                sandbox_url="http://sandbox.example.com",
            )
            assert agent_mod._agent_queue.qsize() == 1
            task = agent_mod._agent_queue.get_nowait()
            assert task.prompt == "test prompt"
            assert task.session_id == session_id
        finally:
            agent_mod._agent_queue = original_queue
            agent_mod._worker_task = original_worker


class TestGetDefaultLlmConfig:
    def test_returns_llm_config_when_present(self):
        from ii_agent.integrations.mcp_sse.agent import _get_default_llm_config
        from ii_agent.core.config.llm_config import LLMConfig

        mock_llm_config = MagicMock(spec=LLMConfig)

        mock_config = MagicMock()
        mock_config.llm_configs = {"default": mock_llm_config}

        result = _get_default_llm_config(mock_config)
        assert result is mock_llm_config

    def test_validates_dict_config(self):
        from ii_agent.integrations.mcp_sse.agent import _get_default_llm_config
        from ii_agent.core.config.llm_config import LLMConfig

        llm_config_dict = {
            "model": "claude-3-5-sonnet-20241022",
            "provider": "anthropic",
            "api_key": "test-key",
        }
        mock_config = MagicMock()
        mock_config.llm_configs = {"default": llm_config_dict}

        with patch.object(LLMConfig, "model_validate", return_value=MagicMock(spec=LLMConfig)) as mock_validate:
            result = _get_default_llm_config(mock_config)
            mock_validate.assert_called_once_with(llm_config_dict)

    def test_raises_when_default_missing(self):
        from ii_agent.integrations.mcp_sse.agent import _get_default_llm_config

        mock_config = MagicMock()
        mock_config.llm_configs = {}

        with pytest.raises(ValueError, match="Default LLM configuration is missing"):
            _get_default_llm_config(mock_config)

    def test_raises_when_llm_configs_none(self):
        from ii_agent.integrations.mcp_sse.agent import _get_default_llm_config

        mock_config = MagicMock()
        mock_config.llm_configs = None

        # When llm_configs is None, getattr returns None, then None.get("default") raises AttributeError
        with pytest.raises((ValueError, AttributeError, TypeError)):
            _get_default_llm_config(mock_config)


class TestEnsureSessionUserExists:
    @pytest.mark.asyncio
    async def test_does_nothing_when_user_exists(self):
        from ii_agent.integrations.mcp_sse.agent import _ensure_session_user_exists

        mock_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_config = MagicMock()
        mock_config.mcp_default_session_user_email = None

        with patch("ii_agent.integrations.mcp_sse.agent.get_db_session_local", return_value=mock_ctx):
            await _ensure_session_user_exists("user-1", mock_config)

        # User already exists so db.add should not have been called
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_user_when_not_exists(self):
        from ii_agent.integrations.mcp_sse.agent import _ensure_session_user_exists

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_config = MagicMock()
        mock_config.mcp_default_session_user_email = None
        mock_config.default_user_credits = 100.0

        with patch("ii_agent.integrations.mcp_sse.agent.get_db_session_local", return_value=mock_ctx):
            await _ensure_session_user_exists("new-user-1", mock_config)

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_user_id_template_email(self):
        from ii_agent.integrations.mcp_sse.agent import _ensure_session_user_exists

        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = None  # User doesn't exist

        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = None  # Email check

        mock_db = AsyncMock()
        call_count = [0]

        async def execute_side_effect(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_result_1
            return mock_result_2

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_config = MagicMock()
        mock_config.mcp_default_session_user_email = "service-{user_id}@example.com"
        mock_config.default_user_credits = 0.0

        with patch("ii_agent.integrations.mcp_sse.agent.get_db_session_local", return_value=mock_ctx):
            await _ensure_session_user_exists("test-user-abc", mock_config)

        # Check that add was called with the correct email
        call_args = mock_db.add.call_args
        user_obj = call_args[0][0]
        assert "test-user-abc" in user_obj.email or user_obj.email.endswith("@mcp.local")


class TestPreConfigureMcpServer:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_api_key(self):
        from ii_agent.integrations.mcp_sse.agent import _pre_configure_mcp_server

        mock_config = MagicMock()
        mock_config.mcp.port = 8080
        mock_config.sandbox.e2b_api_key = None
        mock_config.a2a_sandbox_api_key = None

        mock_sandbox = MagicMock()
        mock_sandbox.expose_port = AsyncMock(return_value="http://sandbox.example.com")

        session_id = uuid.uuid4()
        result = await _pre_configure_mcp_server(mock_config, mock_sandbox, session_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_connection(self):
        from ii_agent.integrations.mcp_sse.agent import _pre_configure_mcp_server

        mock_config = MagicMock()
        mock_config.mcp.port = 8080
        mock_config.sandbox.e2b_api_key = "test-api-key"
        mock_config.tool_server_url = "http://tools.example.com"

        mock_sandbox = MagicMock()
        mock_sandbox.expose_port = AsyncMock(return_value="http://abc-123.sandbox.example.com")

        mock_mcp_client = AsyncMock()
        mock_mcp_client.__aenter__ = AsyncMock(return_value=mock_mcp_client)
        mock_mcp_client.__aexit__ = AsyncMock(return_value=False)
        mock_mcp_client.set_credential = AsyncMock()
        mock_mcp_client.set_tool_server_url = AsyncMock()
        mock_mcp_client.ping = AsyncMock()
        mock_mcp_client.list_tools = AsyncMock(return_value=[MagicMock(), MagicMock()])

        session_id = uuid.uuid4()

        with patch("ii_agent.integrations.mcp_sse.agent.MCPClient", return_value=mock_mcp_client):
            result = await _pre_configure_mcp_server(mock_config, mock_sandbox, session_id)
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_after_all_retries_fail(self):
        from ii_agent.integrations.mcp_sse.agent import _pre_configure_mcp_server

        mock_config = MagicMock()
        mock_config.mcp.port = 8080
        mock_config.sandbox.e2b_api_key = "test-api-key"
        mock_config.tool_server_url = "http://tools.example.com"

        mock_sandbox = MagicMock()
        mock_sandbox.expose_port = AsyncMock(return_value="http://abc-123.sandbox.example.com")

        mock_mcp_client = AsyncMock()
        mock_mcp_client.__aenter__ = AsyncMock(return_value=mock_mcp_client)
        mock_mcp_client.__aexit__ = AsyncMock(return_value=False)
        mock_mcp_client.set_credential = AsyncMock(side_effect=Exception("Connection refused"))

        session_id = uuid.uuid4()

        with (
            patch("ii_agent.integrations.mcp_sse.agent.MCPClient", return_value=mock_mcp_client),
            patch("ii_agent.integrations.mcp_sse.agent.asyncio.sleep", AsyncMock()),
        ):
            result = await _pre_configure_mcp_server(mock_config, mock_sandbox, session_id)
            assert result is False


class TestRunAgentInternal:
    def test_runs_agent_and_returns_metadata(self):
        from ii_agent.integrations.mcp_sse.agent import run_agent_internal

        mock_controller = MagicMock()
        mock_controller.run_agent = MagicMock()

        session_id = uuid.uuid4()
        result = run_agent_internal(
            agent_controller=mock_controller,
            prompt="test prompt",
            session_id=session_id,
            sandbox_url="http://sandbox.example.com",
        )

        mock_controller.run_agent.assert_called_once_with(instruction="test prompt", resume=True)
        assert result["session_id"] == str(session_id)
        assert result["sandbox_url"] == "http://sandbox.example.com"


# ===========================================================================
# mcp_sse/widgets.py
# ===========================================================================

class TestGenerateRequestHash:
    def test_returns_sha256_hex(self):
        from ii_agent.integrations.mcp_sse.widgets import _generate_request_hash

        result = _generate_request_hash("prompt", "ctx-1", "website_build")
        assert len(result) == 64  # SHA256 hex length
        # Should be consistent
        result2 = _generate_request_hash("prompt", "ctx-1", "website_build")
        assert result == result2

    def test_different_prompts_produce_different_hashes(self):
        from ii_agent.integrations.mcp_sse.widgets import _generate_request_hash

        hash1 = _generate_request_hash("prompt A", "ctx-1", "website_build")
        hash2 = _generate_request_hash("prompt B", "ctx-1", "website_build")
        assert hash1 != hash2

    def test_none_context_and_agent_type_handled(self):
        from ii_agent.integrations.mcp_sse.widgets import _generate_request_hash

        result = _generate_request_hash("prompt", None, None)
        assert len(result) == 64


class TestCleanupExpiredCache:
    def test_removes_expired_entries(self):
        from ii_agent.integrations.mcp_sse.widgets import _cleanup_expired_cache
        import ii_agent.integrations.mcp_sse.widgets as widgets_mod

        original_cache = widgets_mod._request_cache.copy()
        try:
            # Add expired entry
            widgets_mod._request_cache["old_hash"] = ("sess-old", time.time() - 100)
            # Add fresh entry
            widgets_mod._request_cache["new_hash"] = ("sess-new", time.time())

            _cleanup_expired_cache()

            assert "old_hash" not in widgets_mod._request_cache
            assert "new_hash" in widgets_mod._request_cache
        finally:
            widgets_mod._request_cache.clear()
            widgets_mod._request_cache.update(original_cache)


class TestCheckDuplicateRequest:
    def test_returns_not_duplicate_for_new_request(self):
        from ii_agent.integrations.mcp_sse.widgets import _check_duplicate_request
        import ii_agent.integrations.mcp_sse.widgets as widgets_mod

        original_cache = widgets_mod._request_cache.copy()
        try:
            widgets_mod._request_cache.clear()
            is_dup, session_id = _check_duplicate_request("new prompt", None, None)
            assert is_dup is False
            assert session_id is None
        finally:
            widgets_mod._request_cache.clear()
            widgets_mod._request_cache.update(original_cache)

    def test_returns_duplicate_for_cached_request(self):
        from ii_agent.integrations.mcp_sse.widgets import (
            _check_duplicate_request,
            _generate_request_hash,
        )
        import ii_agent.integrations.mcp_sse.widgets as widgets_mod

        original_cache = widgets_mod._request_cache.copy()
        try:
            widgets_mod._request_cache.clear()

            prompt = "existing prompt"
            req_hash = _generate_request_hash(prompt, None, None)
            widgets_mod._request_cache[req_hash] = ("existing-session", time.time())

            is_dup, session_id = _check_duplicate_request(prompt, None, None)
            assert is_dup is True
            assert session_id == "existing-session"
        finally:
            widgets_mod._request_cache.clear()
            widgets_mod._request_cache.update(original_cache)


class TestCacheRequest:
    def test_stores_request_in_cache(self):
        from ii_agent.integrations.mcp_sse.widgets import (
            _cache_request,
            _generate_request_hash,
        )
        import ii_agent.integrations.mcp_sse.widgets as widgets_mod

        original_cache = widgets_mod._request_cache.copy()
        try:
            widgets_mod._request_cache.clear()

            prompt = "unique prompt xyz"
            session_id = "test-session"
            _cache_request(prompt, None, session_id, None)

            req_hash = _generate_request_hash(prompt, None, None)
            assert req_hash in widgets_mod._request_cache
            assert widgets_mod._request_cache[req_hash][0] == session_id
        finally:
            widgets_mod._request_cache.clear()
            widgets_mod._request_cache.update(original_cache)


class TestCreateReadResourceHandler:
    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_resource(self):
        from mcp import types as mcp_types
        from ii_agent.integrations.mcp_sse.widgets import create_read_resource_handler
        import ii_agent.integrations.mcp_sse.widgets as widgets_mod

        # Ensure WIDGETS_BY_URI is clear for this test
        original_widgets = getattr(widgets_mod, "WIDGETS_BY_URI", {})

        handler = create_read_resource_handler()

        req = MagicMock()
        req.params = MagicMock()
        req.params.uri = "ui://unknown/resource.html"

        with patch.dict("ii_agent.integrations.mcp_sse.widgets.WIDGETS_BY_URI", {}, clear=True):
            result = await handler(req)

        assert isinstance(result, mcp_types.ServerResult)


class TestCreateCallToolHandler:
    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_tool(self):
        from mcp import types as mcp_types
        from ii_agent.integrations.mcp_sse.widgets import create_call_tool_handler

        mock_mcp_server = MagicMock()

        handler = create_call_tool_handler(mock_mcp_server)

        req = MagicMock()
        req.params = MagicMock()
        req.params.name = "unknown_tool"
        req.params.arguments = {}

        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="")

        with (
            patch("ii_agent.integrations.mcp_sse.widgets.get_http_headers", return_value=mock_headers),
        ):
            result = await handler(req)

        assert isinstance(result, mcp_types.ServerResult)
        # The result should have an error
        assert result.root.isError is True

    @pytest.mark.asyncio
    async def test_returns_error_when_prompt_missing(self):
        from mcp import types as mcp_types
        from ii_agent.integrations.mcp_sse.widgets import create_call_tool_handler

        mock_mcp_server = MagicMock()
        handler = create_call_tool_handler(mock_mcp_server)

        req = MagicMock()
        req.params = MagicMock()
        req.params.name = "run_task"
        req.params.arguments = {}  # Missing prompt

        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="")

        with (
            patch("ii_agent.integrations.mcp_sse.widgets.get_http_headers", return_value=mock_headers),
        ):
            result = await handler(req)

        assert isinstance(result, mcp_types.ServerResult)
        assert result.root.isError is True

    @pytest.mark.asyncio
    async def test_returns_error_for_invalid_agent_type(self):
        from mcp import types as mcp_types
        from ii_agent.integrations.mcp_sse.widgets import create_call_tool_handler

        mock_mcp_server = MagicMock()
        handler = create_call_tool_handler(mock_mcp_server)

        req = MagicMock()
        req.params = MagicMock()
        req.params.name = "run_task"
        req.params.arguments = {
            "prompt": "Build a website",
            "agent_type": "invalid_type",
        }

        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="")

        with (
            patch("ii_agent.integrations.mcp_sse.widgets.get_http_headers", return_value=mock_headers),
        ):
            result = await handler(req)

        assert isinstance(result, mcp_types.ServerResult)
        assert result.root.isError is True

    @pytest.mark.asyncio
    async def test_returns_error_for_disallowed_agent_type(self):
        from mcp import types as mcp_types
        from ii_agent.integrations.mcp_sse.widgets import create_call_tool_handler

        mock_mcp_server = MagicMock()
        handler = create_call_tool_handler(mock_mcp_server)

        req = MagicMock()
        req.params = MagicMock()
        req.params.name = "run_task"
        req.params.arguments = {
            "prompt": "Build a website",
            "agent_type": "coding",  # Not in allowed set
        }

        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="")

        with (
            patch("ii_agent.integrations.mcp_sse.widgets.get_http_headers", return_value=mock_headers),
        ):
            result = await handler(req)

        assert isinstance(result, mcp_types.ServerResult)
        assert result.root.isError is True

    @pytest.mark.asyncio
    async def test_returns_cached_session_for_duplicate_request(self):
        from mcp import types as mcp_types
        from ii_agent.integrations.mcp_sse.widgets import (
            create_call_tool_handler,
            _generate_request_hash,
        )
        import ii_agent.integrations.mcp_sse.widgets as widgets_mod

        original_cache = widgets_mod._request_cache.copy()
        mock_mcp_server = MagicMock()
        handler = create_call_tool_handler(mock_mcp_server)

        prompt = "Build me a website about cats"
        existing_session = "existing-session-id"
        req_hash = _generate_request_hash(prompt, None, "website_build")
        widgets_mod._request_cache[req_hash] = (existing_session, time.time())

        try:
            req = MagicMock()
            req.params = MagicMock()
            req.params.name = "run_task"
            req.params.arguments = {
                "prompt": prompt,
                "agent_type": "website_build",
            }

            mock_headers = MagicMock()
            mock_headers.get = MagicMock(return_value="")

            with patch("ii_agent.integrations.mcp_sse.widgets.get_http_headers", return_value=mock_headers):
                result = await handler(req)

            assert isinstance(result, mcp_types.ServerResult)
            # Should return existing session
            assert existing_session in str(result)
        finally:
            widgets_mod._request_cache.clear()
            widgets_mod._request_cache.update(original_cache)

    @pytest.mark.asyncio
    async def test_refresh_session_status_missing_session_id(self):
        from mcp import types as mcp_types
        from ii_agent.integrations.mcp_sse.widgets import create_call_tool_handler

        mock_mcp_server = MagicMock()
        handler = create_call_tool_handler(mock_mcp_server)

        req = MagicMock()
        req.params = MagicMock()
        req.params.name = "refresh_session_status"
        req.params.arguments = {}  # Missing session_id

        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="")

        with patch("ii_agent.integrations.mcp_sse.widgets.get_http_headers", return_value=mock_headers):
            result = await handler(req)

        assert isinstance(result, mcp_types.ServerResult)
        assert result.root.isError is True

    @pytest.mark.asyncio
    async def test_refresh_session_status_invalid_uuid(self):
        from mcp import types as mcp_types
        from ii_agent.integrations.mcp_sse.widgets import create_call_tool_handler

        mock_mcp_server = MagicMock()
        handler = create_call_tool_handler(mock_mcp_server)

        req = MagicMock()
        req.params = MagicMock()
        req.params.name = "refresh_session_status"
        req.params.arguments = {"session_id": "not-a-valid-uuid"}

        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="")

        mock_session_svc = MagicMock()
        mock_session_svc.get_session_by_id = AsyncMock(return_value=None)

        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db_ctx)
        mock_db_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("ii_agent.integrations.mcp_sse.widgets.get_http_headers", return_value=mock_headers),
            patch("ii_agent.integrations.mcp_sse.widgets.get_db_session_local", return_value=mock_db_ctx),
        ):
            result = await handler(req)

        assert isinstance(result, mcp_types.ServerResult)
        assert result.root.isError is True

    @pytest.mark.asyncio
    async def test_agent_init_error_returns_error_result(self):
        from mcp import types as mcp_types
        from ii_agent.integrations.mcp_sse.widgets import (
            create_call_tool_handler,
            _generate_request_hash,
        )
        import ii_agent.integrations.mcp_sse.widgets as widgets_mod

        original_cache = widgets_mod._request_cache.copy()
        try:
            widgets_mod._request_cache.clear()

            mock_mcp_server = MagicMock()
            handler = create_call_tool_handler(mock_mcp_server)

            req = MagicMock()
            req.params = MagicMock()
            req.params.name = "run_task"
            req.params.arguments = {
                "prompt": "Build something unique xyz-abc-123",
                "agent_type": "website_build",
            }

            mock_headers = MagicMock()
            mock_headers.get = MagicMock(return_value="")

            with (
                patch("ii_agent.integrations.mcp_sse.widgets.get_http_headers", return_value=mock_headers),
                patch(
                    "ii_agent.integrations.mcp_sse.widgets.init_agent",
                    AsyncMock(side_effect=Exception("Agent init failed")),
                ),
            ):
                result = await handler(req)

            assert isinstance(result, mcp_types.ServerResult)
            assert result.root.isError is True
        finally:
            widgets_mod._request_cache.clear()
            widgets_mod._request_cache.update(original_cache)


# ===========================================================================
# mcp_sse/agent.py - _agent_worker
# ===========================================================================

class TestAgentWorker:
    @pytest.mark.asyncio
    async def test_worker_processes_task_from_queue(self):
        import asyncio
        import ii_agent.integrations.mcp_sse.agent as agent_mod
        from ii_agent.integrations.mcp_sse.agent import AgentTask

        mock_controller = MagicMock()
        mock_controller.run_agent_async = AsyncMock()

        original_queue = agent_mod._agent_queue
        try:
            queue = asyncio.Queue()
            agent_mod._agent_queue = queue

            session_id = uuid.uuid4()
            task = AgentTask(
                agent_controller=mock_controller,
                prompt="test",
                session_id=session_id,
                sandbox_url="http://sandbox.example.com",
            )
            await queue.put(task)

            # Create worker task and wait briefly
            worker = asyncio.create_task(agent_mod._agent_worker())

            # Give it time to process
            await asyncio.sleep(0.1)
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

            mock_controller.run_agent_async.assert_called_once_with(
                instruction="test", resume=True
            )
        finally:
            agent_mod._agent_queue = original_queue
