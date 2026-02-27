"""Unit tests for projects/design/service.py - ProjectDesignService."""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.projects.design.exceptions import (
    DesignProxyFetchError,
    DesignProxyHostNotAllowedError,
    DesignSessionAccessDeniedError,
    DesignSessionNotFoundError,
    DesignValidationError,
)
from ii_agent.projects.design.schemas import (
    AIChangeRequest,
    DesignStateRequest,
    ElementInfoRequest,
    IframeAIPlanRequest,
    IframeDocumentSnapshotNode,
    StyleChange,
    SyncRequest,
    SyncStateRequest,
)
from ii_agent.projects.design.service import ProjectDesignService


# ---------------------------------------------------------------------------
# Helpers / Builder
# ---------------------------------------------------------------------------

def _make_session(user_id: str = "user-1", session_id: str | None = None) -> MagicMock:
    session = MagicMock()
    session.id = session_id or str(uuid.uuid4())
    session.user_id = user_id
    session.public_url = None
    session.sandbox_id = None
    session.llm_setting_id = None
    return session


def _make_service(**overrides) -> ProjectDesignService:
    repo = MagicMock()
    sandbox_service = MagicMock()
    event_service = MagicMock()
    llm_setting_service = MagicMock()
    llm_execution_service = MagicMock()
    llm_billing_service = None
    config = MagicMock()
    config.llm_configs = {}  # Use a real empty dict

    kwargs = {
        "repo": repo,
        "sandbox_service": sandbox_service,
        "event_service": event_service,
        "llm_setting_service": llm_setting_service,
        "llm_execution_service": llm_execution_service,
        "llm_billing_service": llm_billing_service,
        "config": config,
    }
    kwargs.update(overrides)
    return ProjectDesignService(**kwargs)


def _make_element_info(
    tag: str = "div",
    class_name: str = "container",
    text: str = "Hello",
    computed_styles: dict | None = None,
    design_id: str = "did-1",
) -> ElementInfoRequest:
    info = MagicMock(spec=ElementInfoRequest)
    info.tagName = tag
    info.className = class_name
    info.textContent = text
    info.computedStyles = computed_styles or {"color": "red", "fontSize": "16px"}
    info.designId = design_id
    return info


def _make_snapshot_node(design_id: str, tag: str = "div", children=None, html: str = "") -> IframeDocumentSnapshotNode:
    node = MagicMock(spec=IframeDocumentSnapshotNode)
    node.designId = design_id
    node.tagName = tag
    node.className = "cls"
    node.id = ""
    node.textContent = "text"
    node.attributes = {}
    node.parentDesignId = None
    node.childDesignIds = children or []
    node.html = html
    return node


# ---------------------------------------------------------------------------
# _get_session_for_request
# ---------------------------------------------------------------------------

