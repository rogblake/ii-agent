from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.projects.design.exceptions import (
    DesignProxyFetchError,
    DesignValidationError,
)
from ii_agent.projects.design.schemas import ElementContext, StyleChange
from ii_agent.projects.design.service import ProjectDesignService


def _make_service(settings_factory) -> ProjectDesignService:
    return ProjectDesignService(
        repo=SimpleNamespace(),
        sandbox_service=SimpleNamespace(),
        event_service=SimpleNamespace(),
        llm_setting_service=SimpleNamespace(),
        llm_execution_service=SimpleNamespace(),
        llm_billing_service=None,
        config=settings_factory(),
    )


def _style_change(
    *,
    design_id: str = "d1",
    change_type: str = "style",
    prop: str = "color",
    to_value: str = "red",
    ts: int = 1000,
    ctx: ElementContext | None = None,
) -> StyleChange:
    return StyleChange(
        designId=design_id,
        type=change_type,
        property=prop,
        value={"to": to_value},
        timestamp=ts,
        elementContext=ctx,
    )


class _FakeSandbox:
    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files = dict(files or {})
        self.writes: list[tuple[str, str]] = []

    async def read_file(self, file_path: str):
        if file_path not in self.files:
            raise FileNotFoundError(file_path)
        return self.files[file_path]

    async def write_file(self, file_path: str, content: str):
        self.files[file_path] = content
        self.writes.append((file_path, content))


def test_parse_design_request_color_and_size():
    changes, explanation = ProjectDesignService._parse_design_request(
        "make the text blue and bigger",
        {"fontSize": "16px"},
    )

    assert {"property": "color", "value": "#3b82f6"} in changes
    assert {"property": "font-size", "value": "20px"} in changes
    assert explanation


def test_parse_design_request_unknown_prompt():
    changes, explanation = ProjectDesignService._parse_design_request(
        "do something magical",
        {},
    )

    assert changes == []
    assert "Try being more specific" in explanation


def test_parse_search_lines_sorts_and_filters_noise():
    lines = (
        "/workspace/src/B.tsx:30:match\n"
        "noise\n"
        "/workspace/src/A.tsx:12:match\n"
        "/workspace/src/aaa/longer.tsx:3:match\n"
    )
    parsed = ProjectDesignService._parse_search_lines(lines)

    assert parsed == [
        ("/workspace/src/A.tsx", 12),
        ("/workspace/src/B.tsx", 30),
        ("/workspace/src/aaa/longer.tsx", 3),
    ]


@pytest.mark.asyncio
async def test_apply_replace_modifications_success(settings_factory):
    service = _make_service(settings_factory)
    sandbox = _FakeSandbox({"/workspace/src/App.tsx": "const x = 1;\n"})

    ok, reason = await service._apply_replace_modifications(
        sandbox=sandbox,
        file_path="/workspace/src/App.tsx",
        modifications=[{"type": "replace", "old": "1", "new": "2"}],
    )

    assert ok is True
    assert reason == ""
    assert sandbox.files["/workspace/src/App.tsx"] == "const x = 2;\n"


@pytest.mark.asyncio
async def test_apply_replace_modifications_rejects_invalid_entries(settings_factory):
    service = _make_service(settings_factory)
    sandbox = _FakeSandbox({"/workspace/src/App.tsx": "const x = 1;\n"})

    ok, reason = await service._apply_replace_modifications(
        sandbox=sandbox,
        file_path="/workspace/src/App.tsx",
        modifications=[{"type": "insert", "old": "1", "new": "2"}],
    )
    assert ok is False
    assert "Only replace modifications are supported." in reason

    ok, reason = await service._apply_replace_modifications(
        sandbox=sandbox,
        file_path="/workspace/src/App.tsx",
        modifications=[{"type": "replace", "old": "", "new": "2"}],
    )
    assert ok is False
    assert "replace old cannot be empty." in reason


@pytest.mark.asyncio
async def test_apply_sync_plan_reports_missing_and_invalid_entries(settings_factory, monkeypatch):
    service = _make_service(settings_factory)
    changes = [_style_change(design_id="a"), _style_change(design_id="b")]
    sandbox = _FakeSandbox()

    async def _ok_apply(**kwargs):
        return True, ""

    monkeypatch.setattr(service, "_apply_replace_modifications", _ok_apply)

    applied, errors, failed = await service._apply_sync_plan(
        sandbox=sandbox,
        changes=changes,
        plan_entries=[
            {"change_index": 1, "file_path": "/tmp/outside.tsx", "modifications": [{"type": "replace"}]}
        ],
    )

    assert applied == 0
    assert failed == {0, 1}
    assert any("Invalid file_path" in err for err in errors)
    assert any("Missing plan entry" in err for err in errors)


