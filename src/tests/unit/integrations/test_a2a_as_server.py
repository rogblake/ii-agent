"""Unit tests for ii_agent.integrations.a2a.as_server (IIAgentA2AServer)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server() -> "IIAgentA2AServer":
    from ii_agent.integrations.a2a.as_server import IIAgentA2AServer

    return IIAgentA2AServer()


def _make_request_payload(**kwargs):
    from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload

    return A2ARequestPayload(**kwargs)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestIIAgentA2AServerInit:
    def test_init_sets_none_agent_service(self):
        server = _make_server()
        assert server._agent_service is None

    def test_init_sets_none_config(self):
        server = _make_server()
        assert server._config is None

    def test_agent_service_instance_property_lazy_init(self):
        server = _make_server()
        mock_service = MagicMock()
        mock_storage = MagicMock()
        with (
            patch("ii_agent.integrations.a2a.as_server.get_settings") as ms,
            patch("ii_agent.integrations.a2a.as_server.AgentService", return_value=mock_service),
            patch("ii_agent.core.storage.client.storage", mock_storage),
        ):
            ms.return_value = MagicMock()
            service = server.agent_service_instance
        assert service is not None

    def test_config_property_lazy_init(self):
        server = _make_server()
        with patch("ii_agent.integrations.a2a.as_server.get_settings") as ms:
            ms.return_value = MagicMock(llm_configs={"default": None})
            config = server.config
        assert config is not None


# ---------------------------------------------------------------------------
# _resolve_session_uuid
# ---------------------------------------------------------------------------


class TestResolveSessionUuid:
    def test_valid_uuid_string_returns_uuid(self):
        server = _make_server()
        uid = str(uuid.uuid4())
        result = server._resolve_session_uuid(uid)
        assert str(result) == uid

    def test_invalid_string_returns_uuid5(self):
        server = _make_server()
        result = server._resolve_session_uuid("not-a-uuid")
        assert isinstance(result, uuid.UUID)

    def test_empty_string_raises_value_error(self):
        server = _make_server()
        with pytest.raises(ValueError, match="context_id"):
            server._resolve_session_uuid("")

    def test_deterministic_uuid5_for_same_context_id(self):
        server = _make_server()
        result1 = server._resolve_session_uuid("same-context-id")
        result2 = server._resolve_session_uuid("same-context-id")
        assert result1 == result2

    def test_different_context_ids_produce_different_uuids(self):
        server = _make_server()
        result1 = server._resolve_session_uuid("context-a")
        result2 = server._resolve_session_uuid("context-b")
        assert result1 != result2


# ---------------------------------------------------------------------------
# _resolve_session_user_id
# ---------------------------------------------------------------------------


class TestResolveSessionUserId:
    def test_uses_user_id_from_payload(self):
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload, UserAuth

        server = _make_server()
        payload = A2ARequestPayload(user=UserAuth(user_id="user_from_payload"))
        result = server._resolve_session_user_id(payload, None, "ctx")
        assert result == "user_from_payload"

    def test_falls_back_to_existing_session_user(self):
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload

        server = _make_server()
        payload = A2ARequestPayload()
        existing = MagicMock()
        existing.user = MagicMock()
        existing.user.user_id = "session_user"
        result = server._resolve_session_user_id(payload, existing, "ctx")
        assert result == "session_user"

    def test_falls_back_to_config_default(self):
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload

        server = _make_server()
        server._config = MagicMock()
        server._config.a2a_default_session_user_id = "config_default_user"
        server._config.a2a_sandbox_user_id = "sandbox_user"
        payload = A2ARequestPayload()
        result = server._resolve_session_user_id(payload, None, "ctx")
        assert result == "config_default_user"

    def test_falls_back_to_sandbox_user_id(self):
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload

        server = _make_server()
        server._config = MagicMock()
        server._config.a2a_default_session_user_id = None
        server._config.a2a_sandbox_user_id = "sandbox_user"
        payload = A2ARequestPayload()
        result = server._resolve_session_user_id(payload, None, "ctx")
        assert result == "sandbox_user"


# ---------------------------------------------------------------------------
# _get_default_llm_config
# ---------------------------------------------------------------------------


class TestGetDefaultLlmConfig:
    def test_raises_when_no_default(self):
        server = _make_server()
        server._config = MagicMock()
        server._config.llm_configs = {}
        with pytest.raises(ValueError, match="Default LLM configuration is missing"):
            server._get_default_llm_config()

    def test_returns_llm_config_from_dict(self):
        from ii_agent.core.config.llm_config import LLMConfig

        server = _make_server()
        server._config = MagicMock()
        server._config.llm_configs = {
            "default": {
                "model": "gpt-4o",
                "provider": "OpenAI",
                "api_key": "key",
            }
        }
        result = server._get_default_llm_config()
        assert isinstance(result, LLMConfig)

    def test_returns_llm_config_instance_directly(self):
        from ii_agent.core.config.llm_config import LLMConfig
        from pydantic import SecretStr

        server = _make_server()
        config_obj = LLMConfig(model="gpt-4o", provider="OpenAI", api_key=SecretStr("key"))
        server._config = MagicMock()
        server._config.llm_configs = {"default": config_obj}
        result = server._get_default_llm_config()
        assert result is config_obj


# ---------------------------------------------------------------------------
# _resolve_sandbox_credential
# ---------------------------------------------------------------------------


class TestResolveSandboxCredential:
    def test_uses_request_api_key_when_provided(self):
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload, UserAuth

        server = _make_server()
        server._config = MagicMock()
        server._config.a2a_sandbox_api_key = None
        server._config.a2a_sandbox_user_id = None
        payload = A2ARequestPayload(user=UserAuth(user_id="u1", api_key="request_key"))
        credential, source = server._resolve_sandbox_credential(payload, "ctx")
        assert credential is not None
        assert credential["user_api_key"] == "request_key"
        assert source == "request metadata"

    def test_falls_back_to_config_api_key(self):
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload

        server = _make_server()
        server._config = MagicMock()
        server._config.a2a_sandbox_api_key = "server_key"
        server._config.a2a_sandbox_user_id = "server_user"
        payload = A2ARequestPayload()
        credential, source = server._resolve_sandbox_credential(payload, "ctx")
        assert credential is not None
        assert credential["user_api_key"] == "server_key"
        assert source == "server configuration"

    def test_returns_none_when_no_credentials(self):
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload

        server = _make_server()
        server._config = MagicMock()
        server._config.a2a_sandbox_api_key = None
        server._config.a2a_sandbox_user_id = None
        payload = A2ARequestPayload()
        credential, source = server._resolve_sandbox_credential(payload, "ctx")
        assert credential is None
        assert source is None

    def test_whitespace_only_key_treated_as_none(self):
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload, UserAuth

        server = _make_server()
        server._config = MagicMock()
        server._config.a2a_sandbox_api_key = None
        server._config.a2a_sandbox_user_id = None
        payload = A2ARequestPayload(user=UserAuth(api_key="   "))
        credential, source = server._resolve_sandbox_credential(payload, "ctx")
        assert credential is None

    def test_credential_includes_user_id_when_present(self):
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload, UserAuth

        server = _make_server()
        server._config = MagicMock()
        server._config.a2a_sandbox_api_key = None
        server._config.a2a_sandbox_user_id = None
        payload = A2ARequestPayload(user=UserAuth(user_id="uid1", api_key="key1"))
        credential, _ = server._resolve_sandbox_credential(payload, "ctx")
        assert credential["user_id"] == "uid1"


# ---------------------------------------------------------------------------
# _update_sandbox_extension_context
# ---------------------------------------------------------------------------


class TestUpdateSandboxExtensionContext:
    def test_skips_when_no_extension_context(self):
        from ii_agent.integrations.a2a.as_server import IIAgentA2AServer

        IIAgentA2AServer._update_sandbox_extension_context(
            None,
            reuse_requested=False,
            reuse_attempted=False,
            reuse_granted=False,
            sandbox_id="sid",
            sandbox_user_id=None,
            fallback_reason=None,
        )

    def test_skips_when_sandbox_reuse_not_in_context(self):
        from ii_agent.integrations.a2a.as_server import IIAgentA2AServer

        ctx = {"other_key": "value"}
        IIAgentA2AServer._update_sandbox_extension_context(
            ctx,
            reuse_requested=True,
            reuse_attempted=True,
            reuse_granted=False,
            sandbox_id="sid",
            sandbox_user_id=None,
            fallback_reason=None,
        )
        assert "sandbox_reuse" not in ctx

    def test_updates_extension_context_when_sandbox_reuse_present(self):
        from ii_agent.integrations.a2a.as_server import IIAgentA2AServer

        ctx = {"sandbox_reuse": {}}
        IIAgentA2AServer._update_sandbox_extension_context(
            ctx,
            reuse_requested=True,
            reuse_attempted=True,
            reuse_granted=True,
            sandbox_id="sandbox-123",
            sandbox_user_id="user-1",
            fallback_reason=None,
        )
        sb = ctx["sandbox_reuse"]
        assert sb["reuse_requested"] is True
        assert sb["reuse_granted"] is True
        assert sb["sandbox_id"] == "sandbox-123"
        assert sb["sandbox_user_id"] == "user-1"

    def test_appends_issue_on_fallback(self):
        from ii_agent.integrations.a2a.as_server import IIAgentA2AServer

        ctx = {"sandbox_reuse": {}}
        with patch("ii_agent.integrations.a2a.as_server.append_extension_issue") as mock_append:
            IIAgentA2AServer._update_sandbox_extension_context(
                ctx,
                reuse_requested=True,
                reuse_attempted=True,
                reuse_granted=False,
                sandbox_id="sid",
                sandbox_user_id=None,
                fallback_reason="Sandbox not found",
            )
            mock_append.assert_called_once()

    def test_no_sandbox_user_id_not_added(self):
        from ii_agent.integrations.a2a.as_server import IIAgentA2AServer

        ctx = {"sandbox_reuse": {}}
        IIAgentA2AServer._update_sandbox_extension_context(
            ctx,
            reuse_requested=False,
            reuse_attempted=False,
            reuse_granted=False,
            sandbox_id="sid",
            sandbox_user_id=None,
            fallback_reason=None,
        )
        assert "sandbox_user_id" not in ctx["sandbox_reuse"]


# ---------------------------------------------------------------------------
# _deep_merge_dict
# ---------------------------------------------------------------------------


class TestDeepMergeDict:
    def test_basic_merge(self):
        from ii_agent.integrations.a2a.as_server import _deep_merge_dict

        base = {"a": 1, "b": 2}
        incoming = {"b": 3, "c": 4}
        result = _deep_merge_dict(base, incoming)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_recursive_merge_for_nested_dicts(self):
        from ii_agent.integrations.a2a.as_server import _deep_merge_dict

        base = {"a": {"x": 1, "y": 2}}
        incoming = {"a": {"y": 99, "z": 3}}
        result = _deep_merge_dict(base, incoming)
        assert result["a"] == {"x": 1, "y": 99, "z": 3}

    def test_none_incoming_returns_copy_of_base(self):
        from ii_agent.integrations.a2a.as_server import _deep_merge_dict

        base = {"key": "value"}
        result = _deep_merge_dict(base, None)
        assert result == {"key": "value"}
        assert result is not base

    def test_empty_incoming_returns_copy(self):
        from ii_agent.integrations.a2a.as_server import _deep_merge_dict

        base = {"key": "value"}
        result = _deep_merge_dict(base, {})
        assert result == {"key": "value"}

    def test_incoming_non_dict_value_overrides(self):
        from ii_agent.integrations.a2a.as_server import _deep_merge_dict

        base = {"a": {"nested": "dict"}}
        incoming = {"a": "string"}
        result = _deep_merge_dict(base, incoming)
        assert result["a"] == "string"

    def test_base_does_not_mutate(self):
        from ii_agent.integrations.a2a.as_server import _deep_merge_dict

        base = {"a": 1}
        incoming = {"b": 2}
        _deep_merge_dict(base, incoming)
        assert "b" not in base

    def test_empty_base_with_incoming(self):
        from ii_agent.integrations.a2a.as_server import _deep_merge_dict

        result = _deep_merge_dict({}, {"a": 1})
        assert result == {"a": 1}


# ---------------------------------------------------------------------------
# _build_session_service
# ---------------------------------------------------------------------------


class TestBuildSessionService:
    def test_build_session_service_returns_session_service(self):
        from ii_agent.sessions.service import SessionService

        server = _make_server()
        server._config = MagicMock()
        # storage is imported inside _build_session_service as:
        #   from ii_agent.core.storage.client import storage
        with (
            patch("ii_agent.core.storage.client.storage", MagicMock()),
            patch("ii_agent.integrations.a2a.as_server.get_settings", return_value=server._config),
        ):
            service = server._build_session_service()
        assert isinstance(service, SessionService)


# ---------------------------------------------------------------------------
# process_request – error path
# ---------------------------------------------------------------------------


class TestProcessRequest:
    @pytest.mark.asyncio
    async def test_sends_error_event_on_exception(self):
        server = _make_server()
        server._process_agent_request = AsyncMock(side_effect=RuntimeError("Processing error"))

        event_queue = AsyncMock()
        event_queue.enqueue_event = AsyncMock()

        context = MagicMock()
        context.task_id = "t1"
        context.context_id = "c1"

        await server.process_request(
            query="do something",
            a2a_context=context,
            event_queue=event_queue,
        )

        event_queue.enqueue_event.assert_called()
        call_args = event_queue.enqueue_event.call_args[0][0]
        from a2a.types import TaskStatusUpdateEvent, TaskState

        assert isinstance(call_args, TaskStatusUpdateEvent)
        assert call_args.status.state == TaskState.failed

    @pytest.mark.asyncio
    async def test_calls_process_agent_request(self):
        server = _make_server()
        server._process_agent_request = AsyncMock()

        context = MagicMock()
        context.task_id = "t1"
        context.context_id = "c1"

        await server.process_request(
            query="hello",
            a2a_context=context,
            event_queue=AsyncMock(),
        )

        server._process_agent_request.assert_called_once()