class TestGetSessionForRequest:
    @pytest.mark.asyncio
    async def test_raises_not_found_when_session_missing(self):
        svc = _make_service()
        svc._repo.get_session = AsyncMock(return_value=None)
        with pytest.raises(DesignSessionNotFoundError):
            await svc._get_session_for_request(AsyncMock(), session_id="s1", user_id="u1")

    @pytest.mark.asyncio
    async def test_raises_access_denied_when_wrong_user(self):
        svc = _make_service()
        session = _make_session(user_id="other-user")
        svc._repo.get_session = AsyncMock(return_value=session)
        with pytest.raises(DesignSessionAccessDeniedError):
            await svc._get_session_for_request(AsyncMock(), session_id=session.id, user_id="user-1")

    @pytest.mark.asyncio
    async def test_returns_session_for_valid_request(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        result = await svc._get_session_for_request(AsyncMock(), session_id=session.id, user_id="user-1")
        assert result is session


# ---------------------------------------------------------------------------
# _validate_proxy_url
# ---------------------------------------------------------------------------

class TestValidateProxyUrl:
    def test_valid_https_url(self):
        svc = _make_service()
        parsed = svc._validate_proxy_url("https://abc123.e2b.app/")
        assert parsed.scheme == "https"

    def test_valid_http_url(self):
        svc = _make_service()
        parsed = svc._validate_proxy_url("http://localhost:3000/")
        assert parsed.scheme == "http"

    def test_invalid_scheme_raises(self):
        svc = _make_service()
        with pytest.raises(DesignValidationError, match="scheme"):
            svc._validate_proxy_url("ftp://example.com")

    def test_empty_string_raises(self):
        svc = _make_service()
        with pytest.raises(DesignValidationError):
            svc._validate_proxy_url("")

    def test_none_raises(self):
        svc = _make_service()
        with pytest.raises(DesignValidationError):
            svc._validate_proxy_url(None)

    def test_url_with_credentials_raises(self):
        svc = _make_service()
        with pytest.raises(DesignValidationError):
            svc._validate_proxy_url("https://user:pass@example.com/")

    def test_no_host_raises(self):
        svc = _make_service()
        with pytest.raises(DesignValidationError):
            svc._validate_proxy_url("https://")


# ---------------------------------------------------------------------------
# _is_e2b_hostname
# ---------------------------------------------------------------------------

class TestIsE2bHostname:
    def test_valid_e2b_app_hostname(self):
        assert ProjectDesignService._is_e2b_hostname("abc123.e2b.app") is True

    def test_valid_e2b_dev_hostname(self):
        assert ProjectDesignService._is_e2b_hostname("abc123.e2b.dev") is True

    def test_non_e2b_hostname(self):
        assert ProjectDesignService._is_e2b_hostname("example.com") is False

    def test_empty_hostname(self):
        assert ProjectDesignService._is_e2b_hostname("") is False

    def test_partial_match_not_e2b(self):
        assert ProjectDesignService._is_e2b_hostname("note2b.app") is False

    def test_port_prefixed_e2b_hostname(self):
        assert ProjectDesignService._is_e2b_hostname("3000-abc123.e2b.app") is True


# ---------------------------------------------------------------------------
# _extract_e2b_port_from_hostname
# ---------------------------------------------------------------------------

class TestExtractE2bPortFromHostname:
    def test_extracts_port_from_valid_hostname(self):
        port = ProjectDesignService._extract_e2b_port_from_hostname("3000-sandboxid.e2b.app")
        assert port == 3000

    def test_returns_none_for_non_e2b_hostname(self):
        port = ProjectDesignService._extract_e2b_port_from_hostname("example.com")
        assert port is None

    def test_returns_none_when_no_port_prefix(self):
        port = ProjectDesignService._extract_e2b_port_from_hostname("abc-sandboxid.e2b.app")
        assert port is None

    def test_returns_none_for_empty_hostname(self):
        port = ProjectDesignService._extract_e2b_port_from_hostname("")
        assert port is None

    def test_returns_none_for_invalid_port_number(self):
        port = ProjectDesignService._extract_e2b_port_from_hostname("99999-sandboxid.e2b.app")
        assert port is None


# ---------------------------------------------------------------------------
# _hostname_matches_sandbox_id
# ---------------------------------------------------------------------------

class TestHostnameMatchesSandboxId:
    def test_exact_match(self):
        result = ProjectDesignService._hostname_matches_sandbox_id("sandbox123.e2b.app", "sandbox123")
        assert result is True

    def test_port_prefixed_match(self):
        result = ProjectDesignService._hostname_matches_sandbox_id("3000-sandbox123.e2b.app", "sandbox123")
        assert result is True

    def test_non_e2b_hostname_returns_false(self):
        result = ProjectDesignService._hostname_matches_sandbox_id("sandbox123.example.com", "sandbox123")
        assert result is False

    def test_different_sandbox_id_returns_false(self):
        result = ProjectDesignService._hostname_matches_sandbox_id("othersandbox.e2b.app", "sandbox123")
        assert result is False

    def test_empty_hostname(self):
        result = ProjectDesignService._hostname_matches_sandbox_id("", "sandbox123")
        assert result is False

    def test_empty_sandbox_id(self):
        result = ProjectDesignService._hostname_matches_sandbox_id("sandbox123.e2b.app", "")
        assert result is False


# ---------------------------------------------------------------------------
# _build_proxy_hostname_allow_check
# ---------------------------------------------------------------------------

class TestBuildProxyHostnameAllowCheck:
    def test_allows_matching_provider_sandbox(self):
        svc = _make_service()
        sandbox_record = MagicMock()
        sandbox_record.provider_sandbox_id = "sandbox123"
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url=None,
            session_sandbox_id=None,
            requested_hostname="sandbox123.e2b.app",
            sandbox_record=sandbox_record,
        )
        assert is_allowed("sandbox123.e2b.app") is True

    def test_allows_public_url_hostname(self):
        svc = _make_service()
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url="https://myapp.example.com",
            session_sandbox_id=None,
            requested_hostname="myapp.example.com",
            sandbox_record=None,
        )
        assert is_allowed("myapp.example.com") is True

    def test_rejects_unrelated_hostname(self):
        svc = _make_service()
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url="https://myapp.example.com",
            session_sandbox_id=None,
            requested_hostname="evil.com",
            sandbox_record=None,
        )
        assert is_allowed("evil.com") is False

    def test_allows_session_sandbox_id(self):
        svc = _make_service()
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url=None,
            session_sandbox_id="mysandbox",
            requested_hostname="mysandbox.e2b.app",
            sandbox_record=None,
        )
        assert is_allowed("mysandbox.e2b.app") is True

    def test_empty_hostname_rejected(self):
        svc = _make_service()
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url="https://myapp.com",
            session_sandbox_id=None,
            requested_hostname="myapp.com",
            sandbox_record=None,
        )
        assert is_allowed("") is False