def test_resolve_failed_sync_indexes_uses_fingerprint_fallback(settings_factory):
    service = _make_service(settings_factory)
    change_a = _style_change(design_id="a", to_value="red")
    change_b = _style_change(design_id="b", to_value="blue")
    cloned_b = StyleChange.model_validate(change_b.model_dump())

    failed = service._resolve_failed_sync_indexes(
        changes=[change_a, change_b],
        remaining_changes=[cloned_b],
    )
    assert failed == {1}


@pytest.mark.asyncio
async def test_normalize_iframe_plan_operations_filters_and_enriches_icon(settings_factory, monkeypatch):
    service = _make_service(settings_factory)
    nodes = [
        SimpleNamespace(designId="hero", tagName="h1", className="", id=None, textContent="Hello", attributes={}, parentDesignId=None, childDesignIds=[], html="<h1>Hello</h1>"),
        SimpleNamespace(designId="icon", tagName="svg", className="", id=None, textContent="", attributes={}, parentDesignId=None, childDesignIds=[], html="<svg></svg>"),
    ]
    icon_tool = SimpleNamespace(name="icon_getter")

    async def _execute_tool(**kwargs):
        output = SimpleNamespace(value={"svg_inner": "<path d='M1 1' />"})
        return SimpleNamespace(output=output)

    monkeypatch.setattr(
        "ii_agent.projects.design.service.ChatToolService.execute_tool",
        _execute_tool,
    )

    normalized = await service._normalize_iframe_plan_operations(
        operations=[
            {"op": "set_style", "design_id": "hero", "property": "color", "value": "red"},
            {"op": "set_text", "design_id": "hero", "text": "Updated"},
            {"op": "set_icon", "design_id": "icon", "icon_name": "bell"},
            {"op": "move", "design_id": "hero", "anchor": "before:icon"},
            {"op": "swap", "design_id": "hero", "target_design_id": "icon"},
            {"op": "set_style", "design_id": "missing", "property": "color", "value": "red"},
            {"op": "move", "design_id": "hero", "anchor": "before:missing"},
        ],
        snapshot_nodes=nodes,
        icon_svg_tool=icon_tool,
    )

    assert normalized == [
        {"op": "set_style", "design_id": "hero", "property": "color", "value": "red"},
        {"op": "set_text", "design_id": "hero", "text": "Updated"},
        {"op": "set_icon", "design_id": "icon", "icon_name": "bell", "svg_inner": "<path d='M1 1' />"},
        {"op": "move", "design_id": "hero", "anchor": "before:icon"},
        {"op": "swap", "design_id": "hero", "target_design_id": "icon"},
    ]


def test_extract_source_search_queries_includes_context_fields(settings_factory):
    service = _make_service(settings_factory)
    ctx = ElementContext(
        designId="ctx-id",
        tagName="button",
        className="btn primary",
        textContent="Save",
        contextText="Context",
        prevSiblingText="Back",
        nextSiblingText="Next",
        attributes={"aria-label": "Save Story", "title": "Save"},
    )
    change = _style_change(design_id="d1", to_value="new", ctx=ctx)
    queries = service._extract_source_search_queries(change)

    assert "d1" in queries
    assert "ctx-id" in queries
    assert "Save Story" in queries
    assert "new" in queries


def test_build_sync_changes_text_embeds_hints(settings_factory):
    service = _make_service(settings_factory)
    change = _style_change(
        design_id="d1",
        change_type="text",
        prop="textContent",
        to_value="new text",
        ctx=ElementContext(designId="d1", tagName="p", textContent="old"),
    )
    text = service._build_sync_changes_text(
        [change],
        source_hints={1: "- candidate_file: /workspace/src/App.tsx\n- match_line: 12"},
    )

    assert "Change 1:" in text
    assert "candidate_file" in text
    assert "new text" in text


def test_sync_change_fingerprint_accepts_dict_and_model():
    change = _style_change(design_id="d1")
    fp_model = ProjectDesignService._sync_change_fingerprint(change)
    fp_dict = ProjectDesignService._sync_change_fingerprint(change.model_dump())

    assert json.loads(fp_model)["designId"] == "d1"
    assert json.loads(fp_dict)["designId"] == "d1"


def test_validate_proxy_url_and_allowlist_helpers(settings_factory):
    service = _make_service(settings_factory)

    parsed = service._validate_proxy_url("https://123-provider.e2b.app/page")
    assert parsed.hostname == "123-provider.e2b.app"

    with pytest.raises(DesignValidationError):
        service._validate_proxy_url("ftp://bad")
    with pytest.raises(DesignValidationError):
        service._validate_proxy_url("https://user:pass@example.com")
    with pytest.raises(DesignValidationError):
        service._validate_proxy_url("   ")

    checker = service._build_proxy_hostname_allow_check(
        session_public_url="https://public.example.com",
        session_sandbox_id="sandbox-123",
        requested_hostname="3000-provider-id.e2b.app",
        sandbox_record=SimpleNamespace(provider_sandbox_id="provider-id"),
    )
    assert checker("public.example.com") is True
    assert checker("3000-provider-id.e2b.app") is True
    assert checker("3000-provider-id.e2b.dev") is True
    assert checker("evil.example.com") is False


