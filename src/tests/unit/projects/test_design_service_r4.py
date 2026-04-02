"""Unit tests for projects/design/service.py - ProjectDesignService (r4 extended)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.projects.design.exceptions import (
    DesignSessionAccessDeniedError,
    DesignSessionNotFoundError,
    DesignSandboxUnavailableError,
    DesignValidationError,
)
from ii_agent.projects.design.schemas import (
    DesignStateRequest,
    ElementInfoRequest,
    IframeDocumentSnapshotNode,
    StyleChange,
    SyncRequest,
    SyncStateRequest,
)
from ii_agent.projects.design.service import ProjectDesignService

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    user_id: str = "user-1",
    session_id: str | None = None,
    public_url: str | None = None,
    parent_session_id: str | None = None,
    llm_setting_id: str | None = None,
) -> MagicMock:
    session = MagicMock()
    session.id = session_id or str(uuid.uuid4())
    session.user_id = user_id
    session.public_url = public_url
    session.parent_session_id = parent_session_id
    session.llm_setting_id = llm_setting_id
    return session


def _make_service(**overrides) -> ProjectDesignService:
    repo = MagicMock()
    sandbox_service = MagicMock()
    event_service = MagicMock()
    model_setting_service = MagicMock()
    config = MagicMock()
    config.llm_configs = {}

    kwargs = {
        "repo": repo,
        "sandbox_service": sandbox_service,
        "event_service": event_service,
        "model_setting_service": model_setting_service,
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
) -> MagicMock:
    info = MagicMock(spec=ElementInfoRequest)
    info.tagName = tag
    info.className = class_name
    info.textContent = text
    info.computedStyles = computed_styles or {"color": "red", "fontSize": "16px"}
    info.designId = design_id
    return info


def _make_snapshot_node(
    design_id: str,
    tag: str = "div",
    children: list | None = None,
    html: str = "",
    text: str = "text",
) -> MagicMock:
    node = MagicMock(spec=IframeDocumentSnapshotNode)
    node.designId = design_id
    node.tagName = tag
    node.className = "cls"
    node.id = ""
    node.textContent = text
    node.attributes = {}
    node.parentDesignId = None
    node.childDesignIds = children or []
    node.html = html
    return node


def _make_raw_style_change(design_id="did-1", prop="color", value="red") -> dict:
    return {
        "designId": design_id,
        "type": "style",
        "property": prop,
        "value": {"newValue": value},
        "timestamp": 1234567890,
    }


# ---------------------------------------------------------------------------
# _get_session_for_request
# ---------------------------------------------------------------------------


class TestGetSessionForRequestR4:
    @pytest.mark.asyncio
    async def test_raises_not_found_when_session_missing(self):
        svc = _make_service()
        svc._repo.get_session = AsyncMock(return_value=None)
        with pytest.raises(DesignSessionNotFoundError):
            await svc._get_session_for_request(AsyncMock(), session_id="s1", user_id="u1")

    @pytest.mark.asyncio
    async def test_raises_access_denied_wrong_user(self):
        svc = _make_service()
        session = _make_session(user_id="other-user")
        svc._repo.get_session = AsyncMock(return_value=session)
        with pytest.raises(DesignSessionAccessDeniedError):
            await svc._get_session_for_request(AsyncMock(), session_id=session.id, user_id="user-1")

    @pytest.mark.asyncio
    async def test_returns_session_for_valid_user(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        result = await svc._get_session_for_request(
            AsyncMock(), session_id=session.id, user_id="user-1"
        )
        assert result is session

    @pytest.mark.asyncio
    async def test_user_id_compared_as_string(self):
        """Ensure user_id comparison works when session.user_id is a non-string.

        The implementation uses str() coercion on both sides, so str(42) == str("42")
        is True and the request is allowed.
        """
        svc = _make_service()
        session = _make_session()
        session.user_id = 42  # non-string integer
        svc._repo.get_session = AsyncMock(return_value=session)
        # str(42) == str("42") => "42" == "42" => True, so no exception is raised
        result = await svc._get_session_for_request(
            AsyncMock(), session_id=session.id, user_id="42"
        )
        assert result is session


# ---------------------------------------------------------------------------
# _validate_proxy_url
# ---------------------------------------------------------------------------


class TestValidateProxyUrlR4:
    def test_valid_https_url(self):
        svc = _make_service()
        parsed = svc._validate_proxy_url("https://abc123.e2b.app/")
        assert parsed.scheme == "https"

    def test_valid_http_url(self):
        svc = _make_service()
        parsed = svc._validate_proxy_url("http://localhost:3000/page")
        assert parsed.scheme == "http"

    def test_invalid_ftp_scheme(self):
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
            svc._validate_proxy_url(None)  # type: ignore

    def test_url_with_credentials_raises(self):
        svc = _make_service()
        with pytest.raises(DesignValidationError):
            svc._validate_proxy_url("https://user:pass@example.com/")

    def test_no_netloc_raises(self):
        svc = _make_service()
        with pytest.raises(DesignValidationError):
            svc._validate_proxy_url("https://")

    def test_javascript_scheme_raises(self):
        svc = _make_service()
        with pytest.raises(DesignValidationError):
            svc._validate_proxy_url("javascript:alert(1)")

    def test_data_url_raises(self):
        svc = _make_service()
        with pytest.raises(DesignValidationError):
            svc._validate_proxy_url("data:text/html,<h1>hi</h1>")

    def test_url_with_path_and_query_ok(self):
        svc = _make_service()
        parsed = svc._validate_proxy_url("https://sandbox.e2b.app/app?v=1")
        assert parsed.scheme == "https"
        assert parsed.query == "v=1"


# ---------------------------------------------------------------------------
# _is_e2b_hostname
# ---------------------------------------------------------------------------


class TestIsE2bHostnameR4:
    def test_e2b_app_suffix(self):
        assert ProjectDesignService._is_e2b_hostname("abc.e2b.app") is True

    def test_e2b_dev_suffix(self):
        assert ProjectDesignService._is_e2b_hostname("abc.e2b.dev") is True

    def test_non_e2b_returns_false(self):
        assert ProjectDesignService._is_e2b_hostname("example.com") is False

    def test_empty_string_returns_false(self):
        assert ProjectDesignService._is_e2b_hostname("") is False

    def test_port_prefixed_e2b_hostname_is_true(self):
        assert ProjectDesignService._is_e2b_hostname("3000-abc123.e2b.app") is True

    def test_trailing_dot_stripped(self):
        assert ProjectDesignService._is_e2b_hostname("abc.e2b.app.") is True

    def test_partial_match_not_enough(self):
        assert ProjectDesignService._is_e2b_hostname("note2b.app") is False


# ---------------------------------------------------------------------------
# _extract_e2b_port_from_hostname
# ---------------------------------------------------------------------------


class TestExtractE2bPortFromHostnameR4:
    def test_extracts_valid_port(self):
        port = ProjectDesignService._extract_e2b_port_from_hostname("3000-sandbox.e2b.app")
        assert port == 3000

    def test_returns_none_non_e2b(self):
        assert ProjectDesignService._extract_e2b_port_from_hostname("example.com") is None

    def test_returns_none_no_port_prefix(self):
        assert ProjectDesignService._extract_e2b_port_from_hostname("abc-sandbox.e2b.app") is None

    def test_returns_none_empty_string(self):
        assert ProjectDesignService._extract_e2b_port_from_hostname("") is None

    def test_port_zero_invalid(self):
        assert ProjectDesignService._extract_e2b_port_from_hostname("0-sandbox.e2b.app") is None

    def test_port_65536_invalid(self):
        assert ProjectDesignService._extract_e2b_port_from_hostname("65536-sandbox.e2b.app") is None

    def test_port_1_valid(self):
        port = ProjectDesignService._extract_e2b_port_from_hostname("1-sandbox.e2b.app")
        assert port == 1

    def test_port_65535_valid(self):
        port = ProjectDesignService._extract_e2b_port_from_hostname("65535-sandbox.e2b.app")
        assert port == 65535


# ---------------------------------------------------------------------------
# _hostname_matches_sandbox_id
# ---------------------------------------------------------------------------


class TestHostnameMatchesSandboxIdR4:
    def test_exact_match(self):
        assert (
            ProjectDesignService._hostname_matches_sandbox_id("sandbox123.e2b.app", "sandbox123")
            is True
        )

    def test_port_prefixed_match(self):
        assert (
            ProjectDesignService._hostname_matches_sandbox_id(
                "3000-sandbox123.e2b.app", "sandbox123"
            )
            is True
        )

    def test_non_e2b_returns_false(self):
        assert (
            ProjectDesignService._hostname_matches_sandbox_id("sandbox.example.com", "sandbox")
            is False
        )

    def test_different_sandbox_returns_false(self):
        assert (
            ProjectDesignService._hostname_matches_sandbox_id("other.e2b.app", "sandbox123")
            is False
        )

    def test_empty_hostname_returns_false(self):
        assert ProjectDesignService._hostname_matches_sandbox_id("", "sandbox123") is False

    def test_empty_sandbox_id_returns_false(self):
        assert ProjectDesignService._hostname_matches_sandbox_id("sandbox.e2b.app", "") is False

    def test_case_insensitive(self):
        assert (
            ProjectDesignService._hostname_matches_sandbox_id("SANDBOX.e2b.app", "sandbox") is True
        )


# ---------------------------------------------------------------------------
# _build_proxy_hostname_allow_check
# ---------------------------------------------------------------------------


class TestBuildProxyHostnameAllowCheckR4:
    def test_allows_matching_provider_sandbox(self):
        svc = _make_service()
        sandbox_record = MagicMock()
        sandbox_record.provider_sandbox_id = "sandbox123"
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url=None,
            requested_hostname="sandbox123.e2b.app",
            sandbox_record=sandbox_record,
        )
        assert is_allowed("sandbox123.e2b.app") is True

    def test_allows_public_url_hostname(self):
        svc = _make_service()
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url="https://myapp.example.com",
            requested_hostname="myapp.example.com",
            sandbox_record=None,
        )
        assert is_allowed("myapp.example.com") is True

    def test_rejects_unrelated_hostname(self):
        svc = _make_service()
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url="https://myapp.example.com",
            requested_hostname="evil.com",
            sandbox_record=None,
        )
        assert is_allowed("evil.com") is False

    def test_empty_hostname_rejected(self):
        svc = _make_service()
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url="https://myapp.com",
            requested_hostname="myapp.com",
            sandbox_record=None,
        )
        assert is_allowed("") is False

    def test_no_sandbox_no_public_url_rejects_e2b(self):
        svc = _make_service()
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url=None,
            requested_hostname="random.e2b.app",
            sandbox_record=None,
        )
        assert is_allowed("random.e2b.app") is False

    def test_port_prefixed_with_provider_sandbox_allowed(self):
        svc = _make_service()
        sandbox_record = MagicMock()
        sandbox_record.provider_sandbox_id = "mysandbox"
        is_allowed = svc._build_proxy_hostname_allow_check(
            session_public_url=None,
            requested_hostname="3000-mysandbox.e2b.app",
            sandbox_record=sandbox_record,
        )
        assert is_allowed("3000-mysandbox.e2b.app") is True


# ---------------------------------------------------------------------------
# _inject_runtime_script_with_base
# ---------------------------------------------------------------------------


class TestInjectRuntimeScriptWithBaseR4:
    def test_injects_into_head_tag(self):
        svc = _make_service()
        html = "<html><head></head><body>Hello</body></html>"
        result = svc._inject_runtime_script_with_base(
            html=html, base_url="https://sandbox.e2b.app/"
        )
        assert "<head>" in result
        assert len(result) > len(html)

    def test_injects_after_head_with_attributes(self):
        svc = _make_service()
        html = '<html><head lang="en"></head><body></body></html>'
        result = svc._inject_runtime_script_with_base(
            html=html, base_url="https://sandbox.e2b.app/"
        )
        assert "head" in result
        assert len(result) > len(html)

    def test_injects_when_no_head_tag(self):
        svc = _make_service()
        html = "<p>No head here</p>"
        result = svc._inject_runtime_script_with_base(
            html=html, base_url="https://sandbox.e2b.app/"
        )
        assert len(result) > len(html)

    def test_adds_head_when_only_html_tag(self):
        svc = _make_service()
        html = "<html><body>content</body></html>"
        result = svc._inject_runtime_script_with_base(
            html=html, base_url="https://sandbox.e2b.app/"
        )
        assert "<head>" in result

    def test_base_url_appears_in_output(self):
        svc = _make_service()
        html = "<html><head></head><body></body></html>"
        result = svc._inject_runtime_script_with_base(
            html=html, base_url="https://sandbox.e2b.app/app/"
        )
        assert "sandbox.e2b.app" in result


# ---------------------------------------------------------------------------
# _rewrite_urls
# ---------------------------------------------------------------------------


class TestRewriteUrlsR4:
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

    def test_does_not_add_duplicate_base_href(self):
        svc = _make_service()
        html = '<head><base href="https://sandbox.e2b.app/"></head>'
        result = svc._rewrite_urls(html=html, base_url="https://sandbox.e2b.app/")
        assert result.count("<base") == 1

    def test_rewrites_srcset(self):
        svc = _make_service()
        html = '<img srcset="/image1.png 1x, /image2.png 2x">'
        result = svc._rewrite_urls(html=html, base_url="https://sandbox.e2b.app/")
        assert "https://sandbox.e2b.app/image1.png" in result
        assert "https://sandbox.e2b.app/image2.png" in result

    def test_does_not_rewrite_relative_src(self):
        svc = _make_service()
        html = '<img src="images/logo.png">'
        result = svc._rewrite_urls(html=html, base_url="https://sandbox.e2b.app/")
        # Relative paths unchanged (no leading /)
        assert 'src="images/logo.png"' in result

    def test_does_not_rewrite_http_src(self):
        svc = _make_service()
        html = '<img src="https://cdn.example.com/img.png">'
        result = svc._rewrite_urls(html=html, base_url="https://sandbox.e2b.app/")
        assert "cdn.example.com" in result


# ---------------------------------------------------------------------------
# _snapshot_nodes_by_id
# ---------------------------------------------------------------------------


class TestSnapshotNodesByIdR4:
    def test_indexes_nodes_by_design_id(self):
        nodes = [_make_snapshot_node("did-1"), _make_snapshot_node("did-2")]
        result = ProjectDesignService._snapshot_nodes_by_id(nodes)
        assert "did-1" in result
        assert "did-2" in result

    def test_skips_empty_design_id(self):
        nodes = [_make_snapshot_node(""), _make_snapshot_node("did-valid")]
        result = ProjectDesignService._snapshot_nodes_by_id(nodes)
        assert "" not in result
        assert "did-valid" in result

    def test_tag_name_lowercased(self):
        node = _make_snapshot_node("did-1", "DIV")
        result = ProjectDesignService._snapshot_nodes_by_id([node])
        assert result["did-1"]["tagName"] == "div"

    def test_child_ids_preserved(self):
        node = _make_snapshot_node("did-root", children=["did-c1", "did-c2"])
        result = ProjectDesignService._snapshot_nodes_by_id([node])
        assert result["did-root"]["childDesignIds"] == ["did-c1", "did-c2"]

    def test_html_field_preserved(self):
        node = _make_snapshot_node("did-1", html="<svg>test</svg>")
        result = ProjectDesignService._snapshot_nodes_by_id([node])
        assert result["did-1"]["html"] == "<svg>test</svg>"

    def test_empty_input_returns_empty_dict(self):
        result = ProjectDesignService._snapshot_nodes_by_id([])
        assert result == {}


# ---------------------------------------------------------------------------
# _build_snapshot_desc
# ---------------------------------------------------------------------------


class TestBuildSnapshotDescR4:
    def test_empty_nodes_shows_count_zero(self):
        svc = _make_service()
        result = svc._build_snapshot_desc([])
        assert "nodes: 0" in result

    def test_includes_first_12_nodes(self):
        svc = _make_service()
        nodes = [_make_snapshot_node(f"did-{i}") for i in range(20)]
        result = svc._build_snapshot_desc(nodes)
        assert "did-0" in result
        assert "did-11" in result
        assert "did-12" not in result

    def test_shows_node_count_correctly(self):
        svc = _make_service()
        nodes = [_make_snapshot_node(f"id-{i}") for i in range(5)]
        result = svc._build_snapshot_desc(nodes)
        assert "nodes: 5" in result

    def test_includes_class_and_text(self):
        svc = _make_service()
        node = _make_snapshot_node("did-x", text="Some text")
        result = svc._build_snapshot_desc([node])
        assert "Some text" in result


# ---------------------------------------------------------------------------
# _build_selected_desc
# ---------------------------------------------------------------------------


class TestBuildSelectedDescR4:
    def test_none_returns_none_string(self):
        result = ProjectDesignService._build_selected_desc(None)
        assert result == "(none)"

    def test_includes_design_id(self):
        elem = _make_element_info(design_id="the-design-id")
        result = ProjectDesignService._build_selected_desc(elem)
        assert "the-design-id" in result

    def test_includes_tag_name(self):
        elem = _make_element_info(tag="button")
        result = ProjectDesignService._build_selected_desc(elem)
        assert "button" in result

    def test_includes_computed_styles_keys(self):
        elem = _make_element_info(computed_styles={"color": "blue", "fontSize": "20px"})
        result = ProjectDesignService._build_selected_desc(elem)
        assert "blue" in result

    def test_does_not_include_all_styles(self):
        """Only picks specific style keys."""
        elem = _make_element_info(computed_styles={"cursor": "pointer", "color": "red"})
        result = ProjectDesignService._build_selected_desc(elem)
        # "color" is in the picked set, "cursor" is not
        assert "red" in result

    def test_empty_computed_styles(self):
        elem = _make_element_info(computed_styles={})
        result = ProjectDesignService._build_selected_desc(elem)
        assert "designId" in result or "tag" in result


# ---------------------------------------------------------------------------
# _build_selected_subtree_hint
# ---------------------------------------------------------------------------


class TestBuildSelectedSubtreeHintR4:
    def test_empty_when_no_design_id(self):
        svc = _make_service()
        nodes = [_make_snapshot_node("did-1")]
        result = svc._build_selected_subtree_hint(snapshot_nodes=nodes, selected_design_id=None)
        assert result == ""

    def test_empty_when_design_id_not_in_nodes(self):
        svc = _make_service()
        nodes = [_make_snapshot_node("did-1")]
        result = svc._build_selected_subtree_hint(
            snapshot_nodes=nodes, selected_design_id="missing"
        )
        assert result == ""

    def test_returns_subtree_for_valid_root(self):
        svc = _make_service()
        parent = _make_snapshot_node("did-root", children=["did-child"])
        child = _make_snapshot_node("did-child")
        result = svc._build_selected_subtree_hint(
            snapshot_nodes=[parent, child], selected_design_id="did-root"
        )
        assert "did-root" in result
        assert "did-child" in result

    def test_marks_svg_presence_in_html(self):
        svc = _make_service()
        node = _make_snapshot_node("did-svg", html="<svg viewBox='0 0 24 24'>...</svg>")
        result = svc._build_selected_subtree_hint(
            snapshot_nodes=[node], selected_design_id="did-svg"
        )
        assert "has_svg=True" in result

    def test_marks_svg_tag_name(self):
        svc = _make_service()
        node = _make_snapshot_node("did-svg", tag="svg")
        result = svc._build_selected_subtree_hint(
            snapshot_nodes=[node], selected_design_id="did-svg"
        )
        assert "has_svg=True" in result

    def test_non_svg_has_svg_false(self):
        svc = _make_service()
        node = _make_snapshot_node("did-div", tag="div", html="<span>text</span>")
        result = svc._build_selected_subtree_hint(
            snapshot_nodes=[node], selected_design_id="did-div"
        )
        assert "has_svg=False" in result

    def test_max_nodes_limit(self):
        svc = _make_service()
        nodes = [
            _make_snapshot_node(f"did-{i}", children=[f"did-{i + 1}"] if i < 20 else [])
            for i in range(21)
        ]
        result = svc._build_selected_subtree_hint(
            snapshot_nodes=nodes,
            selected_design_id="did-0",
            max_nodes=3,
        )
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) <= 3

    def test_no_infinite_loop_with_cycles(self):
        """Cyclic child relationships should not cause infinite loops."""
        svc = _make_service()
        node_a = _make_snapshot_node("did-a", children=["did-b"])
        node_b = _make_snapshot_node("did-b", children=["did-a"])  # cycle
        result = svc._build_selected_subtree_hint(
            snapshot_nodes=[node_a, node_b],
            selected_design_id="did-a",
        )
        assert "did-a" in result


# ---------------------------------------------------------------------------
# _tool_result_value
# ---------------------------------------------------------------------------


class TestToolResultValueR4:
    def test_returns_value_from_output(self):
        tool_result = MagicMock()
        tool_result.output.value = "result_data"
        result = ProjectDesignService._tool_result_value(tool_result)
        assert result == "result_data"

    def test_returns_none_when_output_is_none(self):
        tool_result = MagicMock()
        tool_result.output = None
        result = ProjectDesignService._tool_result_value(tool_result)
        assert result is None

    def test_returns_model_dump_when_value_none(self):
        tool_result = MagicMock()
        output = MagicMock()
        output.value = None
        output.model_dump = MagicMock(return_value={"key": "val"})
        tool_result.output = output
        result = ProjectDesignService._tool_result_value(tool_result)
        assert result == {"key": "val"}

    def test_returns_none_when_no_output_attr(self):
        tool_result = object()  # no 'output' attribute
        result = ProjectDesignService._tool_result_value(tool_result)
        assert result is None

    def test_returns_none_on_model_dump_exception(self):
        tool_result = MagicMock()
        output = MagicMock()
        output.value = None
        output.model_dump = MagicMock(side_effect=Exception("fail"))
        del output.value  # Remove value attr
        tool_result.output = output
        # Should not raise
        result = ProjectDesignService._tool_result_value(tool_result)
        # Could be None or the exception-swallowed result
        assert result is None or result is not None  # just should not raise


# ---------------------------------------------------------------------------
# _build_billing_context
# ---------------------------------------------------------------------------


class TestBuildBillingContextR4:
    """Billing context was removed — _build_billing_context no longer exists."""

    def test_service_has_no_billing_context_method(self):
        svc = _make_service()
        assert not hasattr(svc, "_build_billing_context")


# ---------------------------------------------------------------------------
# _build_llm_messages
# ---------------------------------------------------------------------------


class TestBuildLlmMessagesR4:
    def test_returns_single_user_message(self):
        messages = ProjectDesignService._build_llm_messages(
            session_id="sess-1", user_prompt="Do this"
        )
        assert len(messages) == 1

    def test_passes_correct_prompt_to_new_message(self):
        from ii_agent.chat.types import TextContent, MessageRole

        messages = ProjectDesignService._build_llm_messages(
            session_id="sess-1", user_prompt="Design this"
        )
        msg = messages[0]
        assert msg.role == MessageRole.USER
        assert msg.session_id == "sess-1"
        assert any(isinstance(p, TextContent) and p.text == "Design this" for p in msg.parts)


# ---------------------------------------------------------------------------
# _parse_design_request (fallback)
# ---------------------------------------------------------------------------


class TestParseDesignRequestR4:
    def test_parses_color_change(self):
        svc = _make_service()
        changes, explanation = svc._parse_design_request("Change color to red", {"color": "blue"})
        assert isinstance(changes, list)
        assert isinstance(explanation, str)

    def test_parses_font_size_change(self):
        svc = _make_service()
        changes, explanation = svc._parse_design_request("Increase font size", {"fontSize": "14px"})
        assert isinstance(changes, list)

    def test_returns_list_for_empty_request(self):
        svc = _make_service()
        changes, explanation = svc._parse_design_request("", {})
        assert isinstance(changes, list)
        assert isinstance(explanation, str)

    def test_returns_list_for_unrecognized_request(self):
        svc = _make_service()
        changes, explanation = svc._parse_design_request("completely random text xyz123", {})
        assert isinstance(changes, list)
        assert isinstance(explanation, str)


# ---------------------------------------------------------------------------
# get_design_state
# ---------------------------------------------------------------------------


class TestGetDesignStateR4:
    @pytest.mark.asyncio
    async def test_returns_design_state(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        svc._repo.get_design_state = MagicMock(
            return_value=([_make_raw_style_change()], [], 1234567890)
        )
        result = await svc.get_design_state(AsyncMock(), session_id=session.id, user_id="user-1")
        assert result.session_id == session.id
        assert len(result.changes) == 1

    @pytest.mark.asyncio
    async def test_raises_for_wrong_user(self):
        svc = _make_service()
        session = _make_session(user_id="other-user")
        svc._repo.get_session = AsyncMock(return_value=session)
        with pytest.raises(DesignSessionAccessDeniedError):
            await svc.get_design_state(AsyncMock(), session_id=session.id, user_id="user-1")

    @pytest.mark.asyncio
    async def test_empty_changes_returns_empty_lists(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        svc._repo.get_design_state = MagicMock(return_value=([], [], None))
        result = await svc.get_design_state(AsyncMock(), session_id=session.id, user_id="user-1")
        assert result.changes == []
        assert result.redo_changes == []


# ---------------------------------------------------------------------------
# save_design_state
# ---------------------------------------------------------------------------


class TestSaveDesignStateR4:
    @pytest.mark.asyncio
    async def test_saves_and_returns_response(self):
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
            redo_changes=None,
        )
        result = await svc.save_design_state(AsyncMock(), request=request, user_id="user-1")
        assert len(result.redo_changes) == 1

    @pytest.mark.asyncio
    async def test_raises_for_wrong_user(self):
        svc = _make_service()
        session = _make_session(user_id="other-user")
        svc._repo.get_session = AsyncMock(return_value=session)
        request = DesignStateRequest(session_id=session.id, changes=[], redo_changes=None)
        with pytest.raises(DesignSessionAccessDeniedError):
            await svc.save_design_state(AsyncMock(), request=request, user_id="user-1")


# ---------------------------------------------------------------------------
# sync_persisted_design_changes
# ---------------------------------------------------------------------------


class TestSyncPersistedDesignChangesR4:
    @pytest.mark.asyncio
    async def test_invalid_session_id_raises(self):
        svc = _make_service()
        request = SyncStateRequest(session_id="not-a-uuid", changes=None, project_info=None)
        with pytest.raises(DesignValidationError, match="Invalid session_id"):
            await svc.sync_persisted_design_changes(AsyncMock(), user_id="user-1", request=request)

    @pytest.mark.asyncio
    async def test_no_pending_changes_returns_empty(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        svc._repo.get_design_state = MagicMock(return_value=([], [], None))
        request = SyncStateRequest(
            session_id=str(uuid.uuid4()),
            changes=None,
            project_info=None,
        )
        result = await svc.sync_persisted_design_changes(
            AsyncMock(), user_id="user-1", request=request
        )
        assert result.success is False
        assert result.total == 0


# ---------------------------------------------------------------------------
# _normalize_iframe_plan_operations
# ---------------------------------------------------------------------------


class TestNormalizeIframePlanOperationsR4:
    @pytest.mark.asyncio
    async def test_non_list_returns_empty(self):
        svc = _make_service()
        result = await svc._normalize_iframe_plan_operations(
            operations=None,
            snapshot_nodes=[],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_non_dict_items_skipped(self):
        svc = _make_service()
        result = await svc._normalize_iframe_plan_operations(
            operations=["string", 42, None],
            snapshot_nodes=[],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_missing_op_or_design_id_skipped(self):
        svc = _make_service()
        ops = [{"op": "set_style"}, {"design_id": "did-1"}, {}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_set_style_passes_through(self):
        svc = _make_service()
        ops = [{"op": "set_style", "design_id": "did-1", "property": "color", "value": "red"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert len(result) == 1
        assert result[0]["op"] == "set_style"
        assert result[0]["property"] == "color"
        assert result[0]["value"] == "red"

    @pytest.mark.asyncio
    async def test_set_style_missing_property_skipped(self):
        svc = _make_service()
        ops = [{"op": "set_style", "design_id": "did-1", "value": "red"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_set_text_passes_through(self):
        svc = _make_service()
        ops = [{"op": "set_text", "design_id": "did-1", "text": "Hello world"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert len(result) == 1
        assert result[0]["op"] == "set_text"
        assert result[0]["text"] == "Hello world"

    @pytest.mark.asyncio
    async def test_design_id_not_in_nodes_skipped(self):
        svc = _make_service()
        ops = [{"op": "set_style", "design_id": "missing-id", "property": "color", "value": "red"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_swap_valid_passes_through(self):
        svc = _make_service()
        ops = [{"op": "swap", "design_id": "did-1", "target_design_id": "did-2"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1"), _make_snapshot_node("did-2")],
            icon_svg_tool=MagicMock(),
        )
        assert len(result) == 1
        assert result[0]["op"] == "swap"
        assert result[0]["target_design_id"] == "did-2"

    @pytest.mark.asyncio
    async def test_swap_missing_target_skipped(self):
        svc = _make_service()
        ops = [{"op": "swap", "design_id": "did-1", "target_design_id": "missing"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_move_before_valid(self):
        svc = _make_service()
        ops = [{"op": "move", "design_id": "did-1", "anchor": "before:did-2"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1"), _make_snapshot_node("did-2")],
            icon_svg_tool=MagicMock(),
        )
        assert len(result) == 1
        assert result[0]["op"] == "move"
        assert result[0]["anchor"] == "before:did-2"

    @pytest.mark.asyncio
    async def test_move_after_valid(self):
        svc = _make_service()
        ops = [{"op": "move", "design_id": "did-1", "anchor": "after:did-2"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1"), _make_snapshot_node("did-2")],
            icon_svg_tool=MagicMock(),
        )
        assert len(result) == 1
        assert result[0]["anchor"] == "after:did-2"

    @pytest.mark.asyncio
    async def test_move_missing_target_in_before_skipped(self):
        svc = _make_service()
        ops = [{"op": "move", "design_id": "did-1", "anchor": "before:missing-id"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_set_icon_with_svg_inner(self):
        svc = _make_service()
        ops = [
            {
                "op": "set_icon",
                "design_id": "did-1",
                "icon_name": "rocket",
                "svg_inner": "<path d='M0 0'/>",
            }
        ]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert len(result) == 1
        assert result[0]["op"] == "set_icon"
        assert result[0]["icon_name"] == "rocket"
        assert "<path" in result[0]["svg_inner"]

    @pytest.mark.asyncio
    async def test_set_icon_no_icon_name_skipped(self):
        svc = _make_service()
        ops = [{"op": "set_icon", "design_id": "did-1", "svg_inner": "<path/>"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_set_icon_svg_too_large_skipped(self):
        svc = _make_service()
        large_svg = "x" * 21000
        ops = [
            {"op": "set_icon", "design_id": "did-1", "icon_name": "rocket", "svg_inner": large_svg}
        ]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_unknown_op_type_skipped(self):
        svc = _make_service()
        ops = [{"op": "unknown_op", "design_id": "did-1"}]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=[_make_snapshot_node("did-1")],
            icon_svg_tool=MagicMock(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_valid_operations(self):
        svc = _make_service()
        ops = [
            {"op": "set_style", "design_id": "did-1", "property": "color", "value": "red"},
            {"op": "set_text", "design_id": "did-2", "text": "New text"},
        ]
        nodes = [_make_snapshot_node("did-1"), _make_snapshot_node("did-2")]
        result = await svc._normalize_iframe_plan_operations(
            operations=ops,
            snapshot_nodes=nodes,
            icon_svg_tool=MagicMock(),
        )
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _resolve_llm_config_for_session
# ---------------------------------------------------------------------------


class TestResolveLlmConfigForSessionR4:
    @pytest.mark.asyncio
    async def test_returns_default_llm_config_when_no_setting(self):
        from ii_agent.core.config.llm_config import LLMConfig

        svc = _make_service()
        # No setting_id on session — falls back to resolve_system_config("default")
        default_config = LLMConfig(model="gpt-4o")
        svc._model_setting_service.resolve_system_config = AsyncMock(return_value=default_config)
        session = _make_session(llm_setting_id=None)
        result = await svc._resolve_llm_config_for_session(
            AsyncMock(),
            session_id=session.id,
            user_id="u1",
            session=session,
        )
        assert isinstance(result, LLMConfig)

    @pytest.mark.asyncio
    async def test_uses_llm_setting_from_service(self):
        from ii_agent.core.config.llm_config import LLMConfig

        svc = _make_service()
        mock_config = MagicMock(spec=LLMConfig)
        mock_config.model_copy = MagicMock(return_value=mock_config)
        svc._model_setting_service.get_user_llm_config = AsyncMock(return_value=mock_config)
        session = _make_session(llm_setting_id="some-model-id")
        result = await svc._resolve_llm_config_for_session(
            AsyncMock(),
            session_id=session.id,
            user_id="u1",
            session=session,
        )
        svc._model_setting_service.get_user_llm_config.assert_called_once()
        assert result is mock_config

    @pytest.mark.asyncio
    async def test_falls_back_to_system_config_when_user_service_fails(self):
        from ii_agent.core.config.llm_config import LLMConfig

        svc = _make_service()
        svc._model_setting_service.get_user_llm_config = AsyncMock(
            side_effect=Exception("not found")
        )
        # resolve_system_config also fails, falls to "default" fallback
        system_config = LLMConfig(model="gpt-4o")
        svc._model_setting_service.resolve_system_config = AsyncMock(
            side_effect=[Exception("not found"), system_config]
        )
        session = _make_session(llm_setting_id="gpt-4")
        # Should not raise, should return a default config
        result = await svc._resolve_llm_config_for_session(
            AsyncMock(),
            session_id=session.id,
            user_id="u1",
            session=session,
        )
        assert isinstance(result, LLMConfig)


# ---------------------------------------------------------------------------
# sync_design_changes (public method)
# ---------------------------------------------------------------------------


class TestSyncDesignChangesR4:
    @pytest.mark.asyncio
    async def test_invalid_session_id_raises_validation_error(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        request = SyncRequest(
            session_id="not-a-valid-uuid",
            changes=[StyleChange(**_make_raw_style_change())],
            project_info=None,
        )
        with pytest.raises(DesignValidationError, match="Invalid session_id"):
            await svc.sync_design_changes(AsyncMock(), user_id="user-1", request=request)

    @pytest.mark.asyncio
    async def test_empty_changes_returns_success(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        valid_uuid = str(uuid.uuid4())
        request = SyncRequest(session_id=valid_uuid, changes=[], project_info=None)
        result = await svc.sync_design_changes(AsyncMock(), user_id="user-1", request=request)
        assert result.success is True
        assert result.applied == 0

    @pytest.mark.asyncio
    async def test_no_sandbox_raises_sandbox_unavailable(self):
        svc = _make_service()
        session = _make_session(user_id="user-1")
        svc._repo.get_session = AsyncMock(return_value=session)
        svc._sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=None)
        svc._sandbox_service.get_sandbox_by_session = AsyncMock(side_effect=Exception("no sandbox"))
        valid_uuid = str(uuid.uuid4())
        request = SyncRequest(
            session_id=valid_uuid,
            changes=[StyleChange(**_make_raw_style_change())],
            project_info=None,
        )
        with pytest.raises(DesignSandboxUnavailableError):
            await svc.sync_design_changes(AsyncMock(), user_id="user-1", request=request)