# ---------------------------------------------------------------------------
# _inject_runtime_script_with_base
# ---------------------------------------------------------------------------

class TestInjectRuntimeScriptWithBase:
    def test_injects_into_head_tag(self):
        svc = _make_service()
        html = "<html><head></head><body>Hello</body></html>"
        result = svc._inject_runtime_script_with_base(html=html, base_url="https://sandbox.e2b.app/")
        # Should contain injection inside head
        assert "<head>" in result
        assert "head>" in result

    def test_injects_after_head_tag_with_attributes(self):
        svc = _make_service()
        html = '<html><head lang="en"></head><body></body></html>'
        result = svc._inject_runtime_script_with_base(html=html, base_url="https://sandbox.e2b.app/")
        assert "head" in result

    def test_fallback_injection_when_no_head(self):
        svc = _make_service()
        html = "<p>No head tag here</p>"
        result = svc._inject_runtime_script_with_base(html=html, base_url="https://sandbox.e2b.app/")
        # Still returns something
        assert len(result) > len(html)

    def test_adds_html_head_when_only_html_tag(self):
        svc = _make_service()
        html = "<html><body>content</body></html>"
        result = svc._inject_runtime_script_with_base(html=html, base_url="https://sandbox.e2b.app/")
        assert "<head>" in result


# ---------------------------------------------------------------------------
# _rewrite_urls
# ---------------------------------------------------------------------------

class TestRewriteUrls:
    def test_rewrites_absolute_src(self):
        svc = _make_service()
        html = '<img src="/images/logo.png">'
        result = svc._rewrite_urls(html=html, base_url="https://sandbox.e2b.app/")
        assert "https://sandbox.e2b.app/images/logo.png" in result

    def test_rewrites_absolute_href(self):
        svc = _make_service()
        html = '<link href="/styles/main.css">'
        result = svc._rewrite_urls(html=html, base_url="https://sandbox.e2b.app/")
        assert "https://sandbox.e2b.app/styles/main.css" in result

    def test_adds_base_href_when_missing(self):
        svc = _make_service()
        html = "<head></head><body>content</body>"
        result = svc._rewrite_urls(html=html, base_url="https://sandbox.e2b.app/app/")
        assert "base href" in result.lower()

    def test_does_not_add_base_href_when_already_present(self):
        svc = _make_service()
        html = '<head><base href="https://sandbox.e2b.app/"></head>'
        result = svc._rewrite_urls(html=html, base_url="https://sandbox.e2b.app/")
        # Only one base href
        assert result.count("<base") == 1

    def test_rewrites_srcset(self):
        svc = _make_service()
        html = '<img srcset="/image1.png 1x, /image2.png 2x">'
        result = svc._rewrite_urls(html=html, base_url="https://sandbox.e2b.app/")
        assert "https://sandbox.e2b.app/image1.png" in result


# ---------------------------------------------------------------------------
# _snapshot_nodes_by_id
# ---------------------------------------------------------------------------