def test_rewrite_urls_and_runtime_injection(settings_factory):
    service = _make_service(settings_factory)
    html = (
        "<html><head></head><body>"
        '<img src="/img.png" srcset="/a.png 1x, /b.png 2x">'
        '<a href="/docs">Docs</a></body></html>'
    )
    injected = service._inject_runtime_script_with_base(
        html=html,
        base_url="https://sandbox.e2b.app/path/page.html",
    )

    assert "__DESIGN_MODE_RUNTIME__" in injected
    assert 'src="https://sandbox.e2b.app/img.png"' in injected
    assert "https://sandbox.e2b.app/a.png 1x" in injected
    assert '<base href="https://sandbox.e2b.app/path/">' in injected


@pytest.mark.asyncio
async def test_fetch_proxy_html_redirect_and_error_paths(settings_factory, monkeypatch):
    service = _make_service(settings_factory)

    class _Response:
        def __init__(self, status_code=200, headers=None, text="ok"):
            self.status_code = status_code
            self.headers = headers or {"content-type": "text/html"}
            self.text = text

        def raise_for_status(self):
            if self.status_code >= 400:
                import httpx

                request = httpx.Request("GET", "https://x")
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError("bad", request=request, response=response)

    class _Client:
        def __init__(self, responses):
            self._responses = list(responses)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers):
            return self._responses.pop(0)

    monkeypatch.setattr(
        "ii_agent.projects.design.service.httpx.AsyncClient",
        lambda **kwargs: _Client(
            [
                _Response(status_code=302, headers={"location": "/next"}),
                _Response(status_code=200, headers={"content-type": "text/html"}, text="<html>ok</html>"),
            ]
        ),
    )
    html, final_url = await service._fetch_proxy_html(
        url="https://host.e2b.app/start",
        is_hostname_allowed=lambda hn: True,
    )
    assert html == "<html>ok</html>"
    assert final_url.endswith("/next")

    monkeypatch.setattr(
        "ii_agent.projects.design.service.httpx.AsyncClient",
        lambda **kwargs: _Client([_Response(status_code=200, headers={"content-type": "application/json"})]),
    )
    with pytest.raises(DesignProxyFetchError):
        await service._fetch_proxy_html(
            url="https://host.e2b.app/start",
            is_hostname_allowed=lambda hn: True,
        )


@pytest.mark.asyncio
async def test_sync_design_changes_internal_success_and_deterministic_failure(settings_factory, monkeypatch):
    session = SimpleNamespace(user_id="user-1")
    repo = SimpleNamespace(get_session=AsyncMock(return_value=session))
    sandbox_service = SimpleNamespace(
        get_sandbox_by_session_id=AsyncMock(return_value=SimpleNamespace()),
        get_sandbox_by_session=AsyncMock(),
    )
    event_service = SimpleNamespace(save_event=AsyncMock(), emit_event=AsyncMock())
    service = ProjectDesignService(
        repo=repo,
        sandbox_service=sandbox_service,
        event_service=event_service,
        llm_setting_service=SimpleNamespace(),
        llm_execution_service=SimpleNamespace(),
        llm_billing_service=None,
        config=settings_factory(),
    )

    changes = [_style_change(design_id="d1")]

    async def _ok_apply(**kwargs):
        return 1, [], []

    monkeypatch.setattr(
        "ii_agent.projects.design.service.apply_changes_with_source_mapping",
        _ok_apply,
    )
    response, failed = await service._sync_design_changes_internal(
        db=None,
        user_id="user-1",
        request=SimpleNamespace(session_id="00000000-0000-0000-0000-000000000001", changes=changes),
    )
    assert response.success is True
    assert response.applied == 1
    assert failed == set()

    async def _boom_apply(**kwargs):
        raise RuntimeError("sync failure")

    monkeypatch.setattr(
        "ii_agent.projects.design.service.apply_changes_with_source_mapping",
        _boom_apply,
    )
    failed_response, failed_indexes = await service._sync_design_changes_internal(
        db=None,
        user_id="user-1",
        request=SimpleNamespace(session_id="00000000-0000-0000-0000-000000000001", changes=changes),
    )
    assert failed_response.success is False
    assert failed_response.applied == 0
    assert failed_indexes == {0}
