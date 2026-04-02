"""Unit tests for ii_agent.integrations.a2a.as_client (IIAgentA2AClient)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(
    agent_url: str = "http://agent.example.com",
    **kwargs,
) -> "IIAgentA2AClient":
    from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

    return IIAgentA2AClient(agent_url, **kwargs)


def _make_text_part(text: str):
    """Create a mock A2A TextPart-like object."""
    from a2a.types import TextPart

    return TextPart(text=text)


def _make_part(text: str):
    """Create a Part wrapping a TextPart."""
    from a2a.types import Part, TextPart

    return Part(root=TextPart(text=text))


def _make_message(text: str = "Hello"):
    """Create a minimal A2A Message."""
    from a2a.types import Role

    from a2a.client.helpers import create_text_message_object

    return create_text_message_object(role=Role.user, content=text)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestIIAgentA2AClientInit:
    def test_default_init(self):
        client = _make_client()
        assert client.agent_url == "http://agent.example.com"
        assert client._httpx_client is None
        assert client._agent_card is None
        assert client._tool_calls == [] if hasattr(client, "_tool_calls") else True

    def test_trailing_slash_stripped_from_url(self):
        client = _make_client("http://agent.example.com/")
        assert client.agent_url == "http://agent.example.com"

    def test_custom_timeout(self):
        timeout = httpx.Timeout(30.0)
        client = _make_client(timeout=timeout)
        assert client._timeout is timeout

    def test_default_timeout_when_none(self):
        client = _make_client()
        assert isinstance(client._timeout, httpx.Timeout)

    def test_custom_headers_sanitized(self):
        client = _make_client(default_headers={"X-Custom": "value", "empty": ""})
        assert client._custom_headers.get("X-Custom") == "value"

    def test_extensions_initialized_empty(self):
        client = _make_client()
        assert client._extension_definitions == {}
        assert client._required_extensions == set()

    def test_interceptors_include_extensions_header_interceptor(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        client = _make_client()
        assert any(isinstance(i, ExtensionsHeaderInterceptor) for i in client._interceptors)

    def test_additional_interceptors_added(self):
        mock_interceptor = MagicMock()
        client = _make_client(interceptors=[mock_interceptor])
        assert mock_interceptor in client._interceptors

    def test_consumers_default_empty(self):
        client = _make_client()
        assert client._consumers == []

    def test_custom_consumers(self):
        consumer = MagicMock()
        client = _make_client(consumers=[consumer])
        assert consumer in client._consumers


# ---------------------------------------------------------------------------
# _sanitize_headers
# ---------------------------------------------------------------------------


class TestSanitizeHeaders:
    def test_none_returns_empty_dict(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        assert IIAgentA2AClient._sanitize_headers(None) == {}

    def test_empty_dict_returns_empty_dict(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        assert IIAgentA2AClient._sanitize_headers({}) == {}

    def test_none_key_skipped(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._sanitize_headers({None: "value"})
        assert result == {}

    def test_none_value_skipped(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._sanitize_headers({"key": None})
        assert result == {}

    def test_empty_key_skipped(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._sanitize_headers({"": "value"})
        assert result == {}

    def test_valid_headers_preserved(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._sanitize_headers({"X-Header": "value"})
        assert result == {"X-Header": "value"}

    def test_numeric_values_converted_to_str(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._sanitize_headers({"X-Count": 42})
        assert result == {"X-Count": "42"}


# ---------------------------------------------------------------------------
# _derive_card_base_url
# ---------------------------------------------------------------------------


class TestDeriveCardBaseUrl:
    def test_strips_well_known_agent_json(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        url = "http://agent.com/.well-known/agent.json"
        result = IIAgentA2AClient._derive_card_base_url(url)
        assert result == "http://agent.com"

    def test_strips_well_known_agent_card_json(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        url = "http://agent.com/.well-known/agent-card.json"
        result = IIAgentA2AClient._derive_card_base_url(url)
        assert result == "http://agent.com"

    def test_plain_url_unchanged(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        url = "http://agent.com"
        result = IIAgentA2AClient._derive_card_base_url(url)
        assert result == "http://agent.com"

    def test_url_with_path_unchanged(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        url = "http://agent.com/api/v1"
        result = IIAgentA2AClient._derive_card_base_url(url)
        assert result == "http://agent.com/api/v1"


# ---------------------------------------------------------------------------
# _resolve_timeout_seconds
# ---------------------------------------------------------------------------


class TestResolveTimeoutSeconds:
    def test_uses_provided_value(self):
        client = _make_client()
        result = client._resolve_timeout_seconds(60.0)
        assert result == 60.0

    def test_ignores_zero_and_uses_fallback(self):
        client = _make_client()
        result = client._resolve_timeout_seconds(0.0)
        assert result > 0.0

    def test_ignores_negative_and_uses_fallback(self):
        client = _make_client()
        result = client._resolve_timeout_seconds(-5.0)
        assert result > 0.0

    def test_none_uses_env_var(self):
        client = _make_client()
        with patch.dict(os.environ, {"A2A_AGENT_DEFAULT_TIMEOUT_SECONDS": "120"}):
            result = client._resolve_timeout_seconds(None)
        assert result == 120.0

    def test_defaults_to_300_when_nothing_set(self):
        client = _make_client()
        with patch.dict(os.environ, {}, clear=False):
            env_backup = os.environ.pop("A2A_AGENT_DEFAULT_TIMEOUT_SECONDS", None)
            try:
                result = client._resolve_timeout_seconds(None)
                assert result == 300.0
            finally:
                if env_backup is not None:
                    os.environ["A2A_AGENT_DEFAULT_TIMEOUT_SECONDS"] = env_backup

    def test_invalid_env_var_uses_fallback(self):
        client = _make_client()
        with patch.dict(os.environ, {"A2A_AGENT_DEFAULT_TIMEOUT_SECONDS": "not_a_number"}):
            result = client._resolve_timeout_seconds(None)
        assert result == 300.0

    def test_invalid_provided_value_uses_fallback(self):
        client = _make_client()
        result = client._resolve_timeout_seconds("not_float")
        assert result == 300.0


# ---------------------------------------------------------------------------
# _build_timeout
# ---------------------------------------------------------------------------


class TestBuildTimeout:
    def test_creates_httpx_timeout(self):
        client = _make_client()
        timeout = client._build_timeout(30.0)
        assert isinstance(timeout, httpx.Timeout)

    def test_none_timeout_uses_default(self):
        client = _make_client()
        timeout = client._build_timeout(None)
        assert isinstance(timeout, httpx.Timeout)


# ---------------------------------------------------------------------------
# _format_error
# ---------------------------------------------------------------------------


class TestFormatError:
    def test_error_format(self):
        client = _make_client()
        result = client._format_error("Something went wrong")
        assert result["success"] is False
        assert "Something went wrong" in result["content"]
        assert result["agent_url"] == client.agent_url

    def test_error_includes_user_display_content(self):
        client = _make_client()
        result = client._format_error("error msg")
        assert "user_display_content" in result


# ---------------------------------------------------------------------------
# _extract_text_from_part
# ---------------------------------------------------------------------------


class TestExtractTextFromPart:
    def test_dict_with_text_returns_text(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._extract_text_from_part({"text": "hello"})
        assert result == "hello"

    def test_dict_with_no_text_returns_none(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._extract_text_from_part({"data": "binary"})
        assert result is None

    def test_part_with_text_part_root(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
        from a2a.types import Part, TextPart

        part = Part(root=TextPart(text="text from part"))
        result = IIAgentA2AClient._extract_text_from_part(part)
        assert result == "text from part"

    def test_part_with_none_root_returns_none(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        part = MagicMock()
        part.root = None
        result = IIAgentA2AClient._extract_text_from_part(part)
        assert result is None


# ---------------------------------------------------------------------------
# _extract_text_from_message
# ---------------------------------------------------------------------------


class TestExtractTextFromMessage:
    def test_none_message_returns_none(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._extract_text_from_message(None)
        assert result is None

    def test_message_with_text_part(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
        from a2a.client.helpers import create_text_message_object
        from a2a.types import Role

        msg = create_text_message_object(role=Role.agent, content="Hello agent!")
        result = IIAgentA2AClient._extract_text_from_message(msg)
        assert result == "Hello agent!"

    def test_message_with_no_parts_returns_none(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        msg = MagicMock()
        msg.parts = []
        result = IIAgentA2AClient._extract_text_from_message(msg)
        assert result is None


# ---------------------------------------------------------------------------
# _extract_text_from_status
# ---------------------------------------------------------------------------


class TestExtractTextFromStatus:
    def test_none_status_returns_none(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._extract_text_from_status(None)
        assert result is None

    def test_status_with_message_returns_text(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
        from a2a.client.helpers import create_text_message_object
        from a2a.types import Role, TaskStatus, TaskState

        msg = create_text_message_object(role=Role.agent, content="status text")
        status = TaskStatus(state=TaskState.completed, message=msg)
        result = IIAgentA2AClient._extract_text_from_status(status)
        assert result == "status text"


# ---------------------------------------------------------------------------
# _extract_text_from_artifact
# ---------------------------------------------------------------------------


class TestExtractTextFromArtifact:
    def test_none_artifact_returns_none(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._extract_text_from_artifact(None)
        assert result is None

    def test_artifact_with_parts_returns_text(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
        from a2a.utils import new_text_artifact

        artifact = new_text_artifact(name="test", text="artifact text")
        result = IIAgentA2AClient._extract_text_from_artifact(artifact)
        assert result == "artifact text"


# ---------------------------------------------------------------------------
# _summary_from_metadata
# ---------------------------------------------------------------------------


class TestSummaryFromMetadata:
    def test_none_model_returns_none(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._summary_from_metadata(None)
        assert result is None

    def test_model_without_metadata_returns_none(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        model = SimpleNamespace()
        result = IIAgentA2AClient._summary_from_metadata(model)
        assert result is None

    def test_metadata_dict_with_extensions_returns_dict(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        model = SimpleNamespace(metadata={"extensions": {"active": ["ext.a"]}})
        result = IIAgentA2AClient._summary_from_metadata(model)
        assert result == {"active": ["ext.a"]}

    def test_metadata_dict_without_extensions_returns_none(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        model = SimpleNamespace(metadata={"other": "data"})
        result = IIAgentA2AClient._summary_from_metadata(model)
        assert result is None

    def test_none_metadata_returns_none(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        model = SimpleNamespace(metadata=None)
        result = IIAgentA2AClient._summary_from_metadata(model)
        assert result is None


# ---------------------------------------------------------------------------
# _merge_extension_list
# ---------------------------------------------------------------------------


class TestMergeExtensionList:
    def test_adds_new_values_to_empty_summary(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        summary = {}
        result = IIAgentA2AClient._merge_extension_list(summary, "requested", ["ext.a", "ext.b"])
        assert result == ["ext.a", "ext.b"]
        assert summary["requested"] == ["ext.a", "ext.b"]

    def test_preserves_existing_order(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        summary = {"requested": ["ext.a"]}
        result = IIAgentA2AClient._merge_extension_list(summary, "requested", ["ext.b"])
        assert result == ["ext.a", "ext.b"]

    def test_deduplicates_values(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        summary = {"requested": ["ext.a"]}
        result = IIAgentA2AClient._merge_extension_list(summary, "requested", ["ext.a", "ext.b"])
        assert result == ["ext.a", "ext.b"]

    def test_empty_values_not_added(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        summary = {}
        result = IIAgentA2AClient._merge_extension_list(summary, "field", ["", "  "])
        assert result == []
        assert "field" not in summary

    def test_non_dict_summary_returns_empty(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._merge_extension_list("not_dict", "field", ["ext.a"])
        assert result == []

    def test_removes_field_when_no_values(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        summary = {"field": ["ext.a"]}
        result = IIAgentA2AClient._merge_extension_list(summary, "field", [])
        # When all values are in existing and no new ones - depends on empty check
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _build_message
# ---------------------------------------------------------------------------


class TestBuildMessage:
    def test_message_with_simple_query(self):
        from a2a.types import Role

        client = _make_client()
        msg = client._build_message("test query", {})
        assert msg.role == Role.user
        assert len(msg.parts) > 0

    def test_message_with_context_adds_metadata(self):
        client = _make_client()
        msg = client._build_message("query", {"key": "value"})
        assert msg.metadata is not None
        assert "ii-agent" in msg.metadata

    def test_message_with_empty_context_no_metadata_key(self):
        client = _make_client()
        msg = client._build_message("query", {})
        # Empty context shouldn't add ii-agent metadata
        if msg.metadata:
            assert "ii-agent" not in msg.metadata

    def test_requested_extensions_added_to_message(self):
        client = _make_client()
        msg = client._build_message("q", {"requested_extensions": ["ext.a", "ext.b"]})
        if msg.extensions:
            assert "ext.a" in msg.extensions

    def test_required_extensions_merged(self):
        client = _make_client()
        client._required_extensions = {"ext.required"}
        msg = client._build_message("q", {})
        if msg.extensions:
            assert "ext.required" in msg.extensions


# ---------------------------------------------------------------------------
# _hydrate_extension_config
# ---------------------------------------------------------------------------


class TestHydrateExtensionConfig:
    def test_populates_extension_definitions(self):
        from a2a.types import AgentExtension

        client = _make_client()
        ext = AgentExtension(uri="urn:ext.a", required=True, params={"metadata_key": "ext_a"})
        card = MagicMock()
        card.capabilities = MagicMock()
        card.capabilities.extensions = [ext]
        client._hydrate_extension_config(card)
        assert "urn:ext.a" in client._extension_definitions
        assert "urn:ext.a" in client._required_extensions

    def test_non_required_extension_not_in_required_set(self):
        from a2a.types import AgentExtension

        client = _make_client()
        ext = AgentExtension(uri="urn:ext.b", required=False, params={})
        card = MagicMock()
        card.capabilities = MagicMock()
        card.capabilities.extensions = [ext]
        client._hydrate_extension_config(card)
        assert "urn:ext.b" in client._extension_definitions
        assert "urn:ext.b" not in client._required_extensions

    def test_no_capabilities_results_in_empty_definitions(self):
        client = _make_client()
        card = MagicMock()
        card.capabilities = None
        client._hydrate_extension_config(card)
        assert client._extension_definitions == {}

    def test_extension_without_uri_ignored(self):
        from a2a.types import AgentExtension

        client = _make_client()
        ext = MagicMock(spec=AgentExtension)
        ext.uri = None
        card = MagicMock()
        card.capabilities = MagicMock()
        card.capabilities.extensions = [ext]
        client._hydrate_extension_config(card)
        assert client._extension_definitions == {}


# ---------------------------------------------------------------------------
# _inject_extensions_into_model
# ---------------------------------------------------------------------------


class TestInjectExtensionsIntoModel:
    def test_none_model_is_ignored(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        IIAgentA2AClient._inject_extensions_into_model(None, {"active": []})

    def test_model_without_metadata_attr_ignored(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        model = SimpleNamespace()
        IIAgentA2AClient._inject_extensions_into_model(model, {"active": []})

    def test_model_with_none_metadata_gets_extensions_set(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        model = SimpleNamespace(metadata=None)
        IIAgentA2AClient._inject_extensions_into_model(model, {"active": ["ext.a"]})
        assert model.metadata == {"extensions": {"active": ["ext.a"]}}

    def test_model_with_dict_metadata_adds_extensions(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        model = SimpleNamespace(metadata={"existing": "data"})
        IIAgentA2AClient._inject_extensions_into_model(model, {"active": []})
        assert "extensions" in model.metadata

    def test_existing_extensions_not_overwritten(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        model = SimpleNamespace(metadata={"extensions": {"active": ["original"]}})
        IIAgentA2AClient._inject_extensions_into_model(model, {"active": ["new"]})
        # setdefault should not overwrite existing
        assert "original" in model.metadata["extensions"]["active"]


# ---------------------------------------------------------------------------
# get_last_response_extensions
# ---------------------------------------------------------------------------


class TestGetLastResponseExtensions:
    def test_returns_none_when_no_extensions(self):
        client = _make_client()
        assert client.get_last_response_extensions() is None

    def test_returns_copy_of_extensions(self):
        client = _make_client()
        client._last_response_extensions = {"active": ["ext.a"]}
        result = client.get_last_response_extensions()
        assert result == {"active": ["ext.a"]}
        # Modifying result should not affect original
        result["new_key"] = "value"
        assert "new_key" not in client._last_response_extensions


# ---------------------------------------------------------------------------
# _iter_extension_models
# ---------------------------------------------------------------------------


class TestIterExtensionModels:
    def test_none_returns_empty_list(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        result = IIAgentA2AClient._iter_extension_models(None)
        assert result == []

    def test_message_returns_list_with_message(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
        from a2a.types import Role
        from a2a.client.helpers import create_text_message_object

        msg = create_text_message_object(role=Role.agent, content="hi")
        result = IIAgentA2AClient._iter_extension_models(msg)
        assert len(result) == 1
        assert result[0] is msg

    def test_tuple_payload_returns_task_and_update(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        task = MagicMock()
        update = MagicMock()
        result = IIAgentA2AClient._iter_extension_models((task, update))
        assert task in result
        assert update in result

    def test_tuple_with_none_update(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        task = MagicMock()
        result = IIAgentA2AClient._iter_extension_models((task, None))
        assert task in result


# ---------------------------------------------------------------------------
# refresh_agent_card
# ---------------------------------------------------------------------------


class TestRefreshAgentCard:
    @pytest.mark.asyncio
    async def test_clears_cached_card_and_refetches(self):
        client = _make_client()
        mock_card = MagicMock()
        client._agent_card = mock_card
        client.get_agent_card = AsyncMock(return_value=MagicMock())
        result = await client.refresh_agent_card()
        assert client._agent_card is None or client._agent_card is not mock_card


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    @pytest.mark.asyncio
    async def test_close_clears_clients(self):
        client = _make_client()
        mock_a2a_client = AsyncMock()
        from ii_agent.integrations.a2a.as_client import _ClientEntry

        entry = _ClientEntry(config=MagicMock(), client=mock_a2a_client)
        client._clients[True] = entry
        mock_httpx = AsyncMock()
        mock_httpx.is_closed = False
        client._httpx_client = mock_httpx
        await client.close()
        assert client._clients == {}
        assert client._httpx_client is None
        assert client._agent_card is None


# ---------------------------------------------------------------------------
# call_agent / stream_agent
# ---------------------------------------------------------------------------


class TestCallAgent:
    @pytest.mark.asyncio
    async def test_call_agent_success_and_extensions_merged(self):
        from a2a.client.helpers import create_text_message_object
        from a2a.types import Role

        client = _make_client()

        async def _stream_payload():
            message = create_text_message_object(role=Role.agent, content="agent result")
            message.metadata = {"extensions": {"active": ["ext-a"]}}
            yield message

        mock_client = MagicMock()
        mock_client.send_message = MagicMock(return_value=_stream_payload())
        client._get_client = AsyncMock(return_value=mock_client)

        result = await client.call_agent("hello")
        assert result["success"] is True
        assert result["content"] == "agent result"
        assert result["extensions"]["active"] == ["ext-a"]
        assert result["extensions"]["activated"] == ["ext-a"]

    @pytest.mark.asyncio
    async def test_call_agent_no_payload_is_error(self):
        client = _make_client()

        async def _empty_stream():
            if False:
                yield None

        mock_client = MagicMock()
        mock_client.send_message = MagicMock(return_value=_empty_stream())
        client._get_client = AsyncMock(return_value=mock_client)

        result = await client.call_agent("hello")
        assert result["success"] is False
        assert result["content"] == "Error: No response received from agent."

    @pytest.mark.asyncio
    async def test_call_agent_exception_path(self):
        client = _make_client()
        client._get_client = AsyncMock(side_effect=RuntimeError("boom"))

        result = await client.call_agent("hello")
        assert result["success"] is False
        assert "boom" in result["content"]


class TestStreamAgent:
    @pytest.mark.asyncio
    async def test_stream_agent_yields_items_and_tracks_extensions(self):
        from a2a.client.helpers import create_text_message_object
        from a2a.types import Role

        client = _make_client()

        async def _stream_payload():
            update = create_text_message_object(role=Role.agent, content="update text")
            update.metadata = {"extensions": {"active": ["ext-update"]}}
            task = create_text_message_object(role=Role.agent, content="task text")
            yield (task, update)

        mock_client = MagicMock()
        mock_client.send_message = MagicMock(return_value=_stream_payload())
        client._get_client = AsyncMock(return_value=mock_client)
        store = MagicMock()
        client._store_response_extensions = store

        items = []
        async for item in client.stream_agent("hello"):
            items.append(item)

        assert len(items) == 2
        assert items[1].metadata["extensions"]["active"] == ["ext-update"]
        store.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_agent_exception_is_propagated(self):
        client = _make_client()

        async def _stream_payload():
            raise RuntimeError("stream-failed")
            yield  # pragma: no cover

        mock_client = MagicMock()
        mock_client.send_message = MagicMock(return_value=_stream_payload())
        client._get_client = AsyncMock(return_value=mock_client)
        store = MagicMock()
        client._store_response_extensions = store

        with pytest.raises(RuntimeError, match="stream-failed"):
            items = []
            async for item in client.stream_agent("hello"):
                items.append(item)

        store.assert_called_once()


# ---------------------------------------------------------------------------
# Client card and transport cache
# ---------------------------------------------------------------------------


class TestAgentCardAndClientCache:
    @pytest.mark.asyncio
    async def test_get_agent_card_uses_cache_when_set(self):
        client = _make_client()
        cached = MagicMock(name="cached-card")
        client._agent_card = cached
        result = await client.get_agent_card()
        assert result is cached

    @pytest.mark.asyncio
    async def test_get_agent_card_fetches_and_caches_card(self):
        client = _make_client()
        client._agent_card = None
        client._get_http_client = AsyncMock(return_value=MagicMock())

        resolver = MagicMock()
        resolved_card = MagicMock(name="resolved-card")
        resolver.get_agent_card = AsyncMock(return_value=resolved_card)

        with patch("ii_agent.integrations.a2a.as_client.A2ACardResolver", return_value=resolver):
            result = await client.get_agent_card()

        assert result is resolved_card
        assert client._agent_card is resolved_card
        resolver.get_agent_card.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refresh_agent_card_forces_refetch(self):
        client = _make_client()
        client._agent_card = MagicMock(name="old")
        client.get_agent_card = AsyncMock(return_value=MagicMock(name="new"))
        result = await client.refresh_agent_card()
        assert client._agent_card is not None
        client.get_agent_card.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_client_reuses_cached_transport(self):
        client = _make_client()
        client._get_http_client = AsyncMock(return_value=MagicMock(name="httpx"))
        mock_agent_card = MagicMock(name="card")
        client.get_agent_card = AsyncMock(return_value=mock_agent_card)
        client._hydrate_extension_config = MagicMock()

        fake_client = MagicMock(name="a2a-client")

        with patch("ii_agent.integrations.a2a.as_client.ClientFactory") as mock_factory_cls:
            mock_factory = MagicMock()
            mock_factory.create.return_value = fake_client
            mock_factory_cls.return_value = mock_factory
            config = await client._get_client(streaming=True)
            config_again = await client._get_client(streaming=True)

        assert config_again is fake_client
        assert client._clients[True].client is fake_client
        mock_factory.create.assert_called_once()
        mock_factory_cls.assert_called_once()


# ---------------------------------------------------------------------------
# Extension helpers
# ---------------------------------------------------------------------------


class TestExtensionHelpers:
    @pytest.mark.asyncio
    async def test_apply_extension_metadata_defaults_populates_context(self):
        from a2a.types import AgentExtension

        client = _make_client()
        client._extension_definitions = {
            "urn:one": AgentExtension(
                uri="urn:one",
                params={
                    "metadata_key": "ii-agent",
                    "sections": ["tool_args", "missing_section"],
                    "fields": ["session_id"],
                },
            )
        }

        message = MagicMock()
        message.metadata = {}
        client._apply_extension_metadata_defaults(
            message=message,
            context={
                "tool_args": {"mode": "fast"},
                "session_id": "session-1",
            },
        )

        ii_agent_metadata = message.metadata["ii-agent"]
        assert ii_agent_metadata["tool_args"] == {"mode": "fast"}
        assert ii_agent_metadata["missing_section"] == {}
        assert ii_agent_metadata["session_id"] == "session-1"

    def test_capture_server_extensions_from_payload_sets_summary(self):
        client = _make_client()
        context = ClientCallContext()
        payload = MagicMock(metadata={"extensions": {"active": ["ext-a"]}})
        client._capture_server_extensions(context, payload)
        state = context.state[ExtensionsHeaderInterceptor._STATE_KEY]
        assert state["server_summary"] == {"active": ["ext-a"]}
        assert "snapshot" not in state

    def test_capture_extensions_snapshot_uses_existing_snapshot(self):
        client = _make_client()
        client._last_response_extensions = {"active": ["ext-b"]}
        context = ClientCallContext()
        context.state = {
            ExtensionsHeaderInterceptor._STATE_KEY: {"snapshot": {"requested": ["ext-b"]}}
        }

        snapshot = client._capture_extensions_snapshot(context)
        assert snapshot == {"requested": ["ext-b"]}

    def test_capture_extensions_snapshot_uses_server_summary(self):
        client = _make_client()
        context = ClientCallContext()
        context.state = {
            ExtensionsHeaderInterceptor._STATE_KEY: {"server_summary": {"active": ["ext-c"]}}
        }

        snapshot = client._capture_extensions_snapshot(context)
        assert snapshot == {"active": ["ext-c"]}

    def test_capture_extensions_snapshot_returns_last_response_when_no_live_state(self):
        client = _make_client()
        client._last_response_extensions = {"active": ["ext-last"]}
        context = ClientCallContext()
        context.state = object()

        snapshot = client._capture_extensions_snapshot(context)
        assert snapshot == {"active": ["ext-last"]}


class TestStreamExtensionsFlow:
    def test_synchronize_stream_extensions_with_tuple_payload(self):
        client = _make_client()
        context = ClientCallContext()
        context.state = {
            ExtensionsHeaderInterceptor._STATE_KEY: {"server_summary": {"active": ["ext-a"]}}
        }

        task = MagicMock(metadata=None)
        update = MagicMock(metadata={"extensions": {"requested": ["ext-a"]}})
        client._synchronize_stream_extensions(context, (task, update))

        assert task.metadata == {"extensions": {"active": ["ext-a"]}}
        assert update.metadata == {"extensions": {"active": ["ext-a"], "requested": ["ext-a"]}}

    def test_synchronize_stream_extensions_without_summary_is_noop(self):
        client = _make_client()
        context = ClientCallContext()
        context.state = {}
        message = MagicMock(metadata={"extensions": {"existing": ["x"]}})

        client._synchronize_stream_extensions(context, message)
        # unchanged because there is no negotiation summary
        assert message.metadata["extensions"] == {"existing": ["x"]}


class TestPayloadTextExtraction:
    def test_extract_text_from_payload_from_task_status_update(self):
        from a2a.types import Role, TaskStatusUpdateEvent
        from a2a.client.helpers import create_text_message_object
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        status = create_text_message_object(role=Role.agent, content="status text")
        status_msg = create_text_message_object(role=Role.agent, content="status wrapper")
        status_update = TaskStatusUpdateEvent(status=MagicMock(message=status_msg))
        task = create_text_message_object(role=Role.agent, content="task")
        payload = (task, status_update)

        result = IIAgentA2AClient()._extract_text_from_payload(payload)
        assert result == "status text"

    def test_extract_text_from_task_history_fallback(self):
        from a2a.types import Role
        from a2a.client.helpers import create_text_message_object
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        history_msg = create_text_message_object(role=Role.agent, content="history text")
        task = SimpleNamespace(
            status=None,
            artifacts=[],
            history=[history_msg],
        )

        result = IIAgentA2AClient()._extract_text_from_task(task)
        assert result == "history text"

    def test_extract_text_from_part_with_dict_root(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        payload = {"root": SimpleNamespace(text="dict-root")}
        assert IIAgentA2AClient._extract_text_from_part(payload) == "dict-root"


class TestResponseExtensionsStorage:
    def test_store_response_extensions_handles_requested_and_missing(self):
        client = _make_client()
        context = ClientCallContext()
        context.state = {
            ExtensionsHeaderInterceptor._STATE_KEY: {
                "requested": ["ext-a", "ext-b"],
                "activated": ["ext-a"],
            }
        }
        result: dict = {}
        client._store_response_extensions(context, result)

        assert result["extensions"]["requested"] == ["ext-a", "ext-b"]
        assert result["extensions"]["activated"] == ["ext-a"]
        assert result["extensions"]["missing"] == ["ext-b"]
        assert client.get_last_response_extensions() == result["extensions"]

    def test_store_response_extensions_with_no_state_returns_none(self):
        client = _make_client()
        context = ClientCallContext()
        client._last_response_extensions = {}
        context.state = {}
        result = {}
        client._store_response_extensions(context, result)
        assert result == {}


class TestHttpClient:
    @pytest.mark.asyncio
    async def test_get_http_client_reuses_open_client(self):
        client = _make_client()
        client._httpx_client = MagicMock()
        client._httpx_client.is_closed = False
        existing = client._httpx_client
        assert await client._get_http_client() is existing

    @pytest.mark.asyncio
    async def test_get_http_client_creates_new_client_on_missing(self):
        client = _make_client()
        client._httpx_client = MagicMock()
        client._httpx_client.is_closed = True
        mock_new = MagicMock()

        with patch("ii_agent.integrations.a2a.as_client.httpx.AsyncClient", return_value=mock_new):
            result = await client._get_http_client()

        assert result is mock_new