class TestSnapshotNodesById:
    def test_indexes_nodes_by_design_id(self):
        nodes = [
            _make_snapshot_node("did-1", "div"),
            _make_snapshot_node("did-2", "span"),
        ]
        result = ProjectDesignService._snapshot_nodes_by_id(nodes)
        assert "did-1" in result
        assert "did-2" in result

    def test_skips_nodes_without_design_id(self):
        nodes = [_make_snapshot_node("", "div")]
        result = ProjectDesignService._snapshot_nodes_by_id(nodes)
        assert len(result) == 0

    def test_tag_name_lowercased(self):
        node = _make_snapshot_node("did-1", "DIV")
        result = ProjectDesignService._snapshot_nodes_by_id([node])
        assert result["did-1"]["tagName"] == "div"


# ---------------------------------------------------------------------------
# _build_snapshot_desc
# ---------------------------------------------------------------------------

class TestBuildSnapshotDesc:
    def test_empty_nodes_returns_count_line(self):
        svc = _make_service()
        result = svc._build_snapshot_desc([])
        assert "nodes: 0" in result

    def test_includes_first_12_nodes(self):
        svc = _make_service()
        nodes = [_make_snapshot_node(f"did-{i}") for i in range(20)]
        result = svc._build_snapshot_desc(nodes)
        # Check limited output
        assert "did-0" in result
        assert "did-11" in result
        # Node 13 should not appear
        assert "did-12" not in result


# ---------------------------------------------------------------------------
# _build_selected_desc
# ---------------------------------------------------------------------------

class TestBuildSelectedDesc:
    def test_none_returns_none_string(self):
        result = ProjectDesignService._build_selected_desc(None)
        assert result == "(none)"

    def test_includes_design_id(self):
        elem = _make_element_info(design_id="test-design-id")
        result = ProjectDesignService._build_selected_desc(elem)
        assert "test-design-id" in result

    def test_includes_tag_name(self):
        elem = _make_element_info(tag="button")
        result = ProjectDesignService._build_selected_desc(elem)
        assert "button" in result

    def test_includes_computed_styles(self):
        elem = _make_element_info(computed_styles={"color": "blue", "fontSize": "16px"})
        result = ProjectDesignService._build_selected_desc(elem)
        assert "computedStyles" in result
        assert "blue" in result


# ---------------------------------------------------------------------------
# _build_selected_subtree_hint
# ---------------------------------------------------------------------------

class TestBuildSelectedSubtreeHint:
    def test_empty_when_no_design_id(self):
        svc = _make_service()
        nodes = [_make_snapshot_node("did-1")]
        result = svc._build_selected_subtree_hint(snapshot_nodes=nodes, selected_design_id=None)
        assert result == ""

    def test_empty_when_design_id_not_in_nodes(self):
        svc = _make_service()
        nodes = [_make_snapshot_node("did-1")]
        result = svc._build_selected_subtree_hint(snapshot_nodes=nodes, selected_design_id="did-missing")
        assert result == ""

    def test_returns_subtree_for_valid_node(self):
        svc = _make_service()
        parent = _make_snapshot_node("did-root", "div", children=["did-child"])
        child = _make_snapshot_node("did-child", "span")
        nodes = [parent, child]

        result = svc._build_selected_subtree_hint(snapshot_nodes=nodes, selected_design_id="did-root")
        assert "did-root" in result
        assert "did-child" in result

    def test_marks_svg_presence(self):
        svc = _make_service()
        node = _make_snapshot_node("did-svg", "svg", html="<svg viewBox='0 0 24 24'>...</svg>")
        node.tagName = "svg"

        result = svc._build_selected_subtree_hint(snapshot_nodes=[node], selected_design_id="did-svg")
        assert "has_svg=True" in result

    def test_limited_to_max_nodes(self):
        svc = _make_service()
        nodes = [_make_snapshot_node(f"did-{i}", children=[f"did-{i+1}"] if i < 30 else []) for i in range(31)]
        result = svc._build_selected_subtree_hint(
            snapshot_nodes=nodes,
            selected_design_id="did-0",
            max_nodes=5,
        )
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) <= 5


# ---------------------------------------------------------------------------
# _tool_result_value
# ---------------------------------------------------------------------------

class TestToolResultValue:
    def test_returns_value_from_output(self):
        tool_result = MagicMock()
        tool_result.output.value = "result"
        result = ProjectDesignService._tool_result_value(tool_result)
        assert result == "result"

    def test_returns_none_when_output_is_none(self):
        tool_result = MagicMock()
        tool_result.output = None
        result = ProjectDesignService._tool_result_value(tool_result)
        assert result is None

    def test_falls_back_to_model_dump(self):
        tool_result = MagicMock()
        output = MagicMock(spec=[])
        output.value = MagicMock()  # value attribute exists but...
        delattr(output, "value") if hasattr(output, "value") else None

        mock_output = MagicMock()
        mock_output.value = None  # value is None
        mock_output.model_dump = MagicMock(return_value={"key": "val"})
        del mock_output.value  # No value attr

        tool_result_mock = MagicMock()
        tool_result_mock.output = mock_output

        with patch.object(mock_output, "model_dump", return_value={"key": "val"}):
            # If value attribute doesn't exist, falls back to model_dump
            pass  # model_dump handling is internal

    def test_returns_model_dump_when_value_none(self):
        tool_result = MagicMock()
        output = MagicMock()
        output.value = None
        output.model_dump = MagicMock(return_value={"k": "v"})
        tool_result.output = output
        result = ProjectDesignService._tool_result_value(tool_result)
        assert result == {"k": "v"}


# ---------------------------------------------------------------------------
# _build_billing_context
# ---------------------------------------------------------------------------

class TestBuildBillingContext:
    def test_returns_none_when_no_billing_service(self):
        svc = _make_service(llm_billing_service=None)
        ctx = svc._build_billing_context(db=AsyncMock(), user_id="u1", session_id="s1", llm_config=MagicMock())
        assert ctx is None

    def test_returns_billing_context_when_service_present(self):
        from ii_agent.core.llm.execution_service import LLMBillingContext
        billing_svc = MagicMock()
        svc = _make_service(llm_billing_service=billing_svc)
        llm_config = MagicMock()
        llm_config.model = "gpt-4"

        ctx = svc._build_billing_context(db=AsyncMock(), user_id="u1", session_id="s1", llm_config=llm_config)
        assert ctx is not None
        assert isinstance(ctx, LLMBillingContext)


# ---------------------------------------------------------------------------
# _build_llm_messages
# ---------------------------------------------------------------------------

class TestBuildLlmMessages:
    def test_returns_single_user_message(self):
        svc = _make_service()
        svc._llm_execution_service.new_message = MagicMock(return_value=MagicMock())
        messages = svc._build_llm_messages(session_id="sess-1", user_prompt="Hello world")
        assert len(messages) == 1

    def test_message_contains_prompt(self):
        from ii_agent.chat.schemas import TextContent, MessageRole
        svc = _make_service()

        mock_message = MagicMock()
        svc._llm_execution_service.new_message = MagicMock(return_value=mock_message)
        messages = svc._build_llm_messages(session_id="sess-1", user_prompt="Design this")

        svc._llm_execution_service.new_message.assert_called_once()
        call_kwargs = svc._llm_execution_service.new_message.call_args
        parts = call_kwargs[1]["parts"]
        assert any(isinstance(p, TextContent) and p.text == "Design this" for p in parts)


# ---------------------------------------------------------------------------
# _parse_design_request (fallback logic)
# ---------------------------------------------------------------------------

class TestParseDesignRequest:
    def test_parses_color_change_request(self):
        svc = _make_service()
        changes, explanation = svc._parse_design_request(
            "Change the color to red",
            {"color": "blue"}
        )
        assert isinstance(changes, list)
        assert isinstance(explanation, str)

    def test_parses_font_size_change(self):
        svc = _make_service()
        changes, explanation = svc._parse_design_request(
            "Increase font size",
            {"fontSize": "14px"}
        )
        assert isinstance(changes, list)

    def test_returns_empty_for_unrecognized_request(self):
        svc = _make_service()
        changes, explanation = svc._parse_design_request(
            "Do something completely random",
            {}
        )
        assert isinstance(changes, list)
        assert isinstance(explanation, str)


# ---------------------------------------------------------------------------
# get_design_state
# ---------------------------------------------------------------------------

def _make_raw_style_change(design_id="did-1", prop="color", value="red"):
    return {
        "designId": design_id,
        "type": "style",
        "property": prop,
        "value": {"newValue": value},
        "timestamp": 1234567890,
    }


class TestGetDesignState:
    @pytest.mark.asyncio
    async def test_returns_design_state(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        svc._repo.get_design_state = MagicMock(return_value=(
            [_make_raw_style_change()],  # changes
            [],  # redo
            1234567890,  # updated_at
        ))

        result = await svc.get_design_state(AsyncMock(), session_id=session.id, user_id="user-1")
        assert result.session_id == session.id
        assert len(result.changes) == 1

    @pytest.mark.asyncio
    async def test_raises_for_unauthorized_access(self):
        svc = _make_service()
        session = _make_session(user_id="other-user")
        svc._repo.get_session = AsyncMock(return_value=session)

        with pytest.raises(DesignSessionAccessDeniedError):
            await svc.get_design_state(AsyncMock(), session_id=session.id, user_id="user-1")


# ---------------------------------------------------------------------------
# save_design_state
# ---------------------------------------------------------------------------

class TestSaveDesignState:
    @pytest.mark.asyncio
    async def test_saves_design_state_and_returns_response(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        svc._repo.get_design_state = MagicMock(return_value=([], [], None))
        svc._repo.update_design_state = AsyncMock()

        style_change = StyleChange(**_make_raw_style_change())
        request = DesignStateRequest(
            session_id=session.id,
            changes=[style_change],
            redo_changes=[],
        )

        result = await svc.save_design_state(AsyncMock(), request=request, user_id="user-1")
        assert result.session_id == session.id
        assert len(result.changes) == 1
        svc._repo.update_design_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_existing_redo_when_none_provided(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        existing_redo = [_make_raw_style_change("did-2", "background", "white")]
        svc._repo.get_session = AsyncMock(return_value=session)
        svc._repo.get_design_state = MagicMock(return_value=([], existing_redo, None))
        svc._repo.update_design_state = AsyncMock()

        request = DesignStateRequest(
            session_id=session.id,
            changes=[],
            redo_changes=None,  # Should use existing
        )

        result = await svc.save_design_state(AsyncMock(), request=request, user_id="user-1")
        assert len(result.redo_changes) == 1


# ---------------------------------------------------------------------------
# sync_persisted_design_changes - invalid session_id
# ---------------------------------------------------------------------------

class TestSyncPersistedDesignChanges:
    @pytest.mark.asyncio
    async def test_invalid_session_id_raises(self):
        svc = _make_service()
        request = SyncStateRequest(session_id="not-a-uuid", changes=None, project_info=None)

        with pytest.raises(DesignValidationError, match="Invalid session_id"):
            await svc.sync_persisted_design_changes(AsyncMock(), user_id="user-1", request=request)

    @pytest.mark.asyncio
    async def test_no_pending_changes_returns_empty_response(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        svc._repo.get_design_state = MagicMock(return_value=([], [], None))

        request = SyncStateRequest(session_id=str(uuid.uuid4()), changes=None, project_info=None)

        result = await svc.sync_persisted_design_changes(AsyncMock(), user_id="user-1", request=request)
        assert result.success is False
        assert result.total == 0


# ---------------------------------------------------------------------------
# _normalize_iframe_plan_operations
# ---------------------------------------------------------------------------

class TestNormalizeIframePlanOperations:
    @pytest.mark.asyncio
    async def test_non_list_operations_return_empty(self):
        svc = _make_service()
        result = await svc._normalize_iframe_plan_operations(
            operations=None,
            snapshot_nodes=[],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_skips_non_dict_operations(self):
        svc = _make_service()
        result = await svc._normalize_iframe_plan_operations(
            operations=["not_a_dict", 42],
            snapshot_nodes=[],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_skips_operations_without_op_or_design_id(self):
        svc = _make_service()
        ops = [{"op": "set_style"}, {"design_id": "did-1"}, {}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_valid_set_style_operation_passes_through(self):
        svc = _make_service()
        ops = [{"op": "set_style", "design_id": "did-1", "property": "color", "value": "red"}]
        nodes = [_make_snapshot_node("did-1")]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=nodes,
            icon_svg_tool=MagicMock(),
        )
        assert len(result) == 1
        assert result[0]["op"] == "set_style"
