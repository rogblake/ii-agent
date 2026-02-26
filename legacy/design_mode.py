"""
Design Mode API endpoints.

Provides:
- Proxy endpoint to fetch sandbox HTML and inject design mode runtime
- Sync endpoint to apply design changes to source files
"""

import json
import logging
import bisect
import posixpath
import re
import shlex
import time
import uuid
from typing import List, Optional, Dict, Any, Callable
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.config.ii_agent_config import config
from ii_agent.db.manager import Events, Sessions, get_db_session_local
from ii_agent.metrics.models import TokenUsage
from ii_agent.server.api.deps import CurrentUser
from ii_agent.server.credits.service import calculate_user_credits
from ii_agent.server.shared import sandbox_service, agent_service
from ii_agent.server.llm_settings.service import (
    get_system_llm_config,
    get_user_llm_config,
)
from ii_agent.llm import get_client
from ii_agent.llm.base import (
    TextPrompt,
    TextResult,
    ToolCall,
    ToolFormattedResult,
)
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.server.api.icon_catalogs import lucide as lucide_icon_catalog
from ii_agent.prompts.design_mode_prompts import (
    build_design_mode_batch_sync_prompt,
    build_design_mode_iframe_plan_prompt,
    build_design_mode_single_sync_prompt,
    build_design_mode_style_change_prompt,
)
from ii_agent.tools.design_mode_tool_params import (
    DESIGN_MODE_AI_CHANGE_TOOL,
    DESIGN_MODE_AI_CHANGE_TOOL_NAME,
    DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL,
    DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL_NAME,
    DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL,
    DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL_NAME,
    DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL,
    DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL_NAME,
    DESIGN_MODE_IFRAME_AI_PLAN_TOOL,
    DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME,
    DESIGN_MODE_IFRAME_AI_SEARCH_TOOL,
    DESIGN_MODE_IFRAME_AI_SEARCH_TOOL_NAME,
    DESIGN_MODE_SYNC_PLAN_TOOL,
    DESIGN_MODE_SYNC_PLAN_TOOL_NAME,
)
from ii_agent.v1.db.sandbox import Sandbox

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/design-mode", tags=["Design Mode"])
# The design mode runtime script that gets injected into the iframe
DESIGN_MODE_RUNTIME_SCRIPT = """
"""


_E2B_ALLOWED_HOST_SUFFIXES = (".e2b.app", ".e2b.dev")


def _is_e2b_hostname(hostname: str) -> bool:
    if not isinstance(hostname, str):
        return False
    value = hostname.strip().lower().rstrip(".")
    if not value:
        return False
    return value.endswith(_E2B_ALLOWED_HOST_SUFFIXES)


def _extract_e2b_port_from_hostname(hostname: str) -> Optional[int]:
    """
    Best-effort parse of E2B "port-prefixed" hostnames like:
      3000-<provider_id>.e2b.app
      6060-<provider_id>.e2b.dev
    Returns the port number when present, else None.
    """
    if not isinstance(hostname, str):
        return None
    hn = hostname.strip().lower().rstrip(".")
    if not hn or not _is_e2b_hostname(hn):
        return None
    label = hn.split(".", 1)[0]
    if not label:
        return None
    first = label.split("-", 1)[0]
    if not first.isdigit():
        return None
    try:
        port = int(first)
    except Exception:
        return None
    if port < 1 or port > 65535:
        return None
    return port


def _hostname_matches_sandbox_id(hostname: str, sandbox_id: str) -> bool:
    if not isinstance(hostname, str) or not isinstance(sandbox_id, str):
        return False
    hn = hostname.strip().lower().rstrip(".")
    sid = sandbox_id.strip().lower()
    if not hn or not sid:
        return False
    if not _is_e2b_hostname(hn):
        return False

    label = hn.split(".", 1)[0]
    if label == sid:
        return True
    if label.endswith(f"-{sid}") or label.startswith(f"{sid}-") or f"-{sid}-" in label:
        return True
    parts = [p for p in label.split("-") if p]
    return sid in parts


async def _resolve_provider_sandbox_id_for_session_sandbox_id(
    session_sandbox_id: str,
) -> Optional[str]:
    """Resolve provider_sandbox_id from session_sandbox_id using V1 sandbox database.

    The session_sandbox_id can be either:
    1. A sandbox record ID (UUID) from the sandboxes table
    2. A session_id that can be used to look up the sandbox
    """
    if not isinstance(session_sandbox_id, str):
        return None
    session_sandbox_id = session_sandbox_id.strip()
    if not session_sandbox_id:
        return None

    try:
        async with get_db_session_local() as db_session:
            # First try to get sandbox by ID (if session_sandbox_id is a sandbox record ID)
            sandbox_record = None
            try:
                sandbox_record = await Sandbox.get_by_id(db_session, session_sandbox_id)
            except (ValueError, Exception):
                # Not a valid UUID, try by session_id
                pass

            # If not found by ID, try by session_id
            if not sandbox_record:
                sandbox_record = await Sandbox.get_by_session_id(
                    db_session, session_sandbox_id
                )

            if not sandbox_record:
                return None

            provider_sandbox_id = sandbox_record.provider_sandbox_id
            if not isinstance(provider_sandbox_id, str):
                return None
            provider_sandbox_id = provider_sandbox_id.strip()
            return provider_sandbox_id or None
    except Exception as exc:
        logger.warning(
            "[DesignMode Proxy] Failed to resolve provider_sandbox_id for session sandbox_id=%s: %s",
            session_sandbox_id,
            exc,
        )
        return None


async def _resolve_exposed_hostname_for_session_sandbox_port(
    session_sandbox_id: str, port: int
) -> Optional[str]:
    """Resolve exposed hostname for a sandbox port using V1 sandbox database.

    Uses E2B's hostname format: {port}-{provider_sandbox_id}.e2b.app
    """
    if not isinstance(session_sandbox_id, str):
        return None
    session_sandbox_id = session_sandbox_id.strip()
    if not session_sandbox_id:
        return None
    try:
        port = int(port)
    except Exception:
        return None
    if port < 1 or port > 65535:
        return None

    try:
        async with get_db_session_local() as db_session:
            # First try to get sandbox by ID (if session_sandbox_id is a sandbox record ID)
            sandbox_record = None
            try:
                sandbox_record = await Sandbox.get_by_id(db_session, session_sandbox_id)
            except (ValueError, Exception):
                # Not a valid UUID, try by session_id
                pass

            # If not found by ID, try by session_id
            if not sandbox_record:
                sandbox_record = await Sandbox.get_by_session_id(
                    db_session, session_sandbox_id
                )

            if not sandbox_record or not sandbox_record.provider_sandbox_id:
                return None

            provider_sandbox_id = sandbox_record.provider_sandbox_id.strip()
            if not provider_sandbox_id:
                return None

            # Construct E2B hostname format: {port}-{provider_sandbox_id}.e2b.app
            hostname = f"{port}-{provider_sandbox_id}.e2b.app"
            return hostname.lower()
    except Exception as exc:
        logger.warning(
            "[DesignMode Proxy] Failed to resolve exposed hostname for sandbox_id=%s port=%s: %s",
            session_sandbox_id,
            port,
            exc,
        )
        return None


class _V1SandboxWrapper:
    """Wrapper to make V1 E2BSandboxManager compatible with design mode operations.

    The design mode code expects methods like `run_cmd`, but V1 uses `run_command`.
    This wrapper provides compatibility.
    """

    def __init__(self, sandbox_manager):
        self._sandbox_manager = sandbox_manager

    async def run_cmd(self, cmd: str) -> str:
        """Run a command in the sandbox (compatibility wrapper for run_command)."""
        return await self._sandbox_manager.run_command(cmd)

    async def read_file(self, file_path: str) -> str:
        """Read a file from the sandbox."""
        return await self._sandbox_manager.read_file(file_path)

    async def write_file(self, content: str, file_path: str) -> bool:
        """Write a file to the sandbox.

        Note: Design mode code calls write_file(content, path) but E2BSandboxManager
        expects write_file(path, content), so we swap the parameters here.
        """
        await self._sandbox_manager.write_file(file_path, content)
        return True

    async def upload_file(self, content: str, file_path: str) -> bool:
        """Upload a file to the sandbox (compatibility wrapper for write_file)."""
        await self._sandbox_manager.write_file(file_path, content)
        return True

    async def download_file(self, file_path: str, format: str = "text"):
        """Download a file from the sandbox."""
        return await self._sandbox_manager.read_file(file_path)


async def _get_v1_sandbox_for_session(session_id: uuid.UUID):
    """Get the V1 E2BSandboxManager for a session.

    This resolves the sandbox from the V1 sandboxes database table and returns
    a wrapped E2BSandboxManager instance that can be used for file operations.

    Args:
        session_id: The session UUID.

    Returns:
        _V1SandboxWrapper instance with compatibility methods.

    Raises:
        HTTPException: If sandbox not found or connection fails.
    """
    from ii_agent.v1.sandboxes.e2b import E2BSandboxManager

    try:
        async with get_db_session_local() as db_session:
            # Look up sandbox by session_id
            sandbox_record = await Sandbox.get_by_session_id(
                db_session, str(session_id)
            )

            if not sandbox_record:
                raise HTTPException(
                    status_code=404, detail=f"No sandbox found for session {session_id}"
                )

            if not sandbox_record.provider_sandbox_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Sandbox {sandbox_record.id} has no provider_sandbox_id",
                )

            # Create E2BSandboxManager from the sandbox record
            sandbox_manager = await E2BSandboxManager.from_sandbox_record(
                sandbox_record
            )
            if not sandbox_manager:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to connect to sandbox {sandbox_record.provider_sandbox_id}",
                )

            # Return wrapped sandbox with compatibility methods
            return _V1SandboxWrapper(sandbox_manager)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "[DesignMode] Failed to get V1 sandbox for session %s: %s",
            session_id,
            exc,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get sandbox: {exc}"
        ) from exc


def _validate_design_mode_proxy_url(
    *, url: str, is_hostname_allowed: Callable[[str], bool]
) -> str:
    if not isinstance(url, str):
        raise HTTPException(status_code=400, detail="Invalid URL")
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        requested = urlparse(url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL")

    if requested.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Invalid URL scheme")
    if not requested.netloc or not requested.hostname:
        raise HTTPException(status_code=400, detail="Invalid URL")
    if requested.username or requested.password:
        raise HTTPException(status_code=400, detail="Invalid URL")

    requested_hostname = (requested.hostname or "").lower()
    if not is_hostname_allowed(requested_hostname):
        raise HTTPException(status_code=403, detail="Proxy URL host not allowed")

    return url


async def _fetch_design_mode_proxy_html(
    *, url: str, is_hostname_allowed: Callable[[str], bool]
) -> tuple[str, str]:
    max_redirects = 5
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            current_url = url
            for _ in range(max_redirects + 1):
                response = await client.get(
                    current_url,
                    headers={"Accept": "text/html,application/xhtml+xml"},
                )

                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise HTTPException(
                            status_code=502,
                            detail="Failed to fetch sandbox content (invalid redirect)",
                        )
                    next_url = urljoin(current_url, location)
                    parsed_next = urlparse(next_url)
                    if (
                        parsed_next.scheme not in {"http", "https"}
                        or not parsed_next.netloc
                        or not parsed_next.hostname
                    ):
                        raise HTTPException(
                            status_code=502,
                            detail="Failed to fetch sandbox content (invalid redirect)",
                        )
                    if not is_hostname_allowed((parsed_next.hostname or "").lower()):
                        raise HTTPException(
                            status_code=502,
                            detail="Failed to fetch sandbox content (redirect not allowed)",
                        )
                    current_url = next_url
                    continue

                response.raise_for_status()

                content_type = (response.headers.get("content-type") or "").lower()
                if (
                    "text/html" not in content_type
                    and "application/xhtml+xml" not in content_type
                ):
                    raise HTTPException(
                        status_code=502,
                        detail="Failed to fetch sandbox content (expected HTML)",
                    )

                return response.text, current_url

            raise HTTPException(
                status_code=502,
                detail="Failed to fetch sandbox content (too many redirects)",
            )
    except httpx.HTTPStatusError as e:
        logger.error("Failed to fetch sandbox URL: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch sandbox content: {e.response.status_code}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching sandbox URL: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch sandbox content")


@router.get("/proxy", response_class=HTMLResponse)
async def proxy_design_mode(
    current_user: CurrentUser,
    session_id: str = Query(..., description="Session ID"),
    url: str = Query(..., description="Sandbox URL to proxy"),
) -> HTMLResponse:
    """
    Proxy endpoint that fetches HTML from sandbox and injects design mode runtime.

    This endpoint:
    1. Validates the user owns the session
    2. Fetches HTML from the sandbox URL
    3. Injects the design mode runtime script into <head>
    4. Rewrites relative URLs to absolute sandbox URLs
    5. Returns the modified HTML
    """
    # Validate session ownership
    session = await Sessions.get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if str(session.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    session_public_url = (
        session.public_url.strip() if isinstance(session.public_url, str) else ""
    )
    allowed_public_hostname = ""
    if session_public_url:
        try:
            allowed_public_hostname = (
                urlparse(session_public_url).hostname or ""
            ).lower()
        except Exception:
            allowed_public_hostname = ""

    session_sandbox_id = (
        session.sandbox_id.strip() if isinstance(session.sandbox_id, str) else ""
    )
    provider_sandbox_id = (
        await _resolve_provider_sandbox_id_for_session_sandbox_id(session_sandbox_id)
        if session_sandbox_id
        else None
    )

    requested_hostname = ""
    requested_port_hint: Optional[int] = None
    try:
        requested_hostname = (urlparse(url).hostname or "").lower()
        requested_port_hint = _extract_e2b_port_from_hostname(requested_hostname)
    except Exception:
        requested_port_hint = None

    expected_exposed_hostname: Optional[str] = None
    if session_sandbox_id and requested_port_hint:
        expected_exposed_hostname = (
            await _resolve_exposed_hostname_for_session_sandbox_port(
                session_sandbox_id, requested_port_hint
            )
        )

    def is_hostname_allowed(hostname: str) -> bool:
        if not hostname:
            return False
        hn = hostname.strip().lower().rstrip(".")
        if not hn:
            return False

        if expected_exposed_hostname and hn == expected_exposed_hostname:
            return True

        for sandbox_id in (
            provider_sandbox_id,
            session_sandbox_id,
        ):
            if sandbox_id and _hostname_matches_sandbox_id(hn, sandbox_id):
                return True

        return bool(allowed_public_hostname and hn == allowed_public_hostname)

    validated_url = _validate_design_mode_proxy_url(
        url=url, is_hostname_allowed=is_hostname_allowed
    )

    html, final_url = await _fetch_design_mode_proxy_html(
        url=validated_url, is_hostname_allowed=is_hostname_allowed
    )

    # Inject design mode runtime into <head>
    modified_html = inject_runtime_script(html, final_url)

    return HTMLResponse(
        content=modified_html,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-popups",
        },
    )


def inject_runtime_script(html: str, base_url: str) -> str:
    """
    Inject the design mode runtime script into the HTML.
    Also rewrites relative URLs to absolute URLs.
    """
    # Rewrite relative URLs to absolute
    html = rewrite_urls(html, base_url)

    # Inject runtime script into <head>
    if "<head>" in html:
        html = html.replace("<head>", f"<head>\n{DESIGN_MODE_RUNTIME_SCRIPT}\n", 1)
    elif "<head " in html:
        # Handle <head> with attributes
        html = re.sub(
            r"(<head[^>]*>)", rf"\1\n{DESIGN_MODE_RUNTIME_SCRIPT}\n", html, count=1
        )
    elif "<html>" in html or "<html " in html:
        # No <head>, inject after <html>
        html = re.sub(
            r"(<html[^>]*>)",
            rf"\1\n<head>\n{DESIGN_MODE_RUNTIME_SCRIPT}\n</head>\n",
            html,
            count=1,
        )
    else:
        # No <html>, prepend
        html = f"{DESIGN_MODE_RUNTIME_SCRIPT}\n{html}"

    return html


def rewrite_urls(html: str, base_url: str) -> str:
    """
    Rewrite relative URLs in HTML to absolute URLs.
    Handles src, href, and srcset attributes.
    """
    parsed_base = urlparse(base_url)
    origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
    base_href = urljoin(base_url, ".")
    if base_href and not base_href.endswith("/"):
        base_href += "/"

    # Rewrite src attributes
    html = re.sub(
        r'(src=["\'])(/[^"\']*)',
        lambda m: f"{m.group(1)}{urljoin(origin, m.group(2))}",
        html,
    )

    # Rewrite href attributes (but not anchors or javascript:)
    html = re.sub(
        r'(href=["\'])(/[^"\'#][^"\']*)',
        lambda m: f"{m.group(1)}{urljoin(origin, m.group(2))}",
        html,
    )

    def _rewrite_srcset(value: str) -> str:
        if not value:
            return value
        rewritten: list[str] = []
        for part in value.split(","):
            item = part.strip()
            if not item:
                continue
            pieces = item.split()
            if not pieces:
                continue
            url_part = pieces[0]
            if url_part.startswith("/"):
                url_part = urljoin(origin, url_part)
            rewritten.append(" ".join([url_part, *pieces[1:]]).strip())
        return ", ".join(rewritten)

    html = re.sub(
        r'(srcset=["\'])([^"\']*)(["\'])',
        lambda m: f"{m.group(1)}{_rewrite_srcset(m.group(2))}{m.group(3)}",
        html,
    )

    # Add base tag if not present
    if "<base" not in html.lower():
        if "<head>" in html:
            html = html.replace("<head>", f'<head>\n<base href="{base_href}">\n', 1)
        elif "<head " in html:
            html = re.sub(
                r"(<head[^>]*>)", rf'\1\n<base href="{base_href}">\n', html, count=1
            )

    return html


# ==========================================
# AI Change Endpoint (Phase 5)
# ==========================================


class ElementInfoRequest(BaseModel):
    """Element information for AI change request."""

    designId: str
    tagName: str
    className: Optional[str] = None
    textContent: Optional[str] = None
    computedStyles: Optional[dict] = None
    xpath: Optional[str] = None


class AIChangeRequest(BaseModel):
    """Request body for AI-assisted design change."""

    session_id: str
    element_info: ElementInfoRequest
    user_request: str


class AIChangeResponse(BaseModel):
    """Response from AI change endpoint."""

    changes: List[dict]  # [{ property: string, value: string }]
    explanation: str


class IframeDocumentSnapshotNode(BaseModel):
    designId: str
    tagName: Optional[str] = None
    className: Optional[str] = None
    id: Optional[str] = None
    textContent: Optional[str] = None
    attributes: Optional[Dict[str, str]] = None
    parentDesignId: Optional[str] = None
    childDesignIds: Optional[List[str]] = None
    html: Optional[str] = None


class IframeDocumentSnapshot(BaseModel):
    version: int = 1
    generatedAt: Optional[int] = None
    url: Optional[str] = None
    title: Optional[str] = None
    nodes: List[IframeDocumentSnapshotNode]


class IframeAIPlanRequest(BaseModel):
    """Request body for AI edits that operate on the Design Mode iframe copy."""

    session_id: str
    user_request: str
    selected_element: Optional[ElementInfoRequest] = None
    document_snapshot: IframeDocumentSnapshot


class IframeAIPlanResponse(BaseModel):
    """Response containing an ordered plan of DOM edits to apply in the iframe."""

    operations: List[dict]
    explanation: str


@router.post("/ai-change", response_model=AIChangeResponse)
async def ai_design_change(
    current_user: CurrentUser,
    request: AIChangeRequest,
) -> AIChangeResponse:
    """
    Get AI-suggested design changes for an element.

    This endpoint:
    1. Validates session ownership
    2. Sends element info and user request to a fast LLM
    3. Returns suggested CSS changes
    """
    # Validate session ownership
    session = await Sessions.get_session_by_id(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if str(session.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    prompt = build_design_mode_style_change_prompt(
        tag_name=request.element_info.tagName,
        class_name=request.element_info.className or "",
        computed_styles=request.element_info.computedStyles or {},
        text_content=request.element_info.textContent or "",
        user_request=request.user_request,
    )

    try:
        llm_config = await _get_llm_config_for_session(session)
        llm_config.temperature = 0.2
        client = get_client(llm_config)

        # Best-effort: encourage tool calling, but keep JSON parsing fallback.
        prompt_with_tool = (
            prompt
            + f"\n\nCall the tool `{DESIGN_MODE_AI_CHANGE_TOOL_NAME}` EXACTLY ONCE."
        )

        logger.info(
            "[DesignMode AI Change] Using model=%s api_type=%s",
            llm_config.model,
            llm_config.api_type,
        )
        logger.info(
            "[DesignMode AI Change] Prompt:\n%s",
            _truncate_for_log(prompt_with_tool),
        )

        assistant_blocks, _raw_metrics = await client.agenerate(
            messages=[[TextPrompt(text=prompt_with_tool)]],
            max_tokens=768,
            system_prompt="",
            temperature=0.2,
            tools=[DESIGN_MODE_AI_CHANGE_TOOL],
            tool_choice={"type": "any"},
        )

        await _track_llm_usage_and_charge(
            session_id=request.session_id,
            model_name=llm_config.model,
            raw_metrics=_raw_metrics,
        )

        tool_calls = [
            block
            for block in assistant_blocks
            if isinstance(block, ToolCall)
            and block.tool_name == DESIGN_MODE_AI_CHANGE_TOOL_NAME
        ]

        if tool_calls:
            tool_payload = tool_calls[0].tool_input
            logger.info(
                "[DesignMode AI Change] Tool payload (%s):\n%s",
                DESIGN_MODE_AI_CHANGE_TOOL_NAME,
                _truncate_for_log(
                    json.dumps(tool_payload, ensure_ascii=False, default=str)
                ),
            )

            changes = tool_payload.get("changes")
            explanation = tool_payload.get("explanation")
            if isinstance(changes, list) and isinstance(explanation, str):
                normalized_changes: List[dict] = []
                for item in changes:
                    if not isinstance(item, dict):
                        continue
                    prop = item.get("property")
                    val = item.get("value")
                    if isinstance(prop, str) and isinstance(val, str):
                        normalized_changes.append({"property": prop, "value": val})

                if normalized_changes:
                    return AIChangeResponse(
                        changes=normalized_changes,
                        explanation=explanation.strip()
                        or "Applied the requested changes.",
                    )

        # Fallback: try to parse a JSON response from plain text.
        response_text = "".join(
            block.text for block in assistant_blocks if isinstance(block, TextResult)
        ).strip()
        if response_text:
            logger.info(
                "[DesignMode AI Change] Response (text):\n%s",
                _truncate_for_log(response_text),
            )
            parsed = _parse_design_mode_ai_change_response(response_text)
            if parsed:
                return AIChangeResponse(**parsed)

        # Final fallback: rule-based suggestions for common requests.
        changes, explanation = parse_design_request(
            request.user_request, request.element_info.computedStyles or {}
        )
        return AIChangeResponse(changes=changes, explanation=explanation)

    except Exception as e:
        logger.error("[DesignMode AI Change] Failed: %s", e, exc_info=True)
        # As a safety net, attempt the local heuristic rather than 500'ing.
        changes, explanation = parse_design_request(
            request.user_request, request.element_info.computedStyles or {}
        )
        return AIChangeResponse(changes=changes, explanation=explanation)


def _tokenize_dom_query(query: str) -> List[str]:
    return [t for t in re.split(r"[^a-zA-Z0-9#_\\-]+", query.lower()) if t]


def _build_iframe_snapshot_index(
    snapshot: IframeDocumentSnapshot,
) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for node in snapshot.nodes:
        design_id = (node.designId or "").strip()
        if not design_id:
            continue
        index[design_id] = {
            "designId": design_id,
            "tagName": (node.tagName or "").strip().lower(),
            "className": (node.className or "").strip(),
            "id": (node.id or "").strip(),
            "textContent": (node.textContent or "").strip(),
            "attributes": node.attributes or {},
            "parentDesignId": (node.parentDesignId or "").strip() or None,
            "childDesignIds": [
                c for c in (node.childDesignIds or []) if isinstance(c, str)
            ],
            "html": (node.html or ""),
        }
    return index


def _search_iframe_snapshot(
    nodes_by_id: Dict[str, Dict[str, Any]],
    query: str,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    q_lower = q.lower()
    tokens = _tokenize_dom_query(q)
    results: List[tuple[int, Dict[str, Any]]] = []

    for node in nodes_by_id.values():
        design_id = node.get("designId") or ""
        tag = node.get("tagName") or ""
        class_name = node.get("className") or ""
        node_id = node.get("id") or ""
        text = node.get("textContent") or ""
        html = node.get("html") or ""
        attrs = node.get("attributes") or {}

        haystack = " ".join(
            [
                design_id,
                tag,
                class_name,
                node_id,
                text,
                html,
                " ".join(str(v) for v in attrs.values()),
            ]
        ).lower()

        score = 0
        if q_lower in haystack:
            score += 8

        for t in tokens:
            if not t:
                continue
            if t in design_id.lower():
                score += 6
            elif t in text.lower():
                score += 5
            elif t in class_name.lower():
                score += 3
            elif t in haystack:
                score += 1

        if score <= 0:
            continue

        results.append((score, node))

    results.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict[str, Any]] = []
    for score, node in results[: max(1, min(max_results, 50))]:
        out.append(
            {
                "design_id": node.get("designId"),
                "tag": node.get("tagName"),
                "className": (node.get("className") or "")[:240],
                "id": (node.get("id") or "")[:80],
                "textContent": (node.get("textContent") or "")[:240],
                "parentDesignId": node.get("parentDesignId"),
                "score": score,
            }
        )
    return out


def _normalize_iframe_ai_operations(operations: Any) -> List[Dict[str, Any]]:
    if not isinstance(operations, list):
        return []
    normalized: List[Dict[str, Any]] = []

    for op in operations:
        if not isinstance(op, dict):
            continue
        op_type = op.get("op")
        design_id = op.get("design_id") or op.get("designId") or op.get("designID")
        if not isinstance(op_type, str) or not isinstance(design_id, str):
            continue

        op_type = op_type.strip()
        design_id = design_id.strip()
        if not op_type or not design_id:
            continue

        item: Dict[str, Any] = {"op": op_type, "design_id": design_id}

        if op_type == "set_style":
            prop = op.get("property")
            val = op.get("value")
            if isinstance(prop, str):
                item["property"] = prop
            if isinstance(val, str):
                item["value"] = val
        elif op_type == "set_text":
            text = op.get("text")
            if isinstance(text, str):
                item["text"] = text
        elif op_type == "set_icon":
            icon_name = op.get("icon_name") or op.get("iconName") or op.get("name")
            svg_inner = op.get("svg_inner") or op.get("svgInner")
            if isinstance(icon_name, str):
                item["icon_name"] = icon_name
            if isinstance(svg_inner, str):
                item["svg_inner"] = svg_inner
        elif op_type == "move":
            anchor = op.get("anchor")
            if isinstance(anchor, str):
                item["anchor"] = anchor
        elif op_type == "swap":
            target = op.get("target_design_id") or op.get("targetDesignId")
            if isinstance(target, str):
                item["target_design_id"] = target

        normalized.append(item)

    return normalized


def _build_iframe_selected_subtree_hint(
    nodes_by_id: Dict[str, Dict[str, Any]],
    selected_design_id: str,
    *,
    max_nodes: int = 28,
) -> str:
    """Build a compact subtree summary to help the model retarget quickly."""
    root_id = (selected_design_id or "").strip()
    if not root_id or root_id not in nodes_by_id:
        return ""

    visited: set[str] = set()
    queue: List[str] = [root_id]
    collected: List[Dict[str, Any]] = []

    while queue and len(collected) < max_nodes:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        node = nodes_by_id.get(current)
        if not node:
            continue
        collected.append(node)

        for child in node.get("childDesignIds") or []:
            if isinstance(child, str) and child and child not in visited:
                queue.append(child)

    lines: List[str] = []
    icon_candidates: List[str] = []
    svg_elements: List[str] = []

    for node in collected:
        did = node.get("designId") or ""
        tag = node.get("tagName") or ""
        class_name = (node.get("className") or "")[:140]
        text = (node.get("textContent") or "")[:140]
        html = node.get("html") or ""
        has_svg = "<svg" in html.lower() or str(tag).lower() == "svg"

        # Track SVG elements separately
        if str(tag).lower() == "svg" and isinstance(did, str) and did:
            svg_elements.append(did)
        elif has_svg and isinstance(did, str) and did:
            icon_candidates.append(did)

        lines.append(
            f"- {did}: <{tag}> class='{class_name}' text='{text}' has_svg={has_svg}"
        )

    if svg_elements:
        lines.append("")
        lines.append(
            "SVG elements in selected subtree (prefer these for icon changes):"
        )
        for did in svg_elements[:6]:
            node = nodes_by_id.get(did) or {}
            classes = (node.get("className") or "")[:200]
            html_snippet = re.sub(r"\s+", " ", (node.get("html") or "")).strip()[:300]
            lines.append(f"- {did} class='{classes}' html: {html_snippet}")

    if icon_candidates:
        lines.append("")
        lines.append(
            "Container elements with SVG children (use if SVG elements don't work):"
        )
        for did in icon_candidates[:4]:
            html = (nodes_by_id.get(did) or {}).get("html") or ""
            snippet = re.sub(r"\s+", " ", html).strip()[:380]
            lines.append(f"- {did} html: {snippet}")

    return "\n".join(lines)


@router.post("/ai-iframe-plan", response_model=IframeAIPlanResponse)
async def ai_iframe_plan(
    current_user: CurrentUser,
    request: IframeAIPlanRequest,
) -> IframeAIPlanResponse:
    """
    Generate a plan to modify the *iframe copy* (DOM snapshot) in Design Mode.

    This does NOT touch the sandbox. The frontend applies the returned operations to the iframe,
    which are then recorded in the Design Mode change tracker for user review and later syncing.
    """
    session = await Sessions.get_session_by_id(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    nodes_by_id = _build_iframe_snapshot_index(request.document_snapshot)

    snapshot = request.document_snapshot
    safe_url = _redact_url_for_prompt(snapshot.url or "")
    snapshot_desc = (
        f"- url: {safe_url}\n"
        f"- title: {(snapshot.title or '')[:200]}\n"
        f"- nodes: {len(snapshot.nodes or [])}\n"
    )

    selected = request.selected_element
    selected_desc = ""
    selected_subtree_hint = ""
    if selected:
        computed_summary = ""
        try:
            computed = (
                selected.computedStyles
                if isinstance(getattr(selected, "computedStyles", None), dict)
                else {}
            )
            interesting = {}
            for key in (
                "backgroundColor",
                "color",
                "fontSize",
                "fontWeight",
                "padding",
                "margin",
            ):
                value = computed.get(key)
                if isinstance(value, str) and value.strip():
                    interesting[key] = value.strip()
            if interesting:
                computed_summary = json.dumps(interesting, ensure_ascii=False)[:400]
        except Exception:
            computed_summary = ""

        parent_hint = ""
        try:
            selected_node = nodes_by_id.get(selected.designId) or {}
            parent_id = selected_node.get("parentDesignId")
            if isinstance(parent_id, str) and parent_id.strip():
                parent_id = parent_id.strip()
                parent_node = nodes_by_id.get(parent_id) or {}
                parent_tag = (parent_node.get("tagName") or "").strip()
                parent_class = (parent_node.get("className") or "")[:160]
                if parent_tag or parent_class:
                    parent_hint = (
                        f"- parent: {parent_id} <{parent_tag}> class='{parent_class}'\n"
                    )
                else:
                    parent_hint = f"- parent: {parent_id}\n"
        except Exception:
            parent_hint = ""

        selected_desc = (
            f"- designId: {selected.designId}\n"
            f"- tag: {selected.tagName}\n"
            f"- class: {(selected.className or '')[:200]}\n"
            f"- text: {(selected.textContent or '')[:200]}\n"
            + (f"- computedStyles: {computed_summary}\n" if computed_summary else "")
            + parent_hint
        )
        selected_subtree_hint = _build_iframe_selected_subtree_hint(
            nodes_by_id, selected.designId
        )

    prompt = build_design_mode_iframe_plan_prompt(
        snapshot_desc=snapshot_desc,
        user_request=request.user_request,
        selected_desc=selected_desc or None,
        selected_subtree_hint=selected_subtree_hint or None,
        search_tool_name=DESIGN_MODE_IFRAME_AI_SEARCH_TOOL_NAME,
        get_node_tool_name=DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL_NAME,
        list_icons_tool_name=DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL_NAME,
        get_icon_svg_tool_name=DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL_NAME,
        plan_tool_name=DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME,
    )

    try:
        llm_config = await _get_llm_config_for_session(session)
        llm_config.temperature = 0.0
        # Disable thinking for design mode AI (will use tool_choice which conflicts with thinking)
        llm_config.thinking_tokens = 0
        client = get_client(llm_config)

        logger.info(
            "[DesignMode AI Iframe] Using model=%s api_type=%s",
            llm_config.model,
            llm_config.api_type,
        )
        logger.info(
            "[DesignMode AI Iframe] Prompt:\n%s",
            _truncate_for_log(prompt),
        )

        tools = [
            DESIGN_MODE_IFRAME_AI_SEARCH_TOOL,
            DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL,
            DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL,
            DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL,
            DESIGN_MODE_IFRAME_AI_PLAN_TOOL,
        ]

        messages: List[List[Any]] = [[TextPrompt(text=prompt)]]

        plan_payload: Optional[Dict[str, Any]] = None
        max_steps = 10  # Increased from 6 to allow more tool exploration
        coerced = False
        icon_search_count = 0  # Track icon searches
        max_icon_searches = 3  # Limit icon searches to 3

        forced_plan_tool_choice: Dict[str, str] = {"type": "any"}
        if llm_config.api_type in {"openai", "anthropic"}:
            forced_plan_tool_choice = {
                "type": "tool",
                "name": DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME,
            }

        for _step in range(max_steps):
            step_tool_choice = (
                forced_plan_tool_choice
                if coerced or _step == max_steps - 1
                else {"type": "any"}
            )

            assistant_blocks, _raw_metrics = await client.agenerate(
                messages=messages,
                max_tokens=600,
                system_prompt="",
                temperature=0.0,
                tools=tools,
                tool_choice=step_tool_choice,
            )

            await _track_llm_usage_and_charge(
                session_id=request.session_id,
                model_name=llm_config.model,
                raw_metrics=_raw_metrics,
            )

            messages.append(assistant_blocks)  # assistant turn

            tool_calls = [b for b in assistant_blocks if isinstance(b, ToolCall)]
            if not tool_calls:
                response_text = "".join(
                    b.text for b in assistant_blocks if isinstance(b, TextResult)
                ).strip()
                if response_text:
                    logger.info(
                        "[DesignMode AI Iframe] Response (text):\n%s",
                        _truncate_for_log(response_text),
                    )
                if not coerced:
                    coerced = True
                    messages.append(
                        [
                            TextPrompt(
                                text=(
                                    f"Now CALL `{DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME}` EXACTLY ONCE. "
                                    "Do not reply with normal text. "
                                    "If you need to explain uncertainty, put it in the tool `explanation`."
                                )
                            )
                        ]
                    )
                    continue
                break

            try:
                logger.info(
                    "[DesignMode AI Iframe] Step %s tool calls: %s",
                    _step + 1,
                    ", ".join([c.tool_name for c in tool_calls]),
                )
            except Exception:
                pass

            # If the model already submitted the plan, stop.
            submitted = next(
                (
                    b
                    for b in tool_calls
                    if b.tool_name == DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME
                ),
                None,
            )
            if submitted:
                if isinstance(submitted.tool_input, dict):
                    plan_payload = submitted.tool_input
                    logger.info(
                        "[DesignMode AI Iframe] Tool payload (%s):\n%s",
                        DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME,
                        _truncate_for_log(
                            json.dumps(plan_payload, ensure_ascii=False, default=str)
                        ),
                    )
                break

            # Execute tool calls and feed results back.
            for call in tool_calls:
                tool_name = call.tool_name
                tool_input = (
                    call.tool_input if isinstance(call.tool_input, dict) else {}
                )
                try:
                    logger.info(
                        "[DesignMode AI Iframe] Tool call: %s input=%s",
                        tool_name,
                        _truncate_for_log(
                            json.dumps(tool_input, ensure_ascii=False, default=str)
                        ),
                    )
                except Exception:
                    pass

                if tool_name == DESIGN_MODE_IFRAME_AI_SEARCH_TOOL_NAME:
                    query = (
                        tool_input.get("query")
                        if isinstance(tool_input.get("query"), str)
                        else ""
                    )
                    max_results = (
                        tool_input.get("max_results")
                        if isinstance(tool_input.get("max_results"), int)
                        else 10
                    )
                    tool_out = {
                        "results": _search_iframe_snapshot(
                            nodes_by_id, query=query, max_results=max_results
                        )
                    }
                elif tool_name == DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL_NAME:
                    design_id = (
                        tool_input.get("design_id")
                        if isinstance(tool_input.get("design_id"), str)
                        else ""
                    )
                    node = nodes_by_id.get(design_id)
                    tool_out = {"node": node} if node else {"error": "not_found"}
                elif tool_name == DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL_NAME:
                    icon_search_count += 1  # Increment icon search counter
                    query = (
                        tool_input.get("query")
                        if isinstance(tool_input.get("query"), str)
                        else None
                    )
                    limit = (
                        tool_input.get("limit")
                        if isinstance(tool_input.get("limit"), int)
                        else 50
                    )
                    icons = lucide_icon_catalog.list_icons(query=query, limit=limit)

                    # If we've hit the limit, inform the AI to submit now
                    if icon_search_count >= max_icon_searches:
                        tool_out = {
                            "icons": icons,
                            "note": f"Maximum {max_icon_searches} icon searches reached. Please submit your plan now with the best match.",
                        }
                    else:
                        tool_out = {"icons": icons}
                elif tool_name == DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL_NAME:
                    name = (
                        tool_input.get("name")
                        if isinstance(tool_input.get("name"), str)
                        else ""
                    )
                    svg_inner = lucide_icon_catalog.get_icon_svg_inner(name)
                    if svg_inner:
                        tool_out = {"name": name, "svg_inner": svg_inner}
                    else:
                        tool_out = {
                            "error": "not_found",
                            "suggestions": lucide_icon_catalog.list_icons(
                                query=name, limit=15
                            ),
                        }
                else:
                    tool_out = {"error": f"unknown_tool:{tool_name}"}

                try:
                    logger.info(
                        "[DesignMode AI Iframe] Tool result: %s output=%s",
                        tool_name,
                        _truncate_for_log(
                            json.dumps(tool_out, ensure_ascii=False, default=str)
                        ),
                    )
                except Exception:
                    pass

                messages.append(
                    [
                        ToolFormattedResult(
                            tool_call_id=call.tool_call_id,
                            tool_name=tool_name,
                            tool_output=json.dumps(
                                tool_out, ensure_ascii=False, default=str
                            ),
                        )
                    ]
                )

            # Force plan submission if we've hit the icon search limit
            if icon_search_count >= max_icon_searches and not coerced:
                logger.info(
                    "[DesignMode AI Iframe] Icon search limit reached (%s/%s). Forcing plan submission.",
                    icon_search_count,
                    max_icon_searches,
                )
                coerced = True

        if plan_payload and isinstance(plan_payload, dict):
            operations = _normalize_iframe_ai_operations(plan_payload.get("operations"))
            validated_ops: List[Dict[str, Any]] = []
            for op in operations:
                design_id = op.get("design_id")
                if not isinstance(design_id, str) or design_id not in nodes_by_id:
                    continue

                op_type = op.get("op")
                if op_type == "set_style":
                    prop = op.get("property")
                    if not isinstance(prop, str) or not prop:
                        continue
                    if not isinstance(op.get("value"), str):
                        op["value"] = ""
                    validated_ops.append(op)
                    continue

                if op_type == "set_text":
                    if not isinstance(op.get("text"), str):
                        op["text"] = ""
                    validated_ops.append(op)
                    continue

                if op_type == "set_icon":
                    icon_name = op.get("icon_name")
                    svg_inner = op.get("svg_inner")
                    if not isinstance(icon_name, str) or not icon_name.strip():
                        logger.warning(
                            "[DesignMode AI Iframe] Skipping set_icon op for %s: missing or invalid icon_name",
                            design_id,
                        )
                        continue

                    # Fix: The AI model sometimes double-escapes quotes in the svg_inner string
                    # e.g., width=\"18\" instead of width="18"
                    # Unescape backslash-quote sequences
                    if isinstance(svg_inner, str) and svg_inner.strip():
                        svg_inner = svg_inner.replace('\\"', '"').replace("\\'", "'")

                    if not isinstance(svg_inner, str) or not svg_inner.strip():
                        svg_inner = lucide_icon_catalog.get_icon_svg_inner(icon_name)
                        if not svg_inner:
                            logger.warning(
                                "[DesignMode AI Iframe] Skipping set_icon op for %s: icon '%s' not found in catalog",
                                design_id,
                                icon_name,
                            )
                            continue
                        logger.info(
                            "[DesignMode AI Iframe] Filled svg_inner for icon '%s' from catalog (%d bytes)",
                            icon_name,
                            len(svg_inner),
                        )
                    if len(svg_inner) > 20000:
                        logger.warning(
                            "[DesignMode AI Iframe] Skipping set_icon op for %s: svg_inner too large (%d bytes)",
                            design_id,
                            len(svg_inner),
                        )
                        continue
                    op["icon_name"] = icon_name.strip()
                    op["svg_inner"] = svg_inner
                    validated_ops.append(op)
                    logger.info(
                        "[DesignMode AI Iframe] Validated set_icon op: design_id=%s icon_name=%s svg_len=%d",
                        design_id,
                        icon_name.strip(),
                        len(svg_inner),
                    )
                    continue

                if op_type == "move":
                    anchor = op.get("anchor")
                    if not isinstance(anchor, str) or not anchor:
                        continue
                    # Best-effort validation for before:/after: anchors.
                    if anchor.startswith("before:") or anchor.startswith("after:"):
                        target_id = anchor.split(":", 1)[1]
                        if target_id and target_id not in nodes_by_id:
                            continue
                    validated_ops.append(op)
                    continue

                if op_type == "swap":
                    target = op.get("target_design_id")
                    if (
                        not isinstance(target, str)
                        or not target
                        or target not in nodes_by_id
                    ):
                        continue
                    validated_ops.append(op)
                    continue

            explanation = (
                plan_payload.get("explanation")
                if isinstance(plan_payload.get("explanation"), str)
                else ""
            ).strip()
            if not explanation:
                explanation = "Applied the requested changes."

            return IframeAIPlanResponse(
                operations=validated_ops, explanation=explanation
            )

        return IframeAIPlanResponse(
            operations=[],
            explanation=(
                "I couldn't generate a structured edit plan. "
                "Try re-selecting the element (or a smaller child element) and re-run the request."
            ),
        )

    except Exception as e:
        logger.error("[DesignMode AI Iframe] Failed: %s", e, exc_info=True)
        return IframeAIPlanResponse(
            operations=[],
            explanation="I couldn't generate an edit plan due to an error.",
        )


def _parse_design_mode_ai_change_response(content: str) -> Optional[Dict[str, Any]]:
    """Parse a JSON response for /ai-change from the model (best-effort)."""
    try:
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            return None

        result = json.loads(json_match.group(0))
        changes = result.get("changes")
        explanation = result.get("explanation", "")
        if not isinstance(changes, list):
            return None

        normalized_changes: List[dict] = []
        for item in changes:
            if not isinstance(item, dict):
                continue
            prop = item.get("property")
            value = item.get("value")
            if isinstance(prop, str) and isinstance(value, str):
                normalized_changes.append({"property": prop, "value": value})

        if not normalized_changes:
            return None

        return {
            "changes": normalized_changes,
            "explanation": (
                explanation.strip()
                if isinstance(explanation, str) and explanation.strip()
                else "Applied the requested changes."
            ),
        }

    except Exception:
        logger.debug(
            "[DesignMode AI Change] Failed to parse JSON response",
            exc_info=True,
        )
        return None


def parse_design_request(user_request: str, current_styles: dict) -> tuple:
    """
    Parse a user design request and return suggested changes.
    This is a simple rule-based fallback. Can be enhanced with actual LLM.
    """
    request_lower = user_request.lower()
    changes = []
    explanation = ""

    # Color changes
    color_keywords = {
        "red": "#ef4444",
        "blue": "#3b82f6",
        "green": "#22c55e",
        "yellow": "#eab308",
        "purple": "#a855f7",
        "pink": "#ec4899",
        "orange": "#f97316",
        "white": "#ffffff",
        "black": "#000000",
        "gray": "#6b7280",
        "grey": "#6b7280",
    }

    for color_name, color_value in color_keywords.items():
        if color_name in request_lower:
            if any(word in request_lower for word in ["background", "bg"]):
                changes.append({"property": "background-color", "value": color_value})
                explanation = f"Changed background color to {color_name}"
            elif (
                any(word in request_lower for word in ["text", "font", "color"])
                or "make" in request_lower
            ):
                changes.append({"property": "color", "value": color_value})
                explanation = f"Changed text color to {color_name}"
            else:
                # Default to background for "make it red" type requests
                changes.append({"property": "background-color", "value": color_value})
                explanation = f"Changed background color to {color_name}"
            break

    # Size changes
    if any(word in request_lower for word in ["bigger", "larger", "increase size"]):
        current_size = current_styles.get("fontSize", "16px")
        try:
            size_val = int(current_size.replace("px", ""))
            new_size = min(size_val + 4, 72)
            changes.append({"property": "font-size", "value": f"{new_size}px"})
            explanation = f"Increased font size to {new_size}px"
        except:
            changes.append({"property": "font-size", "value": "20px"})
            explanation = "Increased font size"

    if any(word in request_lower for word in ["smaller", "decrease size", "reduce"]):
        current_size = current_styles.get("fontSize", "16px")
        try:
            size_val = int(current_size.replace("px", ""))
            new_size = max(size_val - 4, 8)
            changes.append({"property": "font-size", "value": f"{new_size}px"})
            explanation = f"Decreased font size to {new_size}px"
        except:
            changes.append({"property": "font-size", "value": "12px"})
            explanation = "Decreased font size"

    # Bold
    if any(word in request_lower for word in ["bold", "bolder"]):
        changes.append({"property": "font-weight", "value": "700"})
        explanation = "Made text bold"

    # Padding
    if "padding" in request_lower:
        if any(word in request_lower for word in ["more", "increase", "add"]):
            changes.append({"property": "padding", "value": "16px"})
            explanation = "Increased padding"
        elif any(word in request_lower for word in ["less", "decrease", "remove"]):
            changes.append({"property": "padding", "value": "4px"})
            explanation = "Decreased padding"

    # Rounded corners
    if any(word in request_lower for word in ["round", "rounded", "radius"]):
        changes.append({"property": "border-radius", "value": "8px"})
        explanation = "Added rounded corners"

    # Center
    if "center" in request_lower:
        changes.append({"property": "text-align", "value": "center"})
        explanation = "Centered the text"

    # Default response if nothing matched
    if not changes:
        explanation = f"I understood your request: '{user_request}'. Try being more specific like 'make it red' or 'increase font size'."

    return changes, explanation


# ==========================================
# Sync Endpoint (Phase 6)
# ==========================================


class ElementContext(BaseModel):
    """Enhanced element context for better source file matching."""

    designId: str
    slideNumber: Optional[int] = None
    tagName: str
    className: Optional[str] = None
    id: Optional[str] = None
    textContent: Optional[str] = None
    innerHTML: Optional[str] = None
    outerHTML: Optional[str] = None
    contextText: Optional[str] = None
    prevSiblingText: Optional[str] = None
    nextSiblingText: Optional[str] = None
    reactSource: Optional[Dict[str, Any]] = None
    attributes: Optional[Dict[str, str]] = None
    parentChain: Optional[List[Dict[str, str]]] = None
    xpath: Optional[str] = None
    computedStyles: Optional[Dict[str, str]] = None


class StyleChange(BaseModel):
    """A single style change with element context."""

    designId: str
    slideNumber: Optional[int] = None
    type: str  # 'style' or 'text'
    property: str
    value: dict  # { from: string, to: string }
    timestamp: int
    elementContext: Optional[ElementContext] = None
    groupId: Optional[str] = None
    groupLabel: Optional[str] = None


# ==========================================
# Persisted Design State (Phase 5.5)
# ==========================================


class DesignStateRequest(BaseModel):
    """Request body for persisting design mode state (pending changes)."""

    session_id: str
    changes: List[StyleChange]


class DesignStateResponse(BaseModel):
    """Response for persisted design mode state."""

    session_id: str
    changes: List[StyleChange]
    updated_at: Optional[int] = None


@router.get("/state", response_model=DesignStateResponse)
async def get_design_state(
    current_user: CurrentUser,
    session_id: str = Query(..., description="Session ID"),
) -> DesignStateResponse:
    """Return the persisted design-mode pending changes for a session."""
    session = await Sessions.get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    metadata = session.session_metadata or {}
    design_mode = metadata.get("design_mode") or {}
    raw_changes = design_mode.get("changes") or []
    updated_at = design_mode.get("updated_at")

    changes: List[StyleChange] = []
    for item in raw_changes:
        if not isinstance(item, dict):
            continue
        try:
            changes.append(StyleChange(**item))
        except Exception:
            # Be resilient to old/invalid payloads rather than hard-failing page load.
            logger.warning("Skipping invalid persisted design change: %s", item)

    return DesignStateResponse(
        session_id=str(session.id),
        changes=changes,
        updated_at=updated_at if isinstance(updated_at, int) else None,
    )


@router.post("/state", response_model=DesignStateResponse)
async def set_design_state(
    current_user: CurrentUser,
    request: DesignStateRequest,
) -> DesignStateResponse:
    """Persist the current design-mode pending changes for a session."""
    session = await Sessions.get_session_by_id(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        session_uuid = uuid.UUID(request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id") from exc

    updated_at = int(time.time() * 1000)
    design_state = {
        "changes": [change.model_dump() for change in request.changes],
        "updated_at": updated_at,
    }

    async with get_db_session_local() as db:
        db_session = await Sessions.find_session_by_id(db=db, session_id=session_uuid)
        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")
        db_session.session_metadata = {
            **(db_session.session_metadata or {}),
            "design_mode": design_state,
        }
        db.add(db_session)
        await db.flush()

    return DesignStateResponse(
        session_id=request.session_id,
        changes=request.changes,
        updated_at=updated_at,
    )


class SyncRequest(BaseModel):
    """Request body for syncing design changes."""

    session_id: str
    changes: List[StyleChange]
    project_info: Optional[dict] = None


class SyncResponse(BaseModel):
    """Response for sync endpoint."""

    success: bool
    applied: int
    errors: List[str]


@router.post("/sync", response_model=SyncResponse)
async def sync_design_changes(
    current_user: CurrentUser,
    request: SyncRequest,
) -> SyncResponse:
    """
    Sync design mode changes to sandbox source files.

    This endpoint applies changes deterministically by locating `data-design-id="..."`
    in the sandbox source and updating inline styles/text without using an LLM.
    """
    # Validate session ownership
    session = await Sessions.get_session_by_id(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if str(session.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    logger.info(
        "Sync request: %d changes for session %s",
        len(request.changes),
        request.session_id,
    )

    # Get sandbox for file operations using V1 sandbox system
    try:
        sandbox = await _get_v1_sandbox_for_session(session.id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sandbox: {e}")
        raise HTTPException(status_code=500, detail="Sandbox not available")

    applied_count, errors, remaining_changes = await _apply_changes_with_source_mapping(
        sandbox=sandbox,
        changes=request.changes,
        session_id=session.id,
    )

    success = (
        applied_count == len(request.changes)
        and len(errors) == 0
        and len(remaining_changes) == 0
    )

    logger.info(
        "Sync complete: %d/%d applied, %d errors",
        applied_count,
        len(request.changes),
        len(errors),
    )
    if errors:
        logger.warning(
            "[DesignMode Sync] Errors (%d):\n%s",
            len(errors),
            _truncate_for_log("\n".join(errors), limit=8000),
        )

    return SyncResponse(success=success, applied=applied_count, errors=errors)


# ==========================================
# Sync Persisted State to Sandbox (Phase 6.5)
# ==========================================


class SyncStateRequest(BaseModel):
    """Request body for syncing persisted design-mode changes."""

    session_id: str


class SyncStateResponse(BaseModel):
    """Response for syncing persisted design-mode changes."""

    success: bool
    applied: int
    total: int
    remaining: int
    errors: List[str]
    summary: str
    remaining_changes: List[StyleChange]
    event_id: Optional[str] = None


def _parse_persisted_design_changes(raw_changes: Any) -> List[StyleChange]:
    """Parse persisted design changes from session metadata (best-effort)."""
    if not isinstance(raw_changes, list):
        return []

    changes: List[StyleChange] = []
    for item in raw_changes:
        if not isinstance(item, dict):
            continue
        try:
            changes.append(StyleChange(**item))
        except Exception:
            # Be resilient to old/invalid payloads rather than hard-failing.
            logger.warning("Skipping invalid persisted design change: %s", item)
    changes.sort(key=lambda c: int(getattr(c, "timestamp", 0) or 0))
    return changes


def _truncate_for_log(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _redact_url_for_prompt(url: str, limit: int = 300) -> str:
    """Best-effort redact sensitive query params for logging/prompting."""
    if not url:
        return ""
    safe = url
    try:
        parsed = urlparse(url)
        redacted_query = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key.lower() in {
                "token",
                "auth_token",
                "authorization",
                "x-api-key",
                "api_key",
            }:
                redacted_query.append((key, "<redacted>"))
                continue
            if isinstance(value, str) and len(value) > 120:
                redacted_query.append((key, value[:117] + "..."))
            else:
                redacted_query.append((key, value))
        safe = parsed._replace(query=urlencode(redacted_query, doseq=True)).geturl()
    except Exception:
        safe = url
    return safe[:limit]


async def _emit_socket_chat_event(
    *,
    session_id: uuid.UUID,
    event_type: EventType,
    content: Dict[str, Any],
) -> None:
    """Best-effort emit a chat_event to the Socket.IO room for this session."""
    try:
        # Import locally to avoid circular imports during app startup.
        from ii_agent.server import shared

        event_data = {
            "type": (
                event_type.value if hasattr(event_type, "value") else str(event_type)
            ),
            "content": content,
        }
        room = str(session_id)

        if shared.session_manager is not None:
            await shared.session_manager.emit(
                "chat_event",
                event_data,
                room=room,
                namespace="/",
            )
        elif shared.sio is not None:
            await shared.sio.emit(
                "chat_event",
                event_data,
                room=room,
                namespace="/",
            )
    except Exception as exc:
        logger.debug("Failed to emit Socket.IO chat_event: %s", exc)


async def _emit_design_mode_sync_progress(
    *,
    session_id: Optional[uuid.UUID],
    processed: int,
    total: int,
    applied: int,
    errors: int,
    current: Optional[int] = None,
    done: bool = False,
) -> None:
    """Emit Design Mode sync progress to the frontend (best-effort)."""
    if not session_id:
        return

    await _emit_socket_chat_event(
        session_id=session_id,
        event_type=EventType.STATUS_UPDATE,
        content={
            "operation": "design_mode_sync",
            "progress": {
                "processed": processed,
                "total": total,
                "applied": applied,
                "errors": errors,
                "current": current,
                "done": done,
            },
        },
    )


async def _track_llm_usage_and_charge(
    *,
    session_id: str,
    model_name: str,
    raw_metrics: Optional[Dict[str, Any]],
) -> None:
    """Best-effort token accounting + credit deduction for Design Mode LLM calls."""
    if not session_id or not raw_metrics:
        return

    try:
        session_uuid = uuid.UUID(str(session_id))
    except Exception:
        logger.warning("[DesignMode] Invalid session_id for metrics: %s", session_id)
        return

    try:
        token_usage = TokenUsage.from_raw_metrics(raw_metrics, model_name=model_name)
        raw_metrics_for_storage = dict(raw_metrics or {})
        # Provider clients include `raw_response` objects that are not JSON serializable.
        # We don't need them for auditing token usage, and persisting them breaks the DB insert.
        raw_metrics_for_storage.pop("raw_response", None)
        metrics_payload = {
            **token_usage.model_dump(),
            **raw_metrics_for_storage,
            "model_name": model_name,
        }
        try:
            json.dumps(metrics_payload)
        except TypeError:
            metrics_payload = json.loads(
                json.dumps(metrics_payload, ensure_ascii=False, default=str)
            )
    except Exception as exc:
        logger.warning(
            "[DesignMode] Failed to parse LLM usage metrics: %s", exc, exc_info=True
        )
        return

    try:
        async with get_db_session_local() as db_session:
            # Persist METRICS_UPDATE so we can audit Design Mode token usage like chat/agent flows.
            # Use a dedicated transaction so failures here don't poison later credit deductions.
            try:
                async with db_session.begin():
                    metrics_event = RealtimeEvent(
                        type=EventType.METRICS_UPDATE,
                        session_id=session_uuid,
                        content=metrics_payload,
                    )
                    await Events.save_event_db_session(
                        db=db_session,
                        session_id=session_uuid,
                        event=metrics_event,
                    )
            except Exception as exc:
                logger.debug(
                    "[DesignMode] Failed to persist metrics event: %s",
                    exc,
                    exc_info=True,
                )

            # Charge credits using the shared metrics/credits service.
            try:
                async with db_session.begin():
                    await calculate_user_credits(
                        db_session=db_session,
                        session_id=str(session_id),
                        content=token_usage.model_dump(),
                    )
            except Exception as exc:
                logger.warning(
                    "[DesignMode] Failed to charge credits for LLM usage: %s",
                    exc,
                    exc_info=True,
                )
    except Exception as exc:
        logger.warning(
            "[DesignMode] Failed to record metrics / charge credits: %s",
            exc,
            exc_info=True,
        )


async def _get_llm_config_for_session(session: Any) -> LLMConfig:
    """
    Best-effort: use the same LLM config as the session, so sync has credentials.

    Sessions may store either:
    - a user LLM setting id (DB row id), or
    - a system LLM config key (in `config.llm_configs`).
    """
    setting_id = getattr(session, "llm_setting_id", None)
    if setting_id:
        async with get_db_session_local() as db:
            try:
                llm_config = await get_user_llm_config(
                    model_id=str(setting_id),
                    user_id=str(session.user_id),
                    db_session=db,
                )
            except Exception:
                llm_config = get_system_llm_config(model_id=str(setting_id))
        return llm_config.model_copy(deep=True)

    # Fallback to a system model if one is configured.
    if config.llm_configs:
        fallback_id = (
            "default"
            if "default" in config.llm_configs
            else next(iter(config.llm_configs.keys()))
        )
        llm_config = get_system_llm_config(model_id=fallback_id)
        return llm_config.model_copy(deep=True)

    # Last resort: rely on environment variables for the default client.
    return LLMConfig()


def _build_batch_sync_prompt(
    indexed_changes: List[tuple[int, StyleChange]],
    *,
    workspace_roots: Optional[List[str]] = None,
    source_hints: Optional[Dict[int, str]] = None,
) -> str:
    """
    Build a single prompt that contains *all* changes so we can make one LLM request.

    The LLM should call our tool and return per-change modifications keyed by `change_index`.
    """
    change_blocks: List[str] = []
    for change_index, change in indexed_changes:
        ctx = change.elementContext
        if not ctx:
            continue

        element_desc = f"<{ctx.tagName}"
        if ctx.id:
            element_desc += f' id="{ctx.id}"'
        if ctx.className:
            element_desc += f' class="{ctx.className}"'
        element_desc += ">"

        parent_context = ""
        if ctx.parentChain:
            parent_context = " > ".join(
                [
                    f"<{p.get('tag')}"
                    + (f" class='{p.get('className')}'" if p.get("className") else "")
                    + ">"
                    for p in ctx.parentChain
                    if isinstance(p, dict) and p.get("tag")
                ]
            )

        if change.type == "style":
            old_value = change.value.get("from", "")
            new_value = change.value.get("to", "")
            tailwind_hint = _get_tailwind_hint(change.property, old_value, new_value)
            change_desc = (
                f"- kind: style\n"
                f"- property: {change.property}\n"
                f"- old: {old_value}\n"
                f"- new: {new_value}{tailwind_hint}\n"
            )
        elif change.type == "text":
            change_desc = (
                f"- kind: text\n"
                f"- old: {change.value.get('from', '')}\n"
                f"- new: {change.value.get('to', '')}\n"
            )
        elif change.type == "attribute" and change.property == "icon":
            # Parse icon name for better display
            to_value = change.value.get("to", "")
            icon_name = ""
            try:
                icon_data = json.loads(to_value) if isinstance(to_value, str) else {}
                icon_name = icon_data.get("name", "")
            except (json.JSONDecodeError, ValueError):
                icon_name = to_value
            change_desc = (
                f"- kind: icon\n"
                f"- new_icon: {icon_name}\n"
                f"- note: Replace the Lucide React icon component with the new icon and update imports\n"
            )
        else:
            change_desc = f"- kind: {change.type}\n- property: {change.property}\n"

        text_content = (ctx.textContent or "").strip()

        outer_html = (ctx.outerHTML or "").strip()
        if outer_html:
            outer_html = _truncate_for_log(outer_html, 500)

        hint = ""
        if source_hints and isinstance(source_hints.get(change_index), str):
            hint = f"\n- source_hint:\n{source_hints[change_index]}\n"

        block = f"""Change {change_index}:
- designId: {change.designId}
- element: {element_desc}
- xpath: {ctx.xpath or "N/A"}
- parents: {parent_context or "N/A"}
- textContent: {text_content or "N/A"}
- outerHTML: {outer_html or "N/A"}
{change_desc}"""
        if hint:
            block += hint
        change_blocks.append(block)

    changes_text = "\n".join(change_blocks) if change_blocks else "(none)"

    workspace_roots_text = ""
    if workspace_roots:
        shown = workspace_roots[:10]
        extra = len(workspace_roots) - len(shown)
        formatted = "\n".join(f"- {root}" for root in shown)
        if extra > 0:
            formatted += f"\n- ... ({extra} more)"

        workspace_roots_text = f"""
**Workspace context:**
The sandbox project is often nested under `/workspace/<project-name>/...`, not directly under `/workspace/src/...`.
Top-level directories under `/workspace`:
{formatted}
"""

    return build_design_mode_batch_sync_prompt(
        workspace_roots_text=workspace_roots_text,
        changes_text=changes_text,
        plan_tool_name=DESIGN_MODE_SYNC_PLAN_TOOL_NAME,
    )


def _extract_source_search_text(change: StyleChange) -> Optional[str]:
    ctx = change.elementContext
    if ctx and isinstance(ctx.textContent, str) and ctx.textContent.strip():
        return ctx.textContent.strip()

    if ctx and isinstance(ctx.contextText, str) and ctx.contextText.strip():
        return ctx.contextText.strip()

    if ctx and isinstance(ctx.prevSiblingText, str) and ctx.prevSiblingText.strip():
        return ctx.prevSiblingText.strip()

    if ctx and isinstance(ctx.nextSiblingText, str) and ctx.nextSiblingText.strip():
        return ctx.nextSiblingText.strip()

    if isinstance(change.value, dict):
        for key in ("to", "from"):
            value = change.value.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def _extract_source_search_queries(change: StyleChange) -> List[str]:
    ctx = change.elementContext
    queries: List[str] = []

    def _add(value: Any) -> None:
        if not isinstance(value, str):
            return
        candidate = value.strip()
        if not candidate:
            return
        if candidate.lower() == "n/a":
            return
        queries.append(candidate)

    if ctx:
        _add(ctx.textContent)
        _add(ctx.contextText)
        _add(ctx.prevSiblingText)
        _add(ctx.nextSiblingText)
        _add(ctx.id)

        attrs = ctx.attributes or {}
        if isinstance(attrs, dict):
            for key in (
                "aria-label",
                "aria-labelledby",
                "title",
                "placeholder",
                "alt",
                "name",
                "value",
                "href",
            ):
                _add(attrs.get(key))

    if isinstance(change.value, dict):
        for key in ("to", "from"):
            _add(change.value.get(key))

    # De-dupe while preserving order.
    deduped: List[str] = []
    seen: set[str] = set()
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        deduped.append(q)
    return deduped


async def _build_source_hints_for_changes(
    sandbox: Any,
    indexed_changes: List[tuple[int, StyleChange]],
) -> Dict[int, str]:
    """
    Best-effort: find where an element's text appears in /workspace and provide a small excerpt.

    This helps the LLM copy exact substrings for `old` so string replacements succeed.
    """
    hints: Dict[int, str] = {}
    seen_queries: Dict[str, str] = {}
    max_hints = min(20, max(0, len(indexed_changes)))

    def _parse_search_lines(output: str) -> List[tuple[str, int]]:
        results: List[tuple[str, int]] = []
        for line in (output or "").splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(?P<path>/[^:]+):(?P<line>\d+):", line)
            if not match:
                continue
            path = match.group("path")
            try:
                line_no = int(match.group("line"))
            except Exception:
                continue
            results.append((path, line_no))
        return results

    def _score_path(path: str) -> tuple[int, int, int]:
        lowered = path.lower()
        ext_rank = 9
        for ext, rank in (
            (".tsx", 0),
            (".jsx", 1),
            (".ts", 2),
            (".js", 3),
            (".html", 4),
            (".css", 5),
        ):
            if lowered.endswith(ext):
                ext_rank = rank
                break
        in_src = 0 if "/src/" in lowered else 1
        return (ext_rank, in_src, len(path))

    async def _search_workspace(query: str) -> str:
        quoted = shlex.quote(query)
        cmd = (
            "if command -v rg >/dev/null 2>&1; then "
            f"rg --no-heading -n -F --hidden "
            "--glob '!**/node_modules/**' "
            "--glob '!**/.git/**' "
            "--glob '!**/dist/**' "
            "--glob '!**/build/**' "
            "--glob '!**/.next/**' "
            f"{quoted} /workspace | head -n 20; "
            "else "
            "grep -R -n -F "
            "--exclude-dir=node_modules "
            "--exclude-dir=.git "
            "--exclude-dir=dist "
            "--exclude-dir=build "
            "--exclude-dir=.next "
            f"-e {quoted} /workspace | head -n 20; "
            "fi"
        )
        try:
            return await sandbox.run_cmd(cmd) or ""
        except Exception:
            return ""

    async def _read_snippet(
        *,
        file_path: str,
        line_no: Optional[int],
        query: Optional[str],
    ) -> Optional[str]:
        try:
            content = await sandbox.read_file(file_path)
            if not isinstance(content, str):
                return None
        except Exception:
            return None

        lines = content.splitlines()
        if not lines:
            return None

        idx = 0
        if isinstance(line_no, int) and line_no > 0:
            idx = max(0, min(len(lines) - 1, line_no - 1))

        start = max(0, idx - 12)
        end = min(len(lines), idx + 13)
        snippet = "\n".join(lines[start:end]).rstrip()
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "\n...[truncated]"

        header_lines: List[str] = []
        if query:
            header_lines.append(f"  - query: {query}")
        header_lines.append(f"  - candidate_file: {file_path}")
        if isinstance(line_no, int) and line_no > 0:
            header_lines.append(f"  - excerpt_lines: {start + 1}-{end}")

        header = "\n".join(header_lines)
        return f"{header}\n" "```tsx\n" f"{snippet}\n" "```"

    async def _hint_from_react_source(ctx: ElementContext) -> Optional[str]:
        if not ctx or not isinstance(ctx.reactSource, dict):
            return None

        raw_file = ctx.reactSource.get("fileName")
        if not isinstance(raw_file, str) or not raw_file.strip():
            return None

        normalized_file = _normalize_react_source_file_name(raw_file)
        if not normalized_file:
            return None

        normalized_path = _normalize_workspace_file_path(normalized_file)
        if not normalized_path:
            return None

        try:
            resolved_content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, normalized_path
            )
            if not isinstance(resolved_content, str):
                return None
        except Exception:
            return None

        line_no = None
        try:
            line_no = int(ctx.reactSource.get("lineNumber") or 0) or None
        except Exception:
            line_no = None

        # Prefer a line-based snippet when we have line numbers.
        snippet = await _read_snippet(
            file_path=resolved_path,
            line_no=line_no,
            query=f"reactSource: {raw_file}",
        )
        if snippet:
            return snippet

        # Fallback: just show the beginning of the file.
        head = "\n".join(resolved_content.splitlines()[:40]).rstrip()
        if len(head) > 2000:
            head = head[:2000] + "\n...[truncated]"
        return (
            f"  - reactSource: {raw_file}\n"
            f"  - candidate_file: {resolved_path}\n"
            "```tsx\n"
            f"{head}\n"
            "```"
        )

    def _extract_class_tokens(ctx: ElementContext) -> List[str]:
        tokens: List[str] = []
        if ctx and isinstance(ctx.className, str) and ctx.className.strip():
            tokens.extend(ctx.className.split())
        if ctx and isinstance(ctx.parentChain, list):
            for parent in ctx.parentChain:
                if not isinstance(parent, dict):
                    continue
                class_name = parent.get("className")
                if isinstance(class_name, str) and class_name.strip():
                    tokens.extend(class_name.split())

        ignored = {
            "flex",
            "block",
            "inline",
            "inline-block",
            "grid",
            "relative",
            "absolute",
            "fixed",
            "w-full",
            "h-full",
            "items-center",
            "justify-center",
            "justify-between",
            "text-sm",
            "text-base",
        }

        filtered: List[str] = []
        for tok in tokens:
            tok = tok.strip()
            if not tok or tok in ignored:
                continue
            if len(tok) < 4:
                continue
            filtered.append(tok)

        # Prefer "unique-ish" tailwind tokens first.
        filtered.sort(key=lambda t: (0 if any(c in t for c in "[]:_") else 1, -len(t)))
        deduped: List[str] = []
        seen: set[str] = set()
        for tok in filtered:
            if tok in seen:
                continue
            seen.add(tok)
            deduped.append(tok)
        return deduped[:6]

    async def _best_file_by_class_tokens(
        tokens: List[str],
    ) -> Optional[tuple[str, int, str]]:
        if not tokens:
            return None

        scores: Dict[str, int] = {}
        token_hits: Dict[str, List[str]] = {}

        for tok in tokens[:4]:
            quoted = shlex.quote(tok)
            cmd = (
                "if command -v rg >/dev/null 2>&1; then "
                f"rg -l -F --hidden "
                "--glob '*.{tsx,jsx,ts,js,html,css,scss,sass,less}' "
                "--glob '!**/node_modules/**' "
                "--glob '!**/.git/**' "
                "--glob '!**/dist/**' "
                "--glob '!**/build/**' "
                "--glob '!**/.next/**' "
                f"{quoted} /workspace | head -n 200; "
                "else "
                "grep -R -l -F "
                "--exclude-dir=node_modules "
                "--exclude-dir=.git "
                "--exclude-dir=dist "
                "--exclude-dir=build "
                "--exclude-dir=.next "
                f"-e {quoted} /workspace | head -n 200; "
                "fi"
            )
            try:
                out = await sandbox.run_cmd(cmd) or ""
            except Exception:
                out = ""
            files = [line.strip() for line in out.splitlines() if line.strip()]
            if not files:
                continue
            token_hits[tok] = files
            for path in files:
                scores[path] = scores.get(path, 0) + 1

        if not scores:
            return None

        best_path = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

        # Pick the token that matched the best path to locate a line number.
        best_token = None
        for tok, files in token_hits.items():
            if best_path in files:
                best_token = tok
                break
        if not best_token:
            best_token = tokens[0]

        line_no = 1
        try:
            quoted = shlex.quote(best_token)
            cmd = (
                "if command -v rg >/dev/null 2>&1; then "
                f"rg --no-heading -n -F {quoted} {shlex.quote(best_path)} | head -n 1; "
                "else "
                f"grep -n -F -m 1 -e {quoted} {shlex.quote(best_path)}; "
                "fi"
            )
            match_line = (await sandbox.run_cmd(cmd) or "").strip()
            parsed_lines = _parse_search_lines(match_line)
            if parsed_lines:
                _, line_no = parsed_lines[0]
        except Exception:
            line_no = 1

        return best_path, line_no, best_token

    for change_index, change in indexed_changes:
        if len(hints) >= max_hints:
            break
        ctx = change.elementContext
        if ctx:
            react_hint = await _hint_from_react_source(ctx)
            if react_hint:
                hints[change_index] = react_hint
                continue

        queries = _extract_source_search_queries(change)
        query_used: Optional[str] = None
        matches: List[tuple[str, int]] = []
        for query in queries:
            candidate = query.strip()
            if len(candidate) < 3:
                continue
            if len(candidate) > 120:
                candidate = candidate[:120]

            if candidate in seen_queries:
                hints[change_index] = seen_queries[candidate]
                query_used = candidate
                break

            candidate_matches = _parse_search_lines(await _search_workspace(candidate))
            if candidate_matches:
                query_used = candidate
                matches = candidate_matches
                break

        if not hints.get(change_index) and matches:
            matches.sort(key=lambda item: _score_path(item[0]))
            file_path, line_no = matches[0]
            snippet = await _read_snippet(
                file_path=file_path, line_no=line_no, query=query_used
            )
            if snippet:
                hints[change_index] = snippet
                if query_used:
                    seen_queries[query_used] = snippet
                continue

        # Last resort for non-text elements: try class tokens to find a likely source file.
        if ctx and not hints.get(change_index):
            tokens = _extract_class_tokens(ctx)
            best = await _best_file_by_class_tokens(tokens)
            if best:
                file_path, line_no, token = best
                snippet = await _read_snippet(
                    file_path=file_path, line_no=line_no, query=f"classToken: {token}"
                )
                if snippet:
                    hints[change_index] = snippet

    return hints


def _parse_batch_ai_response(content: str) -> Optional[Dict[int, Dict[str, Any]]]:
    """Parse batch AI response JSON into a change_index -> payload mapping."""
    try:
        if not content or '"changes"' not in content:
            return None

        def _extract_json_object_with_key(
            source: str, key_with_quotes: str
        ) -> Optional[str]:
            if key_with_quotes not in source:
                return None

            length = len(source)
            for start in range(length):
                if source[start] != "{":
                    continue

                depth = 0
                in_string = False
                escaped = False
                for end in range(start, length):
                    ch = source[end]
                    if in_string:
                        if escaped:
                            escaped = False
                        elif ch == "\\":
                            escaped = True
                        elif ch == '"':
                            in_string = False
                        continue

                    if ch == '"':
                        in_string = True
                        continue
                    if ch == "{":
                        depth += 1
                        continue
                    if ch == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = source[start : end + 1]
                            if key_with_quotes in candidate:
                                return candidate
                            break

            return None

        json_blob = _extract_json_object_with_key(content, '"changes"')
        if not json_blob:
            return None

        parsed = json.loads(json_blob)
        if not isinstance(parsed, dict):
            return None

        raw_items = parsed.get("changes")
        if not isinstance(raw_items, list):
            return None

        mapping: Dict[int, Dict[str, Any]] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                continue

            raw_index = item.get("change_index")
            try:
                change_index = int(raw_index)
            except Exception:
                continue

            mapping[change_index] = item

        if not mapping:
            return None

        return mapping

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse AI response JSON: %s", e)
        return None
    except Exception as e:
        logger.error("Error parsing AI response: %s", e, exc_info=True)
        return None


def _parse_batch_ai_text_plan(content: str) -> Optional[Dict[int, Dict[str, Any]]]:
    """
    Best-effort parser for non-JSON model output like:

    **Change 1:**
    File: `/workspace/.../Foo.tsx`
    Old:
    ```tsx
    ...
    ```
    New:
    ```tsx
    ...
    ```
    """
    if not content:
        return None

    header_re = re.compile(r"(?im)^\s*\*{0,2}\s*Change\s+(?P<idx>\d+)\s*\*{0,2}\s*:")
    matches = list(header_re.finditer(content))
    if not matches:
        return None

    mapping: Dict[int, Dict[str, Any]] = {}
    for i, match in enumerate(matches):
        try:
            idx = int(match.group("idx"))
        except Exception:
            continue

        section_start = match.end()
        section_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section = content[section_start:section_end]

        file_path: Optional[str] = None
        file_match = re.search(r"(?im)^\s*File\s*:\s*`?([^`\n]+)`?\s*$", section)
        if file_match:
            file_path = file_match.group(1).strip()
        else:
            path_match = re.search(r"(?im)(/workspace/[^\s`]+)", section)
            if path_match:
                file_path = path_match.group(1).strip()

        modifications: List[Dict[str, str]] = []
        pair_re = re.compile(
            r"(?is)\bOld\s*:\s*```[^\n]*\n(.*?)\n```\s*\bNew\s*:\s*```[^\n]*\n(.*?)\n```"
        )
        for pair in pair_re.finditer(section):
            old_code = pair.group(1)
            new_code = pair.group(2)
            if not old_code or not new_code:
                continue
            modifications.append({"type": "replace", "old": old_code, "new": new_code})

        if file_path and modifications:
            mapping[idx] = {
                "change_index": idx,
                "file_path": file_path,
                "change_type": "unknown",
                "modifications": modifications,
            }

    return mapping or None


def _parse_batch_ai_tool_input(payload: Any) -> Optional[Dict[int, Dict[str, Any]]]:
    """Parse the Design Mode sync plan from a tool call payload."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            logger.error("Tool payload was a string but not valid JSON")
            return None

    if not isinstance(payload, dict):
        logger.error("Tool payload was not an object")
        return None

    raw_items = payload.get("changes")
    if not isinstance(raw_items, list):
        logger.error("Tool payload missing 'changes' list")
        return None

    mapping: Dict[int, Dict[str, Any]] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        raw_index = item.get("change_index")
        try:
            change_index = int(raw_index)
        except Exception:
            continue

        mapping[change_index] = item

    if not mapping:
        logger.error("No valid change entries found in tool payload")
        return None

    return mapping


def _build_line_start_offsets(content: str) -> List[int]:
    offsets = [0]
    if not isinstance(content, str) or not content:
        return offsets
    for i, ch in enumerate(content):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _pos_to_line_number(line_start_offsets: List[int], pos: int) -> int:
    # line numbers are 1-based
    if not line_start_offsets:
        return 1
    return bisect.bisect_right(line_start_offsets, pos)


def _normalize_react_source_file_name(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None

    value = value.split("#", 1)[0].split("?", 1)[0]

    # Handle fileName values that look like URLs.
    if "://" in value:
        try:
            value = urlparse(value).path or value
        except Exception:
            pass

    value = value.replace("\\", "/")

    # Handle webpack style: webpack:///./src/App.tsx
    if value.startswith("webpack://"):
        value = value[len("webpack://") :]

    value = value.lstrip("/")
    if value.startswith("./"):
        value = value[2:]

    # If the path is absolute but not under /workspace, salvage a src-relative suffix.
    # This commonly happens when devtools report an absolute host path.
    if (
        value.startswith("Users/")
        or value.startswith("home/")
        or value.startswith("var/")
    ):
        match = re.search(r"(?P<suffix>src/.*)$", value)
        if match:
            value = match.group("suffix")
        else:
            return None

    if not value:
        return None
    return value


def _upsert_data_design_id_attribute(tag: str, design_id: str) -> Optional[str]:
    if not isinstance(tag, str) or not isinstance(design_id, str) or not design_id:
        return None

    # If a design id already exists, only treat it as a match when it is the same id.
    # If it is a different id, do NOT overwrite (we likely matched the wrong element).
    existing_match = re.search(
        r"\bdata-design-id\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", tag
    )
    if existing_match:
        existing_val = (existing_match.group("val") or "").strip()
        if existing_val == design_id:
            return tag
        return None
    if "data-design-id" in tag:
        # Unknown/unsupported form like data-design-id={...}; do not overwrite.
        return None

    insert_at = None
    if tag.rstrip().endswith("/>"):
        insert_at = tag.rfind("/>")
    else:
        insert_at = tag.rfind(">")
    if insert_at is None or insert_at == -1:
        return None
    insertion = f' data-design-id="{design_id}"'
    return tag[:insert_at] + insertion + tag[insert_at:]


def _find_best_opening_tag_near_source_location(
    *,
    content: str,
    line_no: int,
    column_no: Optional[int],
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(line_no, int) or line_no <= 0:
        return None

    line_offsets = _build_line_start_offsets(content)
    if line_no > len(line_offsets):
        return None

    base_pos = line_offsets[line_no - 1]
    if isinstance(column_no, int) and column_no > 0:
        base_pos = min(len(content) - 1, base_pos + (column_no - 1))

    window_chars = 8000
    window_start = max(0, base_pos - window_chars)
    window_end = min(len(content), base_pos + window_chars)
    window = content[window_start:window_end]

    best: Optional[tuple[int, int, int]] = None  # (score, tag_start, tag_end)
    for m in re.finditer(r"<[A-Za-z][A-Za-z0-9:_-]*", window):
        tag_start = window_start + m.start()
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None:
            continue
        cand_line = _pos_to_line_number(line_offsets, tag_start)
        line_dist = abs(cand_line - line_no)
        pos_dist = abs(tag_start - base_pos)
        score = line_dist * 100_000 + pos_dist
        if best is None or score < best[0]:
            best = (score, tag_start, tag_end)

    if not best:
        return None
    return best[1], best[2]


async def _backfill_design_id_in_source_from_react_source(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    ctx = change.elementContext
    if not ctx or not isinstance(ctx.reactSource, dict):
        return None

    raw_file = ctx.reactSource.get("fileName")
    normalized_file = _normalize_react_source_file_name(raw_file)
    if not normalized_file:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: missing/invalid reactSource.fileName=%r for designId=%s",
            raw_file,
            design_id,
        )
        return None

    normalized_path = _normalize_workspace_file_path(normalized_file)
    if not normalized_path:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: could not normalize reactSource file path %r for designId=%s",
            normalized_file,
            design_id,
        )
        return None

    line_no = None
    try:
        line_no = int(ctx.reactSource.get("lineNumber") or 0) or None
    except Exception:
        line_no = None
    if not line_no:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: missing reactSource.lineNumber for designId=%s",
            design_id,
        )
        return None

    column_no = None
    try:
        column_no = int(ctx.reactSource.get("columnNumber") or 0) or None
    except Exception:
        column_no = None

    try:
        content, resolved_path = await _read_file_with_workspace_fallback(
            sandbox, normalized_path
        )
    except Exception:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Backfill failed: could not read reactSource file %s (from %r) for designId=%s",
            normalized_path,
            raw_file,
            design_id,
        )
        return None

    if not isinstance(content, str) or not content:
        return None

    bounds = _find_best_opening_tag_near_source_location(
        content=content, line_no=line_no, column_no=column_no
    )
    if not bounds:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Backfill failed: could not locate JSX tag near %s:%s for designId=%s",
            resolved_path,
            line_no,
            design_id,
        )
        return None
    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]
    updated_tag = _upsert_data_design_id_attribute(tag, design_id)
    if not updated_tag:
        return None
    if updated_tag == tag:
        return resolved_path, content
    updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]
    return resolved_path, updated_content


async def _backfill_design_id_in_source_from_text_search(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    ctx = change.elementContext
    if not ctx or not isinstance(ctx.textContent, str):
        return None
    text = ctx.textContent.strip()
    if not text or text.upper() == "N/A":
        return None

    query = text[:80]
    search_out = await _search_workspace_for_fixed_string(sandbox, query)
    candidates = _parse_search_paths(search_out)
    if not candidates:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: text query not found in /workspace for designId=%s",
            design_id,
        )
        return None
    best_path = sorted(candidates, key=_score_source_path)[0]

    try:
        content, resolved_path = await _read_file_with_workspace_fallback(
            sandbox, best_path
        )
    except Exception:
        return None

    if not isinstance(content, str) or not content:
        return None

    idx = content.find(query)
    if idx == -1:
        return None

    search_pos = idx
    while True:
        tag_start = content.rfind("<", 0, search_pos + 1)
        if tag_start == -1:
            return None
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            search_pos = tag_start - 1
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None or tag_end >= idx:
            search_pos = tag_start - 1
            continue
        tag = content[tag_start : tag_end + 1]
        updated_tag = _upsert_data_design_id_attribute(tag, design_id)
        if not updated_tag:
            return None
        if updated_tag == tag:
            return resolved_path, content
        updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]
        return resolved_path, updated_content


def _split_class_tokens(class_name: str) -> List[str]:
    if not isinstance(class_name, str):
        return []
    tokens = [t.strip() for t in re.split(r"\s+", class_name.strip()) if t.strip()]
    deduped: List[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def _class_token_distinctiveness(token: str) -> int:
    if not isinstance(token, str):
        return 0
    score = len(token)
    if any(ch in token for ch in "/[]():#%"):
        score += 25
    if any(ch.isdigit() for ch in token):
        score += 6
    if token.startswith("data-") or token.startswith("aria-"):
        score += 12
    return score


def _extract_anchor_snippets(ctx: Optional[ElementContext]) -> List[str]:
    if not ctx:
        return []

    def _split_anchor_candidates(value: str) -> List[str]:
        """
        Turn iframe-captured text (often `innerText`) into source-searchable anchors.

        Important: container elements' `innerText` concatenates descendant texts that are separated
        by tags in source, so we must split into smaller, atomic snippets (lines/sentences).
        """
        if not isinstance(value, str):
            return []
        text = value.strip()
        if not text or text.lower() == "n/a":
            return []

        parts: List[str] = [p.strip() for p in re.split(r"[\r\n]+", text) if p.strip()]
        if not parts:
            parts = [text]

        # If it's still a single long run, also split by sentence-ish boundaries so we can match
        # contiguous substrings that likely exist as literals in source.
        if len(parts) == 1 and len(parts[0]) > 80:
            sentence_parts = [
                p.strip()
                for p in re.split(r"(?<=[.!?])\s+", parts[0])
                if p and p.strip()
            ]
            if len(sentence_parts) > 1:
                parts = sentence_parts

        return parts

    raw_candidates: List[str] = []
    for value in (
        ctx.textContent,
        ctx.nextSiblingText,
        ctx.prevSiblingText,
        ctx.contextText,
    ):
        for part in _split_anchor_candidates(value):
            raw_candidates.append(part[:120])
            if len(raw_candidates) >= 8:
                break
        if len(raw_candidates) >= 8:
            break

    deduped: List[str] = []
    seen: set[str] = set()
    for snippet in raw_candidates:
        if snippet in seen:
            continue
        seen.add(snippet)
        deduped.append(snippet)
    return deduped


def _find_best_opening_tag_by_class_tokens(
    *,
    content: str,
    class_name: str,
    class_tokens: List[str],
    preferred_tag_name: Optional[str],
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(class_name, str) or not class_name.strip():
        return None
    if not isinstance(class_tokens, list) or not class_tokens:
        return None

    normalized_class = " ".join(class_name.split())
    preferred = (preferred_tag_name or "").strip().lower() or None

    best: Optional[tuple[tuple[int, int, int, int, int], int, int]] = None
    for m in re.finditer(r"<[A-Za-z][A-Za-z0-9:_-]*", content):
        tag_start = m.start()
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None:
            continue
        tag = content[tag_start : tag_end + 1]

        if "className" not in tag and "class" not in tag:
            continue

        full_match = 1 if normalized_class and normalized_class in tag else 0
        token_matches = 0
        for token in class_tokens:
            if token and token in tag:
                token_matches += 1

        if full_match == 0 and token_matches < (1 if len(class_tokens) == 1 else 2):
            continue

        tag_name_match = 0
        if preferred:
            name_match = re.match(r"<\s*(?P<name>[A-Za-z][A-Za-z0-9:_-]*)", tag)
            if name_match and (name_match.group("name") or "").lower() == preferred:
                tag_name_match = 1

        # Prefer elements that do NOT already have a data-design-id; we don't want to steal IDs.
        has_existing_id = 1 if "data-design-id" in tag else 0

        score = (
            -full_match,
            -token_matches,
            has_existing_id,
            -tag_name_match,
            tag_start,
        )
        if best is None or score < best[0]:
            best = (score, tag_start, tag_end)

    if not best:
        return None
    return best[1], best[2]


async def _backfill_design_id_in_source_from_class_name(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    ctx = change.elementContext
    if not ctx:
        return None

    class_name = None
    if isinstance(ctx.className, str) and ctx.className.strip():
        class_name = " ".join(ctx.className.split())
    elif isinstance(ctx.outerHTML, str) and ctx.outerHTML:
        match = re.search(
            r"\bclass\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", ctx.outerHTML
        )
        if match and match.group("val").strip():
            class_name = " ".join(match.group("val").strip().split())

    if not class_name:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill (className) skipped: missing className/outerHTML for designId=%s",
            design_id,
        )
        return None

    class_tokens = _split_class_tokens(class_name)
    if not class_tokens:
        return None

    anchors = _extract_anchor_snippets(ctx)

    search_out = await _search_workspace_for_fixed_string(sandbox, class_name)
    candidates = _parse_search_paths(search_out)
    if candidates:
        ranked = sorted(candidates, key=_score_source_path)
        best_path = ranked[0]
        logger.info(
            "[DesignMode Sync] (source-mapping) Backfill (className) exact match: designId=%s files=%d best=%s",
            design_id,
            len(ranked),
            best_path,
        )
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, best_path
            )
        except Exception:
            content = None
            resolved_path = None

        if (
            isinstance(content, str)
            and content
            and isinstance(resolved_path, str)
            and resolved_path
        ):
            bounds = _find_best_opening_tag_by_class_tokens(
                content=content,
                class_name=class_name,
                class_tokens=class_tokens,
                preferred_tag_name=ctx.tagName,
            )
            if bounds:
                tag_start, tag_end = bounds
                tag = content[tag_start : tag_end + 1]
                updated_tag = _upsert_data_design_id_attribute(tag, design_id)
                if updated_tag and updated_tag != tag:
                    return (
                        resolved_path,
                        content[:tag_start] + updated_tag + content[tag_end + 1 :],
                    )
                if updated_tag == tag:
                    return resolved_path, content

    ranked_tokens = sorted(class_tokens, key=_class_token_distinctiveness, reverse=True)
    tokens_to_search = ranked_tokens[: min(8, len(ranked_tokens))]

    file_hits: Dict[str, int] = {}
    for token in tokens_to_search:
        out = await _search_workspace_for_fixed_string(sandbox, token)
        for path in _parse_search_paths(out):
            file_hits[path] = file_hits.get(path, 0) + 1

    if not file_hits:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill (className) failed: no token matches in /workspace for designId=%s",
            design_id,
        )
        return None

    ranked_files = sorted(
        file_hits.items(),
        key=lambda kv: (-kv[1], _score_source_path(kv[0])),
    )

    best_content: Optional[str] = None
    best_path: Optional[str] = None
    best_anchor_hits = -1
    best_token_hits = -1

    for path, token_hit_count in ranked_files[:5]:
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, path
            )
        except Exception:
            continue
        if not isinstance(content, str) or not content:
            continue

        anchor_hits = 0
        for anchor in anchors:
            if anchor and anchor in content:
                anchor_hits += 1

        if (
            anchor_hits > best_anchor_hits
            or (anchor_hits == best_anchor_hits and token_hit_count > best_token_hits)
            or (
                anchor_hits == best_anchor_hits
                and token_hit_count == best_token_hits
                and best_path
                and _score_source_path(resolved_path) < _score_source_path(best_path)
            )
        ):
            best_content = content
            best_path = resolved_path
            best_anchor_hits = anchor_hits
            best_token_hits = token_hit_count

    if not best_content or not best_path:
        return None

    logger.info(
        "[DesignMode Sync] (source-mapping) Backfill (className) candidate: designId=%s file=%s tokens=%d anchors=%d",
        design_id,
        best_path,
        best_token_hits,
        best_anchor_hits,
    )

    bounds = _find_best_opening_tag_by_class_tokens(
        content=best_content,
        class_name=class_name,
        class_tokens=class_tokens,
        preferred_tag_name=ctx.tagName,
    )
    if not bounds:
        return None
    tag_start, tag_end = bounds
    tag = best_content[tag_start : tag_end + 1]
    updated_tag = _upsert_data_design_id_attribute(tag, design_id)
    if not updated_tag:
        return None
    if updated_tag == tag:
        return best_path, best_content
    return (
        best_path,
        best_content[:tag_start] + updated_tag + best_content[tag_end + 1 :],
    )


def _infer_component_name_before_index(content: str, index: int) -> Optional[str]:
    """
    Best-effort: infer the nearest React component name defined above `index`.

    This is used when a runtime element's className is defined inside a reusable component
    (e.g., shadcn/ui `CardHeader`), but the callsite doesn't include the className literal.
    """
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(index, int) or index <= 0:
        return None

    window_start = max(0, index - 3000)
    window = content[window_start:index]

    patterns = (
        r"(?:export\s+)?const\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*React\.forwardRef",
        r"(?:export\s+)?const\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*forwardRef",
        r"(?:export\s+)?function\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
    )

    candidates: List[tuple[int, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, window):
            name = (match.group("name") or "").strip()
            if not name:
                continue
            candidates.append((match.start(), name))

    if not candidates:
        return None
    # Choose the nearest definition above index.
    return max(candidates, key=lambda t: t[0])[1]


def _find_best_component_callsite_opening_tag(
    *,
    content: str,
    component_name: str,
    anchors: List[str],
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(component_name, str) or not component_name:
        return None

    normalized_anchors = [
        _normalize_whitespace_for_match(a) for a in anchors if isinstance(a, str) and a
    ]
    normalized_anchors = [a for a in normalized_anchors if a]
    if not normalized_anchors:
        return None

    # Match `<Component ...` with a word-ish boundary afterwards.
    pattern = re.compile(r"<\s*" + re.escape(component_name) + r"(?![A-Za-z0-9:_.-])")

    best: Optional[tuple[int, int, int]] = None  # (-anchor_hits, has_id, tag_start)
    best_bounds: Optional[tuple[int, int]] = None

    for match in pattern.finditer(content):
        tag_start = match.start()
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None:
            continue
        tag = content[tag_start : tag_end + 1]

        span_start = tag_start
        span_end = tag_end + 1
        if not tag.rstrip().endswith("/>"):
            closing_end = _find_matching_closing_tag_end(
                content, tag_end + 1, component_name
            )
            if closing_end is None:
                continue
            span_end = closing_end + 1

        window = _normalize_whitespace_for_match(content[span_start:span_end])
        anchor_hits = 0
        for anchor in normalized_anchors:
            if anchor in window:
                anchor_hits += 1

        if anchor_hits <= 0:
            continue

        has_existing_id = 1 if "data-design-id" in tag else 0
        score = (-anchor_hits, has_existing_id, tag_start)
        if best is None or score < best:
            best = score
            best_bounds = (tag_start, tag_end)

    return best_bounds


async def _backfill_design_id_in_source_from_component_callsite(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    """
    Backfill `data-design-id` into a React component callsite when the runtime element's className
    comes from a reusable component definition (so the className literal isn't present at the callsite).

    Example: `CardHeader` renders a `<div className="flex flex-col ...">` internally. We infer the
    component name from the className definition file, then locate the correct callsite by anchor text.
    """
    ctx = change.elementContext
    if not ctx:
        return None

    class_name = None
    if isinstance(ctx.className, str) and ctx.className.strip():
        class_name = " ".join(ctx.className.split())
    elif isinstance(ctx.outerHTML, str) and ctx.outerHTML:
        match = re.search(
            r"\bclass\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", ctx.outerHTML
        )
        if match and match.group("val").strip():
            class_name = " ".join(match.group("val").strip().split())

    anchors = _extract_anchor_snippets(ctx)
    if not class_name or not anchors:
        return None

    # 1) Find definition files that contain the className literal.
    search_out = await _search_workspace_for_fixed_string(sandbox, class_name)
    definition_paths = sorted(_parse_search_paths(search_out), key=_score_source_path)
    if not definition_paths:
        return None

    component_names: List[str] = []
    for def_path in definition_paths[:5]:
        try:
            definition_content, _resolved_def_path = (
                await _read_file_with_workspace_fallback(sandbox, def_path)
            )
        except Exception:
            continue
        if not isinstance(definition_content, str) or not definition_content:
            continue

        for match in re.finditer(re.escape(class_name), definition_content):
            inferred = _infer_component_name_before_index(
                definition_content, match.start()
            )
            if inferred and inferred not in component_names:
                component_names.append(inferred)
        if component_names:
            break

    if not component_names:
        return None

    # 2) Use anchor snippets to find the callsite file (where text literals exist).
    anchor_queries = sorted(anchors, key=lambda s: (-len(s or ""), s or ""))[:3]
    callsite_candidates: List[str] = []
    for anchor in anchor_queries:
        out = await _search_workspace_for_fixed_string(sandbox, anchor)
        callsite_candidates.extend(_parse_search_paths(out))

    # De-dupe while preserving order, then rank.
    deduped: List[str] = []
    seen: set[str] = set()
    for p in callsite_candidates:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    ranked_callsite_paths = sorted(deduped, key=_score_source_path)
    for path in ranked_callsite_paths[:8]:
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, path
            )
        except Exception:
            continue
        if not isinstance(content, str) or not content or not resolved_path:
            continue

        for component_name in component_names:
            if f"<{component_name}" not in content:
                continue
            bounds = _find_best_component_callsite_opening_tag(
                content=content, component_name=component_name, anchors=anchor_queries
            )
            if not bounds:
                continue
            tag_start, tag_end = bounds
            tag = content[tag_start : tag_end + 1]
            updated_tag = _upsert_data_design_id_attribute(tag, design_id)
            if not updated_tag:
                continue
            if updated_tag == tag:
                return resolved_path, content
            updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]
            logger.info(
                "[DesignMode Sync] (source-mapping) Backfill (callsite) inferred component=%s file=%s designId=%s",
                component_name,
                resolved_path,
                design_id,
            )
            return resolved_path, updated_content

    return None


def _css_property_to_jsx_style_key(property_name: str) -> str:
    """Convert a CSS kebab-case property to a JSX style object key."""
    if not isinstance(property_name, str):
        return ""
    value = property_name.strip()
    if not value:
        return ""
    if value.startswith("--"):
        # Custom property: not directly supported as a JSX style key, but keep as-is.
        return value
    parts = [p for p in re.split(r"[-_]+", value) if p]
    if not parts:
        return value
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _escape_js_string_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _upsert_html_style_declaration(
    style_value: str, css_prop: str, css_value: str
) -> str:
    declarations: Dict[str, str] = {}
    order: List[str] = []

    for part in (style_value or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            continue
        key, val = part.split(":", 1)
        key = key.strip()
        if not key:
            continue
        if key not in declarations:
            order.append(key)
        declarations[key] = val.strip()

    css_prop = (css_prop or "").strip()
    if not css_prop:
        return style_value

    css_value = "" if css_value is None else str(css_value)

    if css_value == "":
        declarations.pop(css_prop, None)
        if css_prop in order:
            order = [k for k in order if k != css_prop]
    else:
        if css_prop not in declarations:
            order.append(css_prop)
        declarations[css_prop] = css_value

    if not order:
        return ""

    rebuilt = "; ".join(f"{k}: {declarations[k]}" for k in order if k in declarations)
    return rebuilt + ";"


def _find_tag_end(text: str, start_index: int) -> Optional[int]:
    quote: Optional[str] = None
    brace_depth = 0
    i = start_index
    while i < len(text):
        ch = text[i]
        if quote is not None:
            if ch == quote and (i == 0 or text[i - 1] != "\\"):
                quote = None
        else:
            if ch in {"'", '"'}:
                quote = ch
            elif ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth = max(0, brace_depth - 1)
            elif ch == ">" and brace_depth == 0:
                return i
        i += 1
    return None


def _find_opening_tag_bounds_for_design_id(
    content: str, design_id: str
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not isinstance(design_id, str) or not design_id:
        return None

    needles = [f'data-design-id="{design_id}"', f"data-design-id='{design_id}'"]
    match_index = -1
    for needle in needles:
        match_index = content.find(needle)
        if match_index != -1:
            break
    if match_index == -1:
        return None

    search_pos = match_index
    while True:
        tag_start = content.rfind("<", 0, search_pos + 1)
        if tag_start == -1:
            return None
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            search_pos = tag_start - 1
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None or match_index > tag_end:
            search_pos = tag_start - 1
            continue
        return tag_start, tag_end


def _normalize_whitespace_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _extract_opening_tag_name(tag: str) -> Optional[str]:
    if not isinstance(tag, str) or not tag:
        return None
    match = re.match(r"<\s*(?P<name>[A-Za-z][A-Za-z0-9:_.-]*)", tag)
    if not match:
        return None
    return (match.group("name") or "").strip() or None


_DESIGN_MODE_HTML_TAG_NAMES: set[str] = {
    "a",
    "article",
    "aside",
    "button",
    "div",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "img",
    "input",
    "label",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "section",
    "select",
    "span",
    "textarea",
    "ul",
}


def _is_html_tag_name_for_design_mode(value: str) -> bool:
    return (value or "").strip().lower() in _DESIGN_MODE_HTML_TAG_NAMES


def _extract_literal_class_attr_from_tag(tag: str) -> Optional[str]:
    if not isinstance(tag, str) or not tag:
        return None
    for attr in ("className", "class"):
        match = re.search(
            rf"(?<![\w-]){attr}\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)",
            tag,
            re.DOTALL,
        )
        if match:
            value = (match.group("val") or "").strip()
            if value:
                return value
    return None


def _extract_class_attr_from_outer_html(outer_html: Any) -> Optional[str]:
    if not isinstance(outer_html, str) or not outer_html:
        return None
    match = re.search(
        r"(?<![\w-])class\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)",
        outer_html,
        re.DOTALL,
    )
    if not match:
        return None
    value = (match.group("val") or "").strip()
    return value or None


def _verify_design_mode_target_matches_context(
    *,
    change: StyleChange,
    content: str,
    file_path: str,
    design_id: str,
) -> tuple[bool, str]:
    """
    Best-effort guardrail to prevent applying a change to the wrong source element.

    We verify that the source tag we located via `data-design-id="..."` matches the
    element context captured in the iframe (tagName, nearby text anchors, class tokens).
    """
    ctx = change.elementContext
    if not ctx:
        return True, "no_context"

    bounds = _find_opening_tag_bounds_for_design_id(content, design_id)
    if not bounds:
        return True, "tag_not_found"

    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]

    expected_tag = (getattr(ctx, "tagName", None) or "").strip().lower()
    source_tag = (_extract_opening_tag_name(tag) or "").strip()
    if expected_tag and source_tag:
        # Only enforce tag name match when the source tag is a real HTML tag.
        # In TSX/JSX, design IDs may live on React components (e.g. <Button ...>, <motion.h1 ...>),
        # which render to lowercase DOM tags at runtime.
        if (
            _is_html_tag_name_for_design_mode(source_tag)
            and source_tag.lower() != expected_tag
        ):
            return False, f"tag_name_mismatch expected={expected_tag} got={source_tag}"

    anchors = _extract_anchor_snippets(ctx)
    if anchors:
        window_start = max(0, tag_start - 4000)
        window_end = min(len(content), tag_end + 1 + 12000)
        window = _normalize_whitespace_for_match(content[window_start:window_end])
        found_anchor = False
        for anchor in anchors:
            normalized_anchor = _normalize_whitespace_for_match(anchor)
            if normalized_anchor and normalized_anchor in window:
                found_anchor = True
                break
        if not found_anchor:
            return False, "anchor_text_mismatch"

    expected_class_name = (getattr(ctx, "className", None) or "").strip()
    if not expected_class_name:
        expected_class_name = (
            _extract_class_attr_from_outer_html(getattr(ctx, "outerHTML", None)) or ""
        )

    expected_tokens = (
        _split_class_tokens(expected_class_name) if expected_class_name else []
    )
    source_class_literal = _extract_literal_class_attr_from_tag(tag)
    if expected_tokens and source_class_literal:
        source_tokens = set(_split_class_tokens(source_class_literal))
        overlap = len(set(expected_tokens) & source_tokens)

        # If we have anchors, class mismatch is not fatal (text already disambiguates).
        if not anchors:
            min_overlap = 1 if len(expected_tokens) <= 2 else 2
            if overlap < min_overlap:
                return (
                    False,
                    f"class_token_mismatch overlap={overlap} min={min_overlap}",
                )

    return True, "ok"


def _upsert_jsx_style_attribute(
    tag: str, css_prop: str, css_value: str
) -> Optional[str]:
    if not isinstance(tag, str):
        return None

    style_key = _css_property_to_jsx_style_key(css_prop)
    if not style_key:
        return None

    css_value = "" if css_value is None else str(css_value)
    if css_value == "":
        value_literal = "undefined"
    else:
        value_literal = f"'{_escape_js_string_literal(css_value)}'"

    def _extract_kv_pairs(expr: str) -> List[tuple[str, str]]:
        pairs: List[tuple[str, str]] = []
        if not isinstance(expr, str) or not expr:
            return pairs
        pattern = re.compile(
            r"\b(?P<key>[A-Za-z_$][A-Za-z0-9_$]*)\s*:\s*(?P<val>undefined|'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\")"
        )
        for match in pattern.finditer(expr):
            key = match.group("key")
            val = match.group("val")
            if not key or not val:
                continue
            pairs.append((key, val))
        return pairs

    def _find_jsx_style_attr_ranges() -> List[tuple[int, int, str]]:
        """
        Return a list of (attr_start, attr_end, expression) for each `style={...}` in this tag.

        attr_start points to the `s` in `style`, and attr_end is the index *after* the closing `}`
        of the JSX expression.
        """
        ranges: List[tuple[int, int, str]] = []
        for match in re.finditer(r"(?<![\w-])style\s*=", tag):
            attr_start = match.start()
            eq_index = tag.find("=", match.end() - 1)
            if eq_index == -1:
                continue
            value_start = eq_index + 1
            while value_start < len(tag) and tag[value_start].isspace():
                value_start += 1
            if value_start >= len(tag) or tag[value_start] != "{":
                continue

            quote: Optional[str] = None
            depth = 0
            i = value_start
            while i < len(tag):
                ch = tag[i]
                if quote is not None:
                    if ch == quote and tag[i - 1] != "\\":
                        quote = None
                else:
                    if ch in {"'", '"'}:
                        quote = ch
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            break
                i += 1
            if depth != 0:
                continue

            value_end = i
            expression = tag[value_start + 1 : value_end].strip()
            ranges.append((attr_start, value_end + 1, expression))
        return ranges

    style_ranges = _find_jsx_style_attr_ranges()
    if not style_ranges:
        insert_at = None
        if tag.rstrip().endswith("/>"):
            insert_at = tag.rfind("/>")
        else:
            insert_at = tag.rfind(">")
        if insert_at is None or insert_at == -1:
            return None
        insertion = " style={{ " + style_key + ": " + value_literal + " }}"
        return tag[:insert_at] + insertion + tag[insert_at:]

    # Merge multiple `style={...}` attributes into one to avoid JSX prop overriding.
    spread_parts: List[str] = []
    kv_parts: List[str] = []

    for _start, _end, expr in style_ranges:
        if not isinstance(expr, str):
            continue
        trimmed = expr.strip()
        if not trimmed:
            continue

        # Normal/expected: object literal or expression.
        if trimmed.startswith("{") and trimmed.endswith("}"):
            spread_parts.append(f"...({trimmed})")
            continue

        # Repair corrupted expressions produced by earlier buggy syncs, e.g. when we accidentally wrote
        # `style={ ...({foo: 'bar'}), baz: 'qux' }` (missing the inner braces for an object literal).
        #
        # If an expression contains key/value pairs but isn't wrapped in `{...}`, extract the pairs
        # rather than attempting to spread an invalid expression containing `...`.
        if ":" in trimmed:
            extracted = _extract_kv_pairs(trimmed)
            if extracted:
                kv_parts.extend([f"{k}: {v}" for (k, v) in extracted])
                continue

        spread_parts.append(f"...({trimmed})")

    merged_inner = ", ".join(
        spread_parts + kv_parts + [f"{style_key}: {value_literal}"]
    )
    new_attr = f"style={{{{ {merged_inner} }}}}"

    # Remove all but the first style attribute.
    new_tag = tag
    for start, end, _expr in reversed(style_ranges[1:]):
        # Remove a preceding space if present to avoid leaving double spaces.
        if start > 0 and new_tag[start - 1].isspace():
            start -= 1
        new_tag = new_tag[:start] + new_tag[end:]

    first_start, first_end, _first_expr = style_ranges[0]
    return new_tag[:first_start] + new_attr + new_tag[first_end:]


def _upsert_html_style_attribute(
    tag: str, css_prop: str, css_value: str
) -> Optional[str]:
    if not isinstance(tag, str):
        return None
    match = re.search(
        r"(?<![\w-])style\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", tag, re.DOTALL
    )
    if not match:
        insert_at = None
        if tag.rstrip().endswith("/>"):
            insert_at = tag.rfind("/>")
        else:
            insert_at = tag.rfind(">")
        if insert_at is None or insert_at == -1:
            return None
        css_prop = (css_prop or "").strip()
        css_value = "" if css_value is None else str(css_value)
        if not css_prop or css_value == "":
            return tag
        insertion = f' style="{css_prop}: {css_value};"'
        return tag[:insert_at] + insertion + tag[insert_at:]

    existing = match.group("val")
    updated = _upsert_html_style_declaration(
        existing, css_prop, "" if css_value is None else str(css_value)
    )
    if updated == "":
        # Drop the style attribute entirely when no declarations remain.
        return tag[: match.start()] + tag[match.end() :]
    return tag[: match.start("val")] + updated + tag[match.end("val") :]


def _apply_style_change_by_design_id(
    *,
    content: str,
    file_path: str,
    design_id: str,
    css_prop: str,
    css_value: str,
) -> tuple[str, bool]:
    bounds = _find_opening_tag_bounds_for_design_id(content, design_id)
    if not bounds:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate tag for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False
    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]

    ext = (posixpath.splitext(file_path or "")[1] or "").lower()
    is_html = ext in {".html", ".htm"}

    updated_tag: Optional[str]
    if is_html:
        updated_tag = _upsert_html_style_attribute(tag, css_prop, css_value)
    else:
        updated_tag = _upsert_jsx_style_attribute(tag, css_prop, css_value)

    if not updated_tag:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not update style for designId=%s css=%s in %s; tag=%s",
            design_id,
            css_prop,
            file_path,
            _truncate_for_log(tag, limit=400),
        )
        return content, False
    if updated_tag == tag:
        # Treat already-in-sync as success.
        return content, True
    return content[:tag_start] + updated_tag + content[tag_end + 1 :], True


_DESIGN_MODE_CSS_OVERRIDES_START = "/* === Design Mode Overrides (ii-agent) === */"
_DESIGN_MODE_CSS_OVERRIDES_END = "/* === End Design Mode Overrides === */"


def _escape_css_attribute_value(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def _upsert_design_mode_css_override(
    *, css_text: str, design_id: str, css_prop: str, css_value: str
) -> str:
    if not isinstance(css_text, str):
        css_text = ""
    css_prop = (css_prop or "").strip()
    if not css_prop:
        return css_text

    selector = f'[data-design-id="{_escape_css_attribute_value(design_id)}"]'
    value = "" if css_value is None else str(css_value).strip()

    def _upsert_rule(section: str) -> str:
        pattern = re.compile(rf"(?s){re.escape(selector)}\s*\{{(?P<body>.*?)\}}\s*")
        match = pattern.search(section)

        if not match:
            if not value:
                return section
            block = f"{selector} {{\n  {css_prop}: {value};\n}}\n"
            section = section.rstrip() + ("\n\n" if section.strip() else "")
            return section + block

        body = match.group("body") or ""
        prop_line = re.compile(
            rf"(?m)^(?P<indent>\s*){re.escape(css_prop)}\s*:\s*[^;]*;\s*$"
        )

        if not value:
            new_body = prop_line.sub("", body)
        elif prop_line.search(body):
            new_body = prop_line.sub(rf"\g<indent>{css_prop}: {value};", body, count=1)
        else:
            indent_match = re.search(
                r"(?m)^(?P<indent>\s*)[A-Za-z_-][A-Za-z0-9_-]*\s*:", body
            )
            indent = indent_match.group("indent") if indent_match else "  "
            trimmed = body.rstrip("\n")
            if trimmed.strip():
                trimmed = trimmed + "\n"
            new_body = f"{trimmed}{indent}{css_prop}: {value};\n"

        # If no declarations remain, drop the whole block.
        if not re.search(r"(?m)^\s*[A-Za-z_-][A-Za-z0-9_-]*\s*:", new_body or ""):
            start, end = match.span()
            updated = section[:start] + section[end:]
            return updated.rstrip() + ("\n" if updated.strip() else "")

        rebuilt_block = f"{selector} {{\n{new_body.rstrip()}\n}}\n"
        start, end = match.span()
        return section[:start] + rebuilt_block + section[end:]

    start = css_text.find(_DESIGN_MODE_CSS_OVERRIDES_START)
    end = css_text.find(_DESIGN_MODE_CSS_OVERRIDES_END)
    has_section = start != -1 and end != -1 and end > start

    if not has_section:
        section = _upsert_rule("")
        rebuilt = css_text.rstrip()
        if rebuilt:
            rebuilt += "\n\n"
        rebuilt += (
            f"{_DESIGN_MODE_CSS_OVERRIDES_START}\n"
            f"{section.rstrip()}\n"
            f"{_DESIGN_MODE_CSS_OVERRIDES_END}\n"
        )
        return rebuilt

    section_start = start + len(_DESIGN_MODE_CSS_OVERRIDES_START)
    section_body = css_text[section_start:end].strip("\n")
    updated_section = _upsert_rule(section_body)
    return (
        css_text[:section_start]
        + "\n"
        + updated_section.strip("\n")
        + "\n"
        + css_text[end:]
    )


def _score_globals_css_candidate(path: str) -> int:
    lowered = (path or "").lower()
    if lowered.endswith("/src/app/globals.css"):
        return 0
    if lowered.endswith("/app/globals.css"):
        return 1
    if lowered.endswith("/src/styles/globals.css"):
        return 2
    if lowered.endswith("/styles/globals.css"):
        return 3
    return 9


async def _locate_project_globals_css(
    *, sandbox: Any, manifest_path: Optional[str]
) -> Optional[str]:
    cache_key = "design_mode_globals_css_paths"
    cached = getattr(sandbox, cache_key, None)
    if not isinstance(cached, dict):
        cached = {}
        try:
            setattr(sandbox, cache_key, cached)
        except Exception:
            cached = {}

    project_root = (
        posixpath.dirname(manifest_path)
        if isinstance(manifest_path, str) and manifest_path.startswith("/workspace/")
        else None
    )
    cache_bucket = project_root or "/workspace"
    cached_path = cached.get(cache_bucket)
    if isinstance(cached_path, str) and cached_path.startswith("/workspace/"):
        return cached_path

    search_root = project_root or "/workspace"
    find_cmd = (
        f"find {shlex.quote(search_root)} -type f -name globals.css "
        "-not -path '*/node_modules/*' "
        "-not -path '*/.git/*' "
        "-not -path '*/dist/*' "
        "-not -path '*/build/*' "
        "-not -path '*/.next/*' "
        "-print"
    )
    try:
        out = await sandbox.run_cmd(find_cmd)
    except Exception:
        out = ""
    candidates = [line.strip() for line in (out or "").splitlines() if line.strip()]
    if not candidates and project_root:
        # Last resort: search across all of /workspace.
        try:
            out = await sandbox.run_cmd(find_cmd.replace(search_root, "/workspace", 1))
        except Exception:
            out = ""
        candidates = [line.strip() for line in (out or "").splitlines() if line.strip()]
    if not candidates:
        return None

    candidates.sort(key=lambda p: (_score_globals_css_candidate(p), len(p)))
    best = candidates[0]
    cached[cache_bucket] = best
    return best


async def _apply_style_change_as_css_override(
    *,
    sandbox: Any,
    manifest_path: Optional[str],
    design_id: str,
    css_prop: str,
    css_value: str,
) -> tuple[bool, Optional[str]]:
    globals_css_path = await _locate_project_globals_css(
        sandbox=sandbox, manifest_path=manifest_path
    )
    if not globals_css_path:
        return False, None

    try:
        current_css = await sandbox.read_file(globals_css_path)
    except Exception:
        return False, None
    if not isinstance(current_css, str):
        try:
            current_css = str(current_css)
        except Exception:
            return False, None

    updated_css = _upsert_design_mode_css_override(
        css_text=current_css,
        design_id=design_id,
        css_prop=css_prop,
        css_value=css_value,
    )
    if updated_css == current_css:
        return True, globals_css_path

    try:
        ok = await sandbox.write_file(updated_css, globals_css_path)
        return bool(ok), globals_css_path
    except Exception:
        return False, None


def _apply_text_change_by_design_id(
    *,
    content: str,
    file_path: str,
    design_id: str,
    old_text: str,
    new_text: str,
) -> tuple[str, bool]:
    bounds = _find_opening_tag_bounds_for_design_id(content, design_id)
    if not bounds:
        return content, False
    tag_start, tag_end = bounds

    if not old_text:
        return content, False

    window_start = tag_end + 1
    window_end = min(len(content), window_start + 6000)
    window = content[window_start:window_end]
    if old_text not in window:
        # Treat already-in-sync as success if the new text is present.
        if new_text and new_text in window:
            return content, True
        return content, False
    window = window.replace(old_text, new_text, 1)
    return content[:window_start] + window + content[window_end:], True


def _normalize_lucide_icon_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    value = value.replace("_", "-").replace(" ", "-")
    value = re.sub(r"[^a-zA-Z0-9-]+", "", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value.lower()


def _lucide_icon_name_to_component_name(icon_name: str) -> Optional[str]:
    if not isinstance(icon_name, str):
        return None
    raw = icon_name.strip()
    if not raw:
        return None

    # Already a valid component identifier like "BrickWall" or "CheckCircle2".
    if re.fullmatch(r"[A-Z][A-Za-z0-9]*", raw):
        return raw

    normalized = _normalize_lucide_icon_name(raw)
    if not normalized:
        return None
    parts = [p for p in normalized.split("-") if p]
    if not parts:
        return None
    component = "".join(p[:1].upper() + p[1:] for p in parts)
    if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", component):
        return None
    return component


def _infer_design_id_pattern(design_id: str) -> Optional[str]:
    """
    Convert a specific design ID to a regex pattern for finding similar IDs.

    Examples:
      features-card-1-icon -> features-card-\\d+-icon
      pricing-tier-pro-icon -> pricing-tier-\\w+-icon
      feature-icon-abc123 -> feature-icon-\\w+

    This helps find template-generated design IDs in source code.
    """
    if not isinstance(design_id, str) or not design_id.strip():
        return None

    # Replace sequences of digits with \d+
    # Replace sequences of word chars (letters/numbers) with \w+
    pattern = design_id

    # First, replace digit sequences
    pattern = re.sub(r"\d+", r"\\d+", pattern)

    # Then, replace word sequences that aren't already part of a \d+ replacement
    # Look for standalone alphanumeric segments (not already in regex form)
    parts = pattern.split("-")
    new_parts = []
    for part in parts:
        if part and not part.startswith("\\") and re.match(r"^[a-zA-Z]\w*$", part):
            # This is a word segment that might be dynamic
            # Keep common prefixes like "icon", "card", "item" as-is
            if part.lower() in (
                "icon",
                "card",
                "item",
                "feature",
                "features",
                "pricing",
                "tier",
            ):
                new_parts.append(part)
            else:
                # Replace with pattern for variable content
                new_parts.append(r"\w+")
        else:
            new_parts.append(part)

    pattern = "-".join(new_parts)
    return pattern


async def _find_icon_by_dynamic_pattern(
    *, sandbox: Any, design_id: str, icon_name: str, element_context: Any
) -> tuple[Optional[str], bool]:
    """
    General solution for finding and updating icons with dynamically generated design IDs.

    Strategy:
    1. Infer a pattern from the design ID (e.g., features-card-1-icon -> features-card-\d+-icon)
    2. Search for this pattern in template strings in the codebase
    3. Find the JSX where this pattern is used
    4. Locate the data array being mapped
    5. Determine the position/index from the design ID
    6. Update the icon at that position in the array

    Args:
        sandbox: Sandbox instance
        design_id: The dynamic design ID (e.g., "features-card-1-icon")
        icon_name: The new icon name to apply
        element_context: Element context with metadata

    Returns:
        (updated_content, success) tuple, or (None, False) if not applicable
    """
    if not design_id or not icon_name:
        return None, False

    # Infer pattern from design ID
    pattern = _infer_design_id_pattern(design_id)
    if not pattern:
        return None, False

    logger.info(
        "[DesignMode Sync] (dynamic-pattern) Searching for pattern: %s (from designId=%s)",
        pattern,
        design_id,
    )

    # Search for files containing template string patterns that might match
    # Look for common template literal markers
    search_queries = [
        "`${",  # Template literal with interpolation
        "data-design-id={`",  # React template literal in JSX
    ]

    all_candidates = []
    for query in search_queries:
        output = await _search_workspace_for_fixed_string(sandbox, query)
        candidates = _parse_search_paths(output)
        all_candidates.extend(candidates)

    if not all_candidates:
        return None, False

    # Deduplicate and rank
    unique_candidates = list(dict.fromkeys(all_candidates))
    ranked = sorted(unique_candidates, key=_score_source_path)

    # Try to find and apply the change in each candidate file
    for candidate_path in ranked[:15]:
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, candidate_path
            )
        except Exception:
            continue

        if not isinstance(content, str) or not content:
            continue

        # Try to apply the change using pattern-based matching
        updated_content, success = _apply_icon_change_by_dynamic_pattern(
            content=content,
            file_path=resolved_path,
            design_id=design_id,
            pattern=pattern,
            icon_name=icon_name,
        )

        if success:
            # Write the updated content
            try:
                ok = await sandbox.write_file(updated_content, resolved_path)
                if ok:
                    logger.info(
                        "[DesignMode Sync] (dynamic-pattern) Successfully applied icon change in %s",
                        resolved_path,
                    )
                    return updated_content, True
            except Exception as exc:
                logger.warning(
                    "[DesignMode Sync] (dynamic-pattern) Failed to write %s: %s",
                    resolved_path,
                    exc,
                )
                continue

    return None, False


def _apply_icon_change_by_dynamic_pattern(
    *, content: str, file_path: str, design_id: str, pattern: str, icon_name: str
) -> tuple[str, bool]:
    """
    Apply icon change by finding the array element at the inferred position.

    This handles cases where design IDs are generated like:
      data-design-id={`features-card-${feature.id}-icon`}
      data-design-id={`item-${index}-icon`}

    Strategy:
    1. Find where the pattern is used in a template string
    2. Extract the variable name being mapped (e.g., "feature", "item")
    3. Find the array being mapped over
    4. Determine the index from the design ID
    5. Update the icon field in that array element
    """
    if not content or not design_id or not pattern or not icon_name:
        return content, False

    new_icon_component = _lucide_icon_name_to_component_name(icon_name)
    if not new_icon_component:
        return content, False

    # Look for template strings that match our pattern
    # Example: data-design-id={`features-card-${feature.id}-icon`}
    template_pattern = re.compile(r"data-design-id=\{`([^`]*\$\{[^}]+\}[^`]*)`\}")

    matches = list(template_pattern.finditer(content))
    if not matches:
        return content, False

    # Try to find a match that could generate our design_id
    for match in matches:
        template = match.group(1)

        # Extract the static parts and variable parts
        # E.g., "features-card-${feature.id}-icon" -> ["features-card-", "feature.id", "-icon"]
        parts = re.split(r"\$\{([^}]+)\}", template)

        if len(parts) < 2:
            continue

        # Try to reconstruct the pattern to see if it matches our design_id
        # Replace ${...} with regex patterns
        test_pattern = re.escape(parts[0])
        for i in range(1, len(parts), 2):
            if i < len(parts):
                # Variable part - use flexible matching
                test_pattern += r"[\w-]+"
            if i + 1 < len(parts):
                # Static part
                test_pattern += re.escape(parts[i + 1])

        if not re.match(f"^{test_pattern}$", design_id):
            continue

        # This template could generate our design_id!
        # Now extract the variable expression (e.g., "feature.id", "index", "item.idx")
        variable_expr = parts[1] if len(parts) > 1 else None
        if not variable_expr:
            continue

        # Determine what value this variable should have for our design_id
        # Extract the actual value from design_id using the pattern
        value_pattern = re.escape(parts[0]) + r"([\w-]+)"
        if len(parts) > 2:
            value_pattern += re.escape(parts[2])

        value_match = re.match(value_pattern, design_id)
        if not value_match:
            continue

        target_value = value_match.group(1)

        # Find the context around this template string to locate the array
        # Look backwards for .map( or similar patterns
        context_start = max(0, match.start() - 1000)
        context = content[context_start : match.end() + 500]

        # Find array.map((item, index) => pattern
        map_pattern = re.compile(
            r"(\[[\s\S]*?\])\.map\s*\(\s*\(([^,)]+)(?:,\s*([^)]+))?\)\s*=>"
        )
        map_match = map_pattern.search(context)

        if not map_match:
            continue

        # Extract the iterator variable name (e.g., "feature", "item")
        iterator_var = map_match.group(2).strip()
        index_var = map_match.group(3).strip() if map_match.group(3) else None

        # Check if our variable expression uses this iterator
        if iterator_var not in variable_expr and (
            not index_var or index_var not in variable_expr
        ):
            continue

        # Find the array definition
        array_text = map_match.group(1)
        array_start_in_context = map_match.start(1)
        array_start = context_start + array_start_in_context

        # Try to find and update the icon in the array
        # Look for array elements with icon field
        updated = _update_icon_in_array_by_value(
            content=content,
            array_start=array_start,
            target_value=target_value,
            variable_expr=variable_expr,
            iterator_var=iterator_var,
            index_var=index_var,
            new_icon_component=new_icon_component,
        )

        if updated != content:
            # Update imports
            updated = _upsert_lucide_react_import_add_only(
                content=updated, new_icon_component=new_icon_component
            )
            logger.info(
                "[DesignMode Sync] (dynamic-pattern) Updated icon via pattern matching in %s",
                file_path,
            )
            return updated, True

    return content, False


def _update_icon_in_array_by_value(
    *,
    content: str,
    array_start: int,
    target_value: str,
    variable_expr: str,
    iterator_var: str,
    index_var: Optional[str],
    new_icon_component: str,
) -> str:
    """
    Update icon in array element based on matching value.

    Handles:
    - Matching by field value: ${item.id} with target_value="1"
    - Matching by index: ${index} with target_value="0" or "1"
    """
    # Find the array in content starting from array_start
    # Parse array elements
    brace_count = 0
    array_content_start = -1
    array_content_end = -1

    for i in range(array_start, len(content)):
        if content[i] == "[":
            if array_content_start == -1:
                array_content_start = i + 1
            brace_count += 1
        elif content[i] == "]":
            brace_count -= 1
            if brace_count == 0:
                array_content_end = i
                break

    if array_content_start == -1 or array_content_end == -1:
        return content

    array_content = content[array_content_start:array_content_end]

    # If variable expression is just "index", match by position
    if variable_expr == index_var or variable_expr == "index":
        try:
            target_index = int(target_value)
            return _update_icon_at_array_index(
                content=content,
                array_content=array_content,
                array_start=array_content_start,
                target_index=target_index,
                new_icon_component=new_icon_component,
            )
        except (ValueError, TypeError):
            pass

    # Otherwise, match by field value
    # Extract field name from variable_expr (e.g., "feature.id" -> "id")
    field_match = re.match(rf"{re.escape(iterator_var)}\.(\w+)", variable_expr)
    if not field_match:
        return content

    field_name = field_match.group(1)

    # Find object in array with matching field value and update its icon
    return _update_icon_where_field_matches(
        content=content,
        array_content=array_content,
        array_start=array_content_start,
        field_name=field_name,
        field_value=target_value,
        new_icon_component=new_icon_component,
    )


def _update_icon_at_array_index(
    *,
    content: str,
    array_content: str,
    array_start: int,
    target_index: int,
    new_icon_component: str,
) -> str:
    """Update icon field in the Nth object in an array."""
    # Find all object literals in array
    objects = []
    depth = 0
    obj_start = -1

    for i, char in enumerate(array_content):
        if char == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                objects.append((obj_start, i + 1))
                obj_start = -1

    if target_index < 0 or target_index >= len(objects):
        return content

    obj_start, obj_end = objects[target_index]
    obj_content = array_content[obj_start:obj_end]

    # Find and replace icon field
    icon_pattern = re.compile(r"\bicon\s*:\s*([A-Z][A-Za-z0-9]*)")
    icon_match = icon_pattern.search(obj_content)

    if not icon_match:
        return content

    old_icon = icon_match.group(1)
    if old_icon == new_icon_component:
        return content

    # Replace in the actual content
    absolute_match_start = array_start + obj_start + icon_match.start(1)
    absolute_match_end = array_start + obj_start + icon_match.end(1)

    return (
        content[:absolute_match_start]
        + new_icon_component
        + content[absolute_match_end:]
    )


def _update_icon_where_field_matches(
    *,
    content: str,
    array_content: str,
    array_start: int,
    field_name: str,
    field_value: str,
    new_icon_component: str,
) -> str:
    """Update icon field in object where specified field matches value."""
    # Find objects in array and check each for matching field
    depth = 0
    obj_start = -1

    for i, char in enumerate(array_content):
        if char == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                obj_end = i + 1
                obj_content = array_content[obj_start:obj_end]

                # Check if this object has matching field value
                field_pattern = re.compile(
                    rf'\b{re.escape(field_name)}\s*:\s*["\']({re.escape(field_value)}|[\w-]+)["\']'
                )
                field_match = field_pattern.search(obj_content)

                if field_match and field_match.group(1) == field_value:
                    # Found the matching object! Update its icon
                    icon_pattern = re.compile(r"\bicon\s*:\s*([A-Z][A-Za-z0-9]*)")
                    icon_match = icon_pattern.search(obj_content)

                    if icon_match:
                        old_icon = icon_match.group(1)
                        if old_icon != new_icon_component:
                            absolute_match_start = (
                                array_start + obj_start + icon_match.start(1)
                            )
                            absolute_match_end = (
                                array_start + obj_start + icon_match.end(1)
                            )

                            return (
                                content[:absolute_match_start]
                                + new_icon_component
                                + content[absolute_match_end:]
                            )

                obj_start = -1

    return content


def _extract_item_id_from_icon_design_id(design_id: str) -> Optional[str]:
    """
    DEPRECATED: Use _find_icon_by_dynamic_pattern instead for general solution.

    This function is kept for backwards compatibility with simple cases.
    """
    if not isinstance(design_id, str):
        return None
    value = design_id.strip()
    if not value:
        return None

    # Pattern 1: prefix-icon-suffix (e.g., "feature-icon-feature-1")
    if "-icon-" in value:
        parts = value.split("-icon-", 1)
        if len(parts) == 2:
            item_id = parts[1].strip()
            if item_id:
                return item_id

    # Pattern 2: prefix-{id}-icon (e.g., "features-card-1-icon")
    if value.endswith("-icon"):
        base = value[: -len("-icon")]
        segments = base.split("-")
        if segments:
            item_id = segments[-1].strip()
            if item_id:
                return item_id

    return None


def _extract_icon_payload_from_change(
    change: Any,
) -> tuple[Optional[str], Optional[str]]:
    """
    Icon changes are stored as change.type == "attribute" and change.property == "icon".

    The "to" value may be:
      - a dict like {"name":"brick-wall","svg":"..."}
      - a JSON string like {"name":"brick-wall","svg":"..."}
      - a plain string like "brick-wall"
      - raw SVG inner markup like "<path ... />"

    Returns:
      (icon_name, svg_inner), where each may be None.
    """
    if not change or not isinstance(getattr(change, "value", None), dict):
        return None, None

    to_value = change.value.get("to")
    if to_value is None:
        return None, None

    if isinstance(to_value, dict):
        name = to_value.get("name")
        svg = to_value.get("svg")
        icon_name = name.strip() if isinstance(name, str) and name.strip() else None
        svg_inner = svg.strip() if isinstance(svg, str) and svg.strip() else None
        return icon_name, svg_inner

    if not isinstance(to_value, str):
        return None, None

    raw = to_value.strip()
    if not raw:
        return None, None

    try:
        icon_data = json.loads(raw)
        if isinstance(icon_data, dict):
            name = icon_data.get("name")
            svg = icon_data.get("svg")
            icon_name = name.strip() if isinstance(name, str) and name.strip() else None
            svg_inner = svg.strip() if isinstance(svg, str) and svg.strip() else None
            return icon_name, svg_inner
    except Exception:
        pass

    # If it looks like SVG markup, treat it as svg_inner.
    if raw.startswith("<"):
        return None, raw

    return raw, None


def _extract_icon_name_from_change(change: Any) -> Optional[str]:
    icon_name, _svg_inner = _extract_icon_payload_from_change(change)
    return icon_name


def _upsert_jsx_attribute_if_missing(tag: str, attr: str, value: str) -> str:
    """
    Best-effort helper to add `attr="value"` to a JSX opening tag string if missing.
    Does not attempt to handle dynamic JSX expressions.
    """
    if not isinstance(tag, str) or not tag:
        return tag
    if not isinstance(attr, str) or not attr.strip():
        return tag
    if re.search(rf"(?<![\w-]){re.escape(attr)}\s*=", tag):
        return tag
    insertion = f' {attr}="{value}"'
    if tag.rstrip().endswith("/>"):
        return re.sub(r"\s*/>\s*$", insertion + " />", tag, count=1)
    return re.sub(r">\s*$", insertion + ">", tag, count=1)


def _upsert_lucide_class_names_in_svg_opening_tag(
    tag: str, *, icon_name: Optional[str]
) -> str:
    """
    Best-effort: if `className="..."` is a string literal, append lucide marker classes so
    the resulting icon matches the runtime mutation behavior.
    """
    if not isinstance(tag, str) or not tag:
        return tag

    match = re.search(r"(?<![\w-])className\s*=\s*(['\"])(?P<cls>.*?)\1", tag)
    if not match:
        return tag

    quote = match.group(1)
    classes_raw = match.group("cls") or ""
    classes = [c for c in re.split(r"\s+", classes_raw.strip()) if c]

    wanted = ["lucide"]
    if isinstance(icon_name, str) and icon_name.strip():
        wanted.append(f"lucide-{icon_name.strip()}")

    added = False
    for w in wanted:
        if w not in classes:
            classes.append(w)
            added = True

    if not added:
        return tag

    new_attr = f'className={quote}{" ".join(classes)}{quote}'
    start, end = match.span()
    return tag[:start] + new_attr + tag[end:]


def _sanitize_svg_inner_for_jsx(svg_inner: str) -> str:
    """Convert common SVG dash-case attributes to JSX-compatible camelCase."""
    if not isinstance(svg_inner, str) or not svg_inner:
        return svg_inner

    raw = svg_inner.strip()

    # If a full `<svg>...</svg>` was provided, keep only its inner markup so we don't
    # nest `<svg>` elements when patching an existing SVG node.
    outer_svg_match = re.search(
        r"(?is)^\s*<svg\b[^>]*>(?P<inner>.*?)</svg\s*>\s*$", raw
    )
    if outer_svg_match:
        raw = (outer_svg_match.group("inner") or "").strip()
    elif re.match(r"(?is)^\s*<svg\b[^>]*/>\s*$", raw):
        # Self-closing wrapper: no inner content to apply.
        raw = ""
    elif raw.lower().startswith("<svg"):
        # Best-effort: strip an incomplete wrapper (e.g. truncated payloads).
        gt = raw.find(">")
        if gt != -1:
            raw = raw[gt + 1 :]
        raw = re.sub(r"(?is)</svg\s*>\s*$", "", raw).strip()

    replacements = {
        "stroke-width": "strokeWidth",
        "stroke-linecap": "strokeLinecap",
        "stroke-linejoin": "strokeLinejoin",
        "stroke-miterlimit": "strokeMiterlimit",
        "fill-rule": "fillRule",
        "clip-rule": "clipRule",
        "stop-color": "stopColor",
        "stop-opacity": "stopOpacity",
        "text-anchor": "textAnchor",
        "dominant-baseline": "dominantBaseline",
        "xlink:href": "xlinkHref",
        "xml:space": "xmlSpace",
    }

    out = raw
    for src, dst in replacements.items():
        out = re.sub(rf"(?<![\w-]){re.escape(src)}\s*=", f"{dst}=", out)
    return out


def _upsert_lucide_react_import_add_only(
    *, content: str, new_icon_component: str
) -> str:
    """
    Ensure `new_icon_component` is imported from `lucide-react`, without trying to remove
    other imports (some projects reference icons as identifiers, e.g. `icon: Shield`).
    """
    if not isinstance(content, str) or not content:
        return content
    if not isinstance(new_icon_component, str) or not new_icon_component.strip():
        return content
    new_icon_component = new_icon_component.strip()

    import_pattern = r"import\s*\{\s*(?P<names>[^}]*)\s*\}\s*from\s*(?P<q>['\"])lucide-react(?P=q)\s*;?"
    import_match = re.search(import_pattern, content)

    if import_match:
        names_raw = import_match.group("names") or ""
        quote = import_match.group("q") or "'"
        had_semicolon = import_match.group(0).rstrip().endswith(";")

        specifiers: list[str] = []
        seen: set[str] = set()
        for raw_spec in names_raw.split(","):
            spec = raw_spec.strip()
            if not spec:
                continue

            imported_name = spec
            alias = None
            alias_parts = re.split(r"\s+as\s+", spec, maxsplit=1)
            if len(alias_parts) == 2:
                imported_name = alias_parts[0].strip()
                alias = alias_parts[1].strip() or None

            fixed_name = (
                _lucide_icon_name_to_component_name(imported_name) or imported_name
            )
            spec_text = f"{fixed_name} as {alias}" if alias else fixed_name

            imported_symbol = fixed_name.strip()
            if imported_symbol and imported_symbol not in seen:
                seen.add(imported_symbol)
                specifiers.append(spec_text)

        if new_icon_component not in seen:
            specifiers.append(new_icon_component)

        rebuilt_import = (
            f"import {{ {', '.join(specifiers)} }} from {quote}lucide-react{quote}"
        )
        if had_semicolon:
            rebuilt_import += ";"
        return (
            content[: import_match.start()]
            + rebuilt_import
            + content[import_match.end() :]
        )

    # No lucide-react import found: add one at the top after other imports (if any).
    last_import_match = None
    for match in re.finditer(r"import\s+.*?from\s+['\"].*?['\"];?\s*\n", content):
        last_import_match = match

    if last_import_match:
        insert_pos = last_import_match.end()
        new_import = f"import {{ {new_icon_component} }} from 'lucide-react'\n"
        return content[:insert_pos] + new_import + content[insert_pos:]

    return f"import {{ {new_icon_component} }} from 'lucide-react'\n\n{content}"


def _apply_icon_change_by_item_id_assignment(
    *,
    content: str,
    file_path: str,
    item_id: str,
    icon_name: str,
) -> tuple[str, bool]:
    """
    Handle patterns like:
      const features = [{ id: "feature-1", icon: Shield }, ...]
      const features = [{ icon: Shield, id: "feature-1" }, ...]
      ...
      <feature.icon ... />
    by updating the object with `id == item_id` to `icon: <NewIconComponent>`.
    Handles both field orders (id before icon, or icon before id).
    """
    if not isinstance(content, str) or not content:
        return content, False
    if not isinstance(item_id, str) or not item_id.strip():
        return content, False
    item_id = item_id.strip()

    new_icon_component = _lucide_icon_name_to_component_name(icon_name)
    if not new_icon_component:
        return content, False

    # Try Pattern 1: id before icon (original pattern)
    # Match: { id: "1", ..., icon: Shield }
    pattern_id_first = re.compile(
        rf"(?s)(\{{[^{{}}]*?\bid\s*:\s*(?P<q>['\"])"
        rf"{re.escape(item_id)}(?P=q)[^{{}}]*?\bicon\s*:\s*)"
        rf"(?P<icon>[A-Za-z_$][A-Za-z0-9_$]*)"
    )
    match = pattern_id_first.search(content)

    # Try Pattern 2: icon before id
    # Match: { icon: Shield, ..., id: "1" }
    if not match:
        pattern_icon_first = re.compile(
            rf"(?s)(\{{[^{{}}]*?\bicon\s*:\s*)"
            rf"(?P<icon>[A-Za-z_$][A-Za-z0-9_$]*)"
            rf"([^{{}}]*?\bid\s*:\s*(?P<q>['\"])"
            rf"{re.escape(item_id)}(?P=q))"
        )
        match = pattern_icon_first.search(content)

    if not match:
        return content, False

    old_icon_component = match.group("icon") or ""
    if old_icon_component == new_icon_component:
        return content, True

    updated_content = (
        content[: match.start("icon")]
        + new_icon_component
        + content[match.end("icon") :]
    )
    updated_content = _upsert_lucide_react_import_add_only(
        content=updated_content, new_icon_component=new_icon_component
    )

    logger.info(
        "[DesignMode Sync] (source-mapping) Updated icon assignment %s -> %s for item_id=%s in %s",
        old_icon_component or "?",
        new_icon_component,
        item_id,
        file_path,
    )
    return updated_content, True


async def _find_best_source_file_for_icon_item_id(
    *, sandbox: Any, item_id: str
) -> Optional[str]:
    if not isinstance(item_id, str) or not item_id.strip():
        return None
    item_id = item_id.strip()

    outputs: List[str] = []
    for needle in (f'"{item_id}"', f"'{item_id}'"):
        outputs.append(await _search_workspace_for_fixed_string(sandbox, needle))

    candidates: List[str] = []
    for out in outputs:
        candidates.extend(_parse_search_paths(out))
    if not candidates:
        return None

    ranked = sorted(candidates, key=_score_source_path)

    for path in ranked[:20]:
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, path
            )
        except Exception:
            continue
        if not isinstance(content, str) or not content:
            continue

        # Check Pattern 1: id before icon
        check = re.search(
            rf"(?s)\{{[^{{}}]*?\bid\s*:\s*(['\"])"
            rf"{re.escape(item_id)}\1[^{{}}]*?\bicon\s*:\s*[A-Za-z_$][A-Za-z0-9_$]*",
            content,
        )
        # Check Pattern 2: icon before id
        if not check:
            check = re.search(
                rf"(?s)\{{[^{{}}]*?\bicon\s*:\s*[A-Za-z_$][A-Za-z0-9_$]*"
                rf"[^{{}}]*?\bid\s*:\s*(['\"]){re.escape(item_id)}\1",
                content,
            )
        if check:
            return resolved_path

    return None


def _apply_icon_change_by_design_id(
    *,
    content: str,
    file_path: str,
    design_id: str,
    icon_name: Optional[str],
    svg_inner: Optional[str],
) -> tuple[str, bool]:
    """
    Apply an icon change by locating the element with `data-design-id`.

    Supports:
    - Lucide React icon component replacement (<Zap /> -> <Bell />)
    - Inline SVG replacement (<svg>...</svg>) when `svg_inner` is provided
    """
    bounds = _find_opening_tag_bounds_for_design_id(content, design_id)
    if not bounds:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate tag for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]

    tag_name = _extract_opening_tag_name(tag)
    if not tag_name:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not extract tag name for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    # Case 1: Lucide React component replacement (<Zap /> -> <Bell />).
    if tag_name[:1].isupper():
        if not isinstance(icon_name, str) or not icon_name.strip():
            logger.warning(
                "[DesignMode Sync] (source-mapping) Missing icon name for designId=%s in %s",
                design_id,
                file_path,
            )
            return content, False

        old_icon_name = tag_name

        new_icon_component = _lucide_icon_name_to_component_name(icon_name)
        if not new_icon_component:
            logger.warning(
                "[DesignMode Sync] (source-mapping) Invalid lucide icon name %r for designId=%s in %s",
                icon_name,
                design_id,
                file_path,
            )
            return content, False

        # If already the same icon, treat as success
        if old_icon_name == new_icon_component:
            return content, True

        # Replace the icon in the opening tag
        updated_tag = re.sub(
            r"<\s*" + re.escape(old_icon_name) + r"\b",
            f"<{new_icon_component}",
            tag,
            count=1,
        )

        updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]

        # Check if this is a self-closing tag or has a closing tag
        if not tag.rstrip().endswith("/>"):
            # Find and replace the closing tag
            closing_tag_pattern = r"</\s*" + re.escape(old_icon_name) + r"\s*>"
            # Search in a reasonable window after the opening tag
            window_start = tag_start
            window_end = min(len(updated_content), window_start + 2000)
            window = updated_content[window_start:window_end]

            if re.search(closing_tag_pattern, window):
                window = re.sub(
                    closing_tag_pattern, f"</{new_icon_component}>", window, count=1
                )
                updated_content = (
                    updated_content[:window_start]
                    + window
                    + updated_content[window_end:]
                )

        # Update the lucide-react import line to include the new icon (and sanitize any invalid ones).
        import_pattern = r"import\s*\{\s*(?P<names>[^}]*)\s*\}\s*from\s*(?P<q>['\"])lucide-react(?P=q)\s*;?"
        import_match = re.search(import_pattern, updated_content)

        if import_match:
            names_raw = import_match.group("names") or ""
            quote = import_match.group("q") or "'"
            had_semicolon = import_match.group(0).rstrip().endswith(";")

            specifiers: list[str] = []
            seen: set[str] = set()
            for raw_spec in names_raw.split(","):
                spec = raw_spec.strip()
                if not spec:
                    continue

                imported_name = spec
                alias = None
                alias_parts = re.split(r"\s+as\s+", spec, maxsplit=1)
                if len(alias_parts) == 2:
                    imported_name = alias_parts[0].strip()
                    alias = alias_parts[1].strip() or None

                fixed_name = (
                    _lucide_icon_name_to_component_name(imported_name) or imported_name
                )
                spec_text = f"{fixed_name} as {alias}" if alias else fixed_name

                imported_symbol = fixed_name.strip()
                if imported_symbol and imported_symbol not in seen:
                    seen.add(imported_symbol)
                    specifiers.append(spec_text)

            if new_icon_component not in seen:
                specifiers.append(new_icon_component)
                seen.add(new_icon_component)

            content_without_import_line = (
                updated_content[: import_match.start()]
                + updated_content[import_match.end() :]
            )
            old_icon_usage_pattern = r"<" + re.escape(old_icon_name) + r"[\s/>]"
            if not re.search(old_icon_usage_pattern, content_without_import_line):
                specifiers = [
                    s
                    for s in specifiers
                    if re.split(r"\s+as\s+", s, maxsplit=1)[0].strip() != old_icon_name
                ]

            rebuilt_import = (
                f"import {{ {', '.join(specifiers)} }} from {quote}lucide-react{quote}"
            )
            if had_semicolon:
                rebuilt_import += ";"
            updated_content = (
                updated_content[: import_match.start()]
                + rebuilt_import
                + updated_content[import_match.end() :]
            )
        else:
            # No lucide-react import found, add one at the top after other imports
            # Find the last import statement
            last_import_match = None
            for match in re.finditer(
                r"import\s+.*?from\s+['\"].*?['\"];?\s*\n", updated_content
            ):
                last_import_match = match

            if last_import_match:
                insert_pos = last_import_match.end()
                new_import = f"import {{ {new_icon_component} }} from 'lucide-react'\n"
                updated_content = (
                    updated_content[:insert_pos]
                    + new_import
                    + updated_content[insert_pos:]
                )
            else:
                # No imports found, add at the beginning
                new_import = (
                    f"import {{ {new_icon_component} }} from 'lucide-react'\n\n"
                )
                updated_content = new_import + updated_content

        logger.info(
            "[DesignMode Sync] (source-mapping) Replaced icon %s -> %s for designId=%s in %s",
            old_icon_name,
            new_icon_component,
            design_id,
            file_path,
        )

        return updated_content, True

    # Case 2: Inline SVG replacement (<svg>...</svg>) when we have svg payload.
    if not isinstance(svg_inner, str) or not svg_inner.strip():
        logger.warning(
            "[DesignMode Sync] (source-mapping) Missing SVG payload for icon change designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    svg_inner = _sanitize_svg_inner_for_jsx(svg_inner.strip())
    if not svg_inner:
        logger.warning(
            "[DesignMode Sync] (source-mapping) SVG payload empty after sanitization for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    if tag_name.lower() == "svg":
        if tag.rstrip().endswith("/>"):
            # Convert to an explicit <svg>...</svg> block.
            opening = tag.rstrip()[:-2].rstrip() + ">"
            opening = _upsert_jsx_attribute_if_missing(opening, "viewBox", "0 0 24 24")
            opening = _upsert_jsx_attribute_if_missing(opening, "fill", "none")
            opening = _upsert_jsx_attribute_if_missing(
                opening, "stroke", "currentColor"
            )
            opening = _upsert_jsx_attribute_if_missing(opening, "strokeWidth", "2")
            opening = _upsert_jsx_attribute_if_missing(
                opening, "strokeLinecap", "round"
            )
            opening = _upsert_jsx_attribute_if_missing(
                opening, "strokeLinejoin", "round"
            )
            opening = _upsert_lucide_class_names_in_svg_opening_tag(
                opening, icon_name=icon_name
            )
            updated_content = (
                content[:tag_start]
                + opening
                + svg_inner
                + "</svg>"
                + content[tag_end + 1 :]
            )
            return updated_content, True

        closing_end = _find_matching_closing_tag_end(content, tag_end + 1, tag_name)
        if closing_end is None:
            return content, False
        closing_start = content.rfind("</", tag_end + 1, closing_end + 1)
        if closing_start == -1:
            return content, False

        opening = tag
        opening = _upsert_jsx_attribute_if_missing(opening, "viewBox", "0 0 24 24")
        opening = _upsert_jsx_attribute_if_missing(opening, "fill", "none")
        opening = _upsert_jsx_attribute_if_missing(opening, "stroke", "currentColor")
        opening = _upsert_jsx_attribute_if_missing(opening, "strokeWidth", "2")
        opening = _upsert_jsx_attribute_if_missing(opening, "strokeLinecap", "round")
        opening = _upsert_jsx_attribute_if_missing(opening, "strokeLinejoin", "round")
        opening = _upsert_lucide_class_names_in_svg_opening_tag(
            opening, icon_name=icon_name
        )

        updated_content = (
            content[:tag_start] + opening + svg_inner + content[closing_start:]
        )
        return updated_content, True

    # Fallback: designId may be on a wrapper; replace the first <svg> within the element span.
    span = _find_element_span_for_design_id(content, design_id)
    if not span:
        return content, False
    start, end = span
    fragment = content[start:end]
    svg_start = fragment.lower().find("<svg")
    if svg_start == -1:
        return content, False
    svg_open_end = _find_tag_end(fragment, svg_start)
    if svg_open_end is None:
        return content, False
    svg_open_tag = fragment[svg_start : svg_open_end + 1]
    svg_tag_name = _extract_opening_tag_name(svg_open_tag) or "svg"
    svg_close_end = _find_matching_closing_tag_end(
        fragment, svg_open_end + 1, svg_tag_name
    )
    if svg_close_end is None:
        return content, False
    svg_close_start = fragment.rfind("</", svg_open_end + 1, svg_close_end + 1)
    if svg_close_start == -1:
        return content, False

    updated_svg_open = svg_open_tag
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "viewBox", "0 0 24 24"
    )
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "fill", "none"
    )
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "stroke", "currentColor"
    )
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "strokeWidth", "2"
    )
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "strokeLinecap", "round"
    )
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "strokeLinejoin", "round"
    )
    updated_svg_open = _upsert_lucide_class_names_in_svg_opening_tag(
        updated_svg_open, icon_name=icon_name
    )

    updated_fragment = (
        fragment[:svg_start] + updated_svg_open + svg_inner + fragment[svg_close_start:]
    )
    updated_content = content[:start] + updated_fragment + content[end:]
    return updated_content, True


def _extract_closing_tag_name(tag: str) -> Optional[str]:
    if not isinstance(tag, str) or not tag:
        return None
    match = re.match(r"</\s*(?P<name>[A-Za-z][A-Za-z0-9:_.-]*)", tag)
    if not match:
        return None
    return (match.group("name") or "").strip() or None


def _tag_name_matches_for_design_mode(a: str, b: str) -> bool:
    if not a or not b:
        return False
    a = a.strip()
    b = b.strip()
    if _is_html_tag_name_for_design_mode(a) and _is_html_tag_name_for_design_mode(b):
        return a.lower() == b.lower()
    return a == b


def _find_matching_closing_tag_end(
    content: str, start_index: int, tag_name: str
) -> Optional[int]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(tag_name, str) or not tag_name:
        return None

    depth = 1
    i = max(0, start_index)
    while i < len(content):
        lt = content.find("<", i)
        if lt == -1:
            return None

        if lt + 1 < len(content) and content[lt + 1] in {"!", "?"}:
            tag_end = _find_tag_end(content, lt)
            if tag_end is None:
                return None
            i = tag_end + 1
            continue

        tag_end = _find_tag_end(content, lt)
        if tag_end is None:
            return None

        tag = content[lt : tag_end + 1]
        is_closing = tag.startswith("</")
        is_self_closing = tag.rstrip().endswith("/>")

        if is_closing:
            name = _extract_closing_tag_name(tag)
            if name and _tag_name_matches_for_design_mode(name, tag_name):
                depth -= 1
                if depth == 0:
                    return tag_end
        else:
            name = _extract_opening_tag_name(tag)
            if name and _tag_name_matches_for_design_mode(name, tag_name):
                if not is_self_closing:
                    depth += 1

        i = tag_end + 1

    return None


def _find_element_span_for_design_id(
    content: str, design_id: str
) -> Optional[tuple[int, int]]:
    bounds = _find_opening_tag_bounds_for_design_id(content, design_id)
    if not bounds:
        return None
    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]

    if tag.rstrip().endswith("/>"):
        return tag_start, tag_end + 1

    tag_name = _extract_opening_tag_name(tag)
    if not tag_name:
        return None

    closing_end = _find_matching_closing_tag_end(content, tag_end + 1, tag_name)
    if closing_end is None:
        return None

    return tag_start, closing_end + 1


def _apply_delete_change_by_design_id(
    *,
    content: str,
    file_path: str,
    design_id: str,
) -> tuple[str, bool]:
    """
    Delete an element identified by `design_id` from the source content.

    This removes the entire element including its opening tag, content, and closing tag.
    Leading whitespace on the same line is also removed to maintain clean formatting.
    """
    span = _find_element_span_for_design_id(content, design_id)
    if not span:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate element span for delete designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    start, end = span

    # Try to also remove leading whitespace on the same line for cleaner formatting
    # Look backwards from start to find beginning of line
    line_start = start
    while line_start > 0 and content[line_start - 1] in " \t":
        line_start -= 1

    # If the line only contains whitespace before the element, include that whitespace in deletion
    if line_start == 0 or content[line_start - 1] == "\n":
        start = line_start

    # Also try to remove the trailing newline if the element was on its own line
    if end < len(content) and content[end] == "\n":
        end += 1

    updated = content[:start] + content[end:]

    logger.info(
        "[DesignMode Sync] (source-mapping) Deleted element designId=%s from %s (removed %d chars)",
        design_id,
        file_path,
        end - start,
    )

    return updated, True


def _apply_swap_change_by_design_ids(
    *,
    content: str,
    file_path: str,
    design_id: str,
    target_design_id: str,
) -> tuple[str, bool]:
    span_a = _find_element_span_for_design_id(content, design_id)
    if not span_a:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate element span for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    span_b = _find_element_span_for_design_id(content, target_design_id)
    if not span_b:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate element span for target designId=%s in %s",
            target_design_id,
            file_path,
        )
        return content, False

    a_start, a_end = span_a
    b_start, b_end = span_b
    if a_start == b_start and a_end == b_end:
        return content, True

    if a_start > b_start:
        (a_start, a_end), (b_start, b_end) = (b_start, b_end), (a_start, a_end)
        design_id, target_design_id = target_design_id, design_id

    if a_end > b_start:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Swap spans overlap for designId=%s target=%s in %s",
            design_id,
            target_design_id,
            file_path,
        )
        return content, False

    a_block = content[a_start:a_end]
    b_block = content[b_start:b_end]
    updated = (
        content[:a_start] + b_block + content[a_end:b_start] + a_block + content[b_end:]
    )
    return updated, True


def _apply_move_change_by_design_id_anchor(
    *,
    content: str,
    file_path: str,
    design_id: str,
    anchor: str,
) -> tuple[str, bool]:
    """
    Move an element identified by `design_id` to a stable sibling anchor.

    Anchor format:
    - "before:<target-design-id>"
    - "after:<target-design-id>"
    - "only" (no-op)
    """
    if not isinstance(anchor, str) or not anchor:
        return content, False

    anchor = anchor.strip()
    if anchor == "only":
        # Treat as already-in-sync.
        return content, True

    mode: Optional[str] = None
    target_design_id: Optional[str] = None
    if anchor.startswith("before:"):
        mode = "before"
        target_design_id = anchor[len("before:") :].strip() or None
    elif anchor.startswith("after:"):
        mode = "after"
        target_design_id = anchor[len("after:") :].strip() or None

    if not mode or not target_design_id:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Unsupported move anchor for designId=%s in %s: %s",
            design_id,
            file_path,
            _truncate_for_log(anchor, limit=200),
        )
        return content, False

    return _apply_move_change_by_design_ids(
        content=content,
        file_path=file_path,
        design_id=design_id,
        target_design_id=target_design_id,
        mode=mode,
    )


def _apply_move_change_by_design_ids(
    *,
    content: str,
    file_path: str,
    design_id: str,
    target_design_id: str,
    mode: str,
) -> tuple[str, bool]:
    """Move `design_id` element to be directly before/after `target_design_id`."""
    if design_id == target_design_id:
        return content, True
    if mode not in {"before", "after"}:
        return content, False

    span_a = _find_element_span_for_design_id(content, design_id)
    if not span_a:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate element span for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    span_b = _find_element_span_for_design_id(content, target_design_id)
    if not span_b:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate element span for target designId=%s in %s",
            target_design_id,
            file_path,
        )
        return content, False

    a_start, a_end = span_a
    b_start, b_end = span_b

    # Don't attempt to reorder nested/overlapping spans (not siblings in source).
    if not (a_end <= b_start or b_end <= a_start):
        logger.warning(
            "[DesignMode Sync] (source-mapping) Move spans overlap for designId=%s target=%s in %s",
            design_id,
            target_design_id,
            file_path,
        )
        return content, False

    a_block = content[a_start:a_end]
    removed = content[:a_start] + content[a_end:]

    # Re-find target span after removal so indices are correct.
    span_b2 = _find_element_span_for_design_id(removed, target_design_id)
    if not span_b2:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not re-locate target span for move designId=%s target=%s in %s",
            design_id,
            target_design_id,
            file_path,
        )
        return content, False

    insert_at = span_b2[0] if mode == "before" else span_b2[1]
    updated = removed[:insert_at] + a_block + removed[insert_at:]
    return updated, True


async def _search_workspace_for_fixed_string(sandbox: Any, query: str) -> str:
    quoted = shlex.quote(query)
    cmd = (
        "if command -v rg >/dev/null 2>&1; then "
        f"rg --no-heading -n -F --hidden "
        "--glob '!**/node_modules/**' "
        "--glob '!**/.git/**' "
        "--glob '!**/dist/**' "
        "--glob '!**/build/**' "
        "--glob '!**/.next/**' "
        f"{quoted} /workspace | head -n 50; "
        "else "
        "grep -R -n -F "
        "--exclude-dir=node_modules "
        "--exclude-dir=.git "
        "--exclude-dir=dist "
        "--exclude-dir=build "
        "--exclude-dir=.next "
        f"-e {quoted} /workspace | head -n 50; "
        "fi"
    )
    try:
        return await sandbox.run_cmd(cmd) or ""
    except Exception:
        return ""


def _parse_search_paths(output: str) -> List[str]:
    paths: List[str] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(?P<path>/[^:]+):(?P<line>\d+):", line)
        if not match:
            continue
        path = match.group("path").strip()
        if not path:
            continue
        paths.append(path)
    # De-dupe while preserving order.
    deduped: List[str] = []
    seen: set[str] = set()
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)
    return deduped


def _score_source_path(path: str) -> tuple[int, int, int]:
    lowered = (path or "").lower()
    ext_rank = 9
    for ext, rank in (
        (".tsx", 0),
        (".jsx", 1),
        (".ts", 2),
        (".js", 3),
        (".html", 4),
        (".css", 5),
        (".vue", 6),
        (".svelte", 7),
    ):
        if lowered.endswith(ext):
            ext_rank = rank
            break
    in_src = 0 if "/src/" in lowered else 1
    return (ext_rank, in_src, len(path))


DESIGN_MODE_MANIFEST_FILENAME = "design-mode.manifest.json"


def _parse_design_mode_manifest_mapping(manifest_text: str) -> Dict[str, List[str]]:
    """
    Parse `design-mode.manifest.json` and return a mapping: design_id -> [file_path, ...].

    Supported formats:
    1) { "version": 1, "ids": { "<id>": "/workspace/.../file.tsx", ... } }
    2) { "version": 1, "elements": [ { "design_id": "<id>", "file_path": "/workspace/.../file.tsx" }, ... ] }
    3) { "<id>": "/workspace/.../file.tsx", ... } (legacy/simple mapping)
    """

    def _add(mapping: Dict[str, List[str]], design_id: Any, file_path: Any) -> None:
        if not isinstance(design_id, str) or not design_id.strip():
            return
        if not isinstance(file_path, str) or not file_path.strip():
            return
        normalized = _normalize_workspace_path(file_path)
        if not normalized:
            return
        paths = mapping.setdefault(design_id.strip(), [])
        if normalized not in paths:
            paths.append(normalized)

    if not isinstance(manifest_text, str) or not manifest_text.strip():
        return {}

    try:
        data = json.loads(manifest_text)
    except Exception:
        return {}

    mapping: Dict[str, List[str]] = {}

    if isinstance(data, dict):
        ids = data.get("ids")
        if isinstance(ids, dict):
            for design_id, file_path in ids.items():
                _add(mapping, design_id, file_path)
            return mapping

        elements = data.get("elements")
        if isinstance(elements, list):
            for el in elements:
                if not isinstance(el, dict):
                    continue
                design_id = el.get("design_id") or el.get("designId") or el.get("id")
                file_path = el.get("file_path") or el.get("filePath") or el.get("path")
                _add(mapping, design_id, file_path)
            return mapping

        # Accept a direct mapping { "<id>": "<path>" } if values are strings.
        for design_id, file_path in data.items():
            if isinstance(file_path, str):
                _add(mapping, design_id, file_path)
        return mapping

    return {}


async def _load_design_mode_manifest_mapping(
    sandbox: Any,
) -> tuple[Optional[str], Dict[str, List[str]]]:
    """
    Load and cache `design-mode.manifest.json` from the sandbox.

    Returns:
        (resolved_manifest_path, mapping)
    """
    cache_key = "design_mode_manifest_mapping"
    cached = getattr(sandbox, cache_key, None)
    if (
        isinstance(cached, tuple)
        and len(cached) == 2
        and (cached[0] is None or isinstance(cached[0], str))
        and isinstance(cached[1], dict)
    ):
        return cached[0], cached[1]

    default_path = f"/workspace/{DESIGN_MODE_MANIFEST_FILENAME}"
    try:
        manifest_text, resolved_path = await _read_file_with_workspace_fallback(
            sandbox, default_path
        )
    except Exception:
        resolved_path = None
        manifest_text = ""

    mapping = _parse_design_mode_manifest_mapping(manifest_text)

    try:
        setattr(sandbox, cache_key, (resolved_path, mapping))
    except Exception:
        pass

    return resolved_path, mapping


async def _find_best_source_file_for_design_id(
    *, sandbox: Any, design_id: str
) -> Optional[str]:
    if not isinstance(design_id, str) or not design_id.strip():
        return None

    outputs: List[str] = []
    for needle in (f'data-design-id="{design_id}"', f"data-design-id='{design_id}'"):
        outputs.append(await _search_workspace_for_fixed_string(sandbox, needle))

    candidates: List[str] = []
    for out in outputs:
        candidates.extend(_parse_search_paths(out))

    if not candidates:
        logger.warning(
            "[DesignMode Sync] (source-mapping) No matches for data-design-id=%r in /workspace",
            design_id,
        )
        return None
    ranked = sorted(candidates, key=_score_source_path)
    best = ranked[0]
    logger.info(
        "[DesignMode Sync] (source-mapping) data-design-id=%r matched %d file(s); best=%s",
        design_id,
        len(ranked),
        best,
    )
    logger.debug(
        "[DesignMode Sync] (source-mapping) Candidate files for %r: %s",
        design_id,
        ", ".join(ranked[:10]) + (" ..." if len(ranked) > 10 else ""),
    )
    return best


async def _apply_changes_with_source_mapping(
    *,
    sandbox: Any,
    changes: List[StyleChange],
    session_id: Optional[uuid.UUID] = None,
) -> tuple[int, List[str], List[StyleChange]]:
    """
    Apply Design Mode changes deterministically by locating `data-design-id="..."` in source files.

    This avoids spending LLM tokens on file/component searching. It expects Design Mode IDs to exist
    in the sandbox source (e.g., injected at project generation time).
    """
    applied_count = 0
    errors: List[str] = []
    remaining: List[StyleChange] = []

    logger.info(
        "[DesignMode Sync] (source-mapping) Applying %d change(s) using data-design-id mapping",
        len(changes),
    )

    manifest_path: Optional[str]
    manifest_mapping: Dict[str, List[str]]
    try:
        manifest_path, manifest_mapping = await _load_design_mode_manifest_mapping(
            sandbox
        )
    except Exception:
        manifest_path, manifest_mapping = None, {}

    if manifest_mapping:
        logger.info(
            "[DesignMode Sync] (source-mapping) Loaded %d Design Mode manifest entries from %s",
            len(manifest_mapping),
            manifest_path or f"/workspace/{DESIGN_MODE_MANIFEST_FILENAME}",
        )
    else:
        logger.info(
            "[DesignMode Sync] (source-mapping) No Design Mode manifest loaded; using workspace search/backfill"
        )

    await _emit_design_mode_sync_progress(
        session_id=session_id,
        processed=0,
        total=len(changes),
        applied=0,
        errors=0,
        current=1 if changes else None,
        done=False,
    )
    for idx, change in enumerate(changes, start=1):
        await _emit_design_mode_sync_progress(
            session_id=session_id,
            processed=idx - 1,
            total=len(changes),
            applied=applied_count,
            errors=len(errors),
            current=idx,
            done=False,
        )
        ctx = change.elementContext
        design_id = None
        if ctx and isinstance(ctx.designId, str) and ctx.designId.strip():
            design_id = ctx.designId.strip()
        elif isinstance(change.designId, str) and change.designId.strip():
            design_id = change.designId.strip()

        if not design_id:
            remaining.append(change)
            errors.append(f"Change {idx}: Missing designId")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d missing designId",
                idx,
                len(changes),
            )
            continue

        try:
            to_preview = None
            if isinstance(change.value, dict):
                to_preview = change.value.get("to")
            logger.info(
                "[DesignMode Sync] (source-mapping) Change %d/%d: designId=%s type=%s property=%s to=%s",
                idx,
                len(changes),
                design_id,
                change.type,
                change.property,
                (
                    _truncate_for_log(str(to_preview), limit=200)
                    if to_preview is not None
                    else "None"
                ),
            )
        except Exception:
            pass

        file_path: Optional[str] = None
        manifest_used = False
        if manifest_mapping:
            manifest_paths = manifest_mapping.get(design_id) or []
            if len(manifest_paths) == 1:
                file_path = manifest_paths[0]
                manifest_used = True
            else:
                if not manifest_paths:
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Change %d/%d: designId=%s missing from %s; falling back to workspace search",
                        idx,
                        len(changes),
                        design_id,
                        DESIGN_MODE_MANIFEST_FILENAME,
                    )
                else:
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Change %d/%d: manifest mapping ambiguous for designId=%s: %s; falling back to workspace search",
                        idx,
                        len(changes),
                        design_id,
                        manifest_paths,
                    )
                file_path = await _find_best_source_file_for_design_id(
                    sandbox=sandbox, design_id=design_id
                )
        else:
            file_path = await _find_best_source_file_for_design_id(
                sandbox=sandbox, design_id=design_id
            )
        content: Optional[str] = None
        resolved_path: Optional[str] = None

        if file_path:
            try:
                content, resolved_path = await _read_file_with_workspace_fallback(
                    sandbox, file_path
                )
            except Exception as exc:
                remaining.append(change)
                errors.append(f"Change {idx}: Failed to read {file_path}: {exc}")
                logger.warning(
                    "[DesignMode Sync] (source-mapping) Change %d/%d: failed to read %s: %s",
                    idx,
                    len(changes),
                    file_path,
                    exc,
                )
                continue
            if manifest_used and isinstance(content, str):
                if (
                    f'data-design-id="{design_id}"' not in content
                    and f"data-design-id='{design_id}'" not in content
                ):
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Manifest drift: designId=%s not found in %s; falling back to workspace search",
                        design_id,
                        resolved_path,
                    )
                    searched = await _find_best_source_file_for_design_id(
                        sandbox=sandbox, design_id=design_id
                    )
                    if searched:
                        try:
                            content, resolved_path = (
                                await _read_file_with_workspace_fallback(
                                    sandbox, searched
                                )
                            )
                        except Exception:
                            pass
        else:
            if change.type == "attribute" and change.property == "icon":
                icon_name = _extract_icon_name_from_change(change)
                item_id = _extract_item_id_from_icon_design_id(design_id)
                if icon_name and item_id:
                    candidate_path = await _find_best_source_file_for_icon_item_id(
                        sandbox=sandbox, item_id=item_id
                    )
                    if candidate_path:
                        try:
                            cand_content, cand_resolved_path = (
                                await _read_file_with_workspace_fallback(
                                    sandbox, candidate_path
                                )
                            )
                        except Exception:
                            cand_content = None
                            cand_resolved_path = None

                        if (
                            isinstance(cand_content, str)
                            and cand_content
                            and isinstance(cand_resolved_path, str)
                            and cand_resolved_path
                        ):
                            updated_candidate, applied_candidate = (
                                _apply_icon_change_by_item_id_assignment(
                                    content=cand_content,
                                    file_path=cand_resolved_path,
                                    item_id=item_id,
                                    icon_name=icon_name,
                                )
                            )
                            if applied_candidate:
                                try:
                                    ok = await sandbox.write_file(
                                        updated_candidate, cand_resolved_path
                                    )
                                except Exception as exc:
                                    ok = False
                                    errors.append(
                                        f"Change {idx}: Failed to write {cand_resolved_path}: {exc}"
                                    )
                                if ok:
                                    applied_count += 1
                                    logger.info(
                                        "[DesignMode Sync] (source-mapping) Change %d/%d applied via icon assignment fallback in %s",
                                        idx,
                                        len(changes),
                                        cand_resolved_path,
                                    )
                                    continue

            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d: data-design-id=%s not found in source; attempting backfill",
                idx,
                len(changes),
                design_id,
            )
            backfilled = await _backfill_design_id_in_source_from_react_source(
                sandbox=sandbox,
                change=change,
                design_id=design_id,
            )
            if backfilled:
                candidate_path, candidate_content = backfilled
                ok, reason = _verify_design_mode_target_matches_context(
                    change=change,
                    content=candidate_content,
                    file_path=candidate_path,
                    design_id=design_id,
                )
                if not ok:
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Change %d/%d: rejecting reactSource backfill candidate for designId=%s (%s)",
                        idx,
                        len(changes),
                        design_id,
                        reason,
                    )
                    backfilled = None
            if not backfilled:
                backfilled = await _backfill_design_id_in_source_from_text_search(
                    sandbox=sandbox,
                    change=change,
                    design_id=design_id,
                )
                if backfilled:
                    candidate_path, candidate_content = backfilled
                    ok, reason = _verify_design_mode_target_matches_context(
                        change=change,
                        content=candidate_content,
                        file_path=candidate_path,
                        design_id=design_id,
                    )
                    if not ok:
                        logger.warning(
                            "[DesignMode Sync] (source-mapping) Change %d/%d: rejecting text-search backfill candidate for designId=%s (%s)",
                            idx,
                            len(changes),
                            design_id,
                            reason,
                        )
                        backfilled = None
            if not backfilled:
                backfilled = await _backfill_design_id_in_source_from_class_name(
                    sandbox=sandbox,
                    change=change,
                    design_id=design_id,
                )
                if backfilled:
                    candidate_path, candidate_content = backfilled
                    ok, reason = _verify_design_mode_target_matches_context(
                        change=change,
                        content=candidate_content,
                        file_path=candidate_path,
                        design_id=design_id,
                    )
                    if not ok:
                        logger.warning(
                            "[DesignMode Sync] (source-mapping) Change %d/%d: rejecting className backfill candidate for designId=%s (%s)",
                            idx,
                            len(changes),
                            design_id,
                            reason,
                        )
                        backfilled = None
            if not backfilled:
                backfilled = (
                    await _backfill_design_id_in_source_from_component_callsite(
                        sandbox=sandbox,
                        change=change,
                        design_id=design_id,
                    )
                )
                if backfilled:
                    candidate_path, candidate_content = backfilled
                    ok, reason = _verify_design_mode_target_matches_context(
                        change=change,
                        content=candidate_content,
                        file_path=candidate_path,
                        design_id=design_id,
                    )
                    if not ok:
                        logger.warning(
                            "[DesignMode Sync] (source-mapping) Change %d/%d: rejecting callsite backfill candidate for designId=%s (%s)",
                            idx,
                            len(changes),
                            design_id,
                            reason,
                        )
                        backfilled = None
            if not backfilled:
                # Try dynamic pattern matching for icon changes (general solution)
                if change.type == "attribute" and change.property == "icon":
                    icon_name = _extract_icon_name_from_change(change)
                    if icon_name:
                        logger.info(
                            "[DesignMode Sync] (source-mapping) Change %d/%d: attempting dynamic pattern matching for icon designId=%s",
                            idx,
                            len(changes),
                            design_id,
                        )
                        dynamic_content, dynamic_success = (
                            await _find_icon_by_dynamic_pattern(
                                sandbox=sandbox,
                                design_id=design_id,
                                icon_name=icon_name,
                                element_context=change.elementContext,
                            )
                        )
                        if dynamic_success:
                            applied_count += 1
                            logger.info(
                                "[DesignMode Sync] (source-mapping) Change %d/%d applied via dynamic pattern matching",
                                idx,
                                len(changes),
                            )
                            continue

            if not backfilled:
                if change.type == "style":
                    to_value = None
                    if isinstance(change.value, dict):
                        to_value = change.value.get("to")
                    if to_value is not None:
                        css_ok, css_path = await _apply_style_change_as_css_override(
                            sandbox=sandbox,
                            manifest_path=manifest_path,
                            design_id=design_id,
                            css_prop=str(change.property or ""),
                            css_value="" if to_value is None else str(to_value),
                        )
                        if css_ok:
                            applied_count += 1
                            logger.info(
                                "[DesignMode Sync] (source-mapping) Change %d/%d applied as CSS override in %s",
                                idx,
                                len(changes),
                                css_path,
                            )
                            continue

                try:
                    ctx = change.elementContext
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Change %d/%d: backfill failed for designId=%s (tag=%s class=%s text=%s reactSource.file=%s)",
                        idx,
                        len(changes),
                        design_id,
                        getattr(ctx, "tagName", None),
                        _truncate_for_log(
                            str(getattr(ctx, "className", "") or ""), limit=160
                        ),
                        _truncate_for_log(
                            str(getattr(ctx, "textContent", "") or ""), limit=160
                        ),
                        (
                            (getattr(ctx, "reactSource", None) or {}).get("fileName")
                            if getattr(ctx, "reactSource", None)
                            else None
                        ),
                    )
                except Exception:
                    pass
                remaining.append(change)
                errors.append(
                    f'Change {idx}: Could not find data-design-id="{design_id}" in /workspace source'
                )
                continue

            resolved_path, content = backfilled
            logger.info(
                "[DesignMode Sync] (source-mapping) Change %d/%d: backfilled data-design-id=%s into %s",
                idx,
                len(changes),
                design_id,
                resolved_path,
            )

        if not isinstance(content, str) or not content:
            remaining.append(change)
            errors.append(f"Change {idx}: File is empty/unreadable: {resolved_path}")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d: file empty/unreadable: %s",
                idx,
                len(changes),
                resolved_path,
            )
            continue
        if not isinstance(resolved_path, str) or not resolved_path:
            remaining.append(change)
            errors.append(
                f"Change {idx}: Missing/invalid resolved_path for designId={design_id}"
            )
            continue

        match_ok, mismatch_reason = _verify_design_mode_target_matches_context(
            change=change,
            content=content,
            file_path=resolved_path,
            design_id=design_id,
        )
        if not match_ok:
            if change.type == "style":
                to_value = None
                if isinstance(change.value, dict):
                    to_value = change.value.get("to")
                if to_value is not None:
                    css_ok, css_path = await _apply_style_change_as_css_override(
                        sandbox=sandbox,
                        manifest_path=manifest_path,
                        design_id=design_id,
                        css_prop=str(change.property or ""),
                        css_value="" if to_value is None else str(to_value),
                    )
                    if css_ok:
                        applied_count += 1
                        logger.info(
                            "[DesignMode Sync] (source-mapping) Change %d/%d applied as CSS override in %s (mismatch guard bypass)",
                            idx,
                            len(changes),
                            css_path,
                        )
                        continue

            remaining.append(change)
            errors.append(
                f'Change {idx}: data-design-id="{design_id}" matched an unexpected element in {resolved_path} ({mismatch_reason})'
            )
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d: mismatch guard blocked apply for designId=%s in %s (%s)",
                idx,
                len(changes),
                design_id,
                resolved_path,
                mismatch_reason,
            )
            continue

        updated_content = content
        did_apply = False

        if change.type == "style":
            to_value = None
            if isinstance(change.value, dict):
                to_value = change.value.get("to")
            if to_value is None:
                remaining.append(change)
                errors.append(f"Change {idx}: Missing style 'to' value")
                logger.warning(
                    "[DesignMode Sync] (source-mapping) Change %d/%d missing style 'to' value",
                    idx,
                    len(changes),
                )
                continue

            updated_content, did_apply = _apply_style_change_by_design_id(
                content=content,
                file_path=resolved_path,
                design_id=design_id,
                css_prop=str(change.property or ""),
                css_value="" if to_value is None else str(to_value),
            )
        elif change.type == "text":
            from_value = None
            to_value = None
            if isinstance(change.value, dict):
                from_value = change.value.get("from")
                to_value = change.value.get("to")
            if not isinstance(from_value, str) or not isinstance(to_value, str):
                remaining.append(change)
                errors.append(f"Change {idx}: Missing text from/to values")
                logger.warning(
                    "[DesignMode Sync] (source-mapping) Change %d/%d missing text from/to values",
                    idx,
                    len(changes),
                )
                continue

            updated_content, did_apply = _apply_text_change_by_design_id(
                content=content,
                file_path=resolved_path,
                design_id=design_id,
                old_text=from_value,
                new_text=to_value,
            )
        elif change.type == "move":
            to_value = None
            if isinstance(change.value, dict):
                to_value = change.value.get("to")
            if not isinstance(to_value, str) or not to_value:
                remaining.append(change)
                errors.append(f"Change {idx}: Missing move target")
                logger.warning(
                    "[DesignMode Sync] (source-mapping) Change %d/%d missing move target",
                    idx,
                    len(changes),
                )
                continue

            # New format: anchor-based move (before:<id> / after:<id> / only).
            if (
                to_value == "only"
                or to_value.startswith("before:")
                or to_value.startswith("after:")
            ):
                if to_value == "only":
                    updated_content, did_apply = content, True
                else:
                    target_id = (
                        to_value.split(":", 1)[1].strip() if ":" in to_value else ""
                    )
                    if not target_id:
                        remaining.append(change)
                        errors.append(f"Change {idx}: Invalid move anchor '{to_value}'")
                        logger.warning(
                            "[DesignMode Sync] (source-mapping) Change %d/%d invalid move anchor: %s",
                            idx,
                            len(changes),
                            to_value,
                        )
                        continue

                    if not _find_opening_tag_bounds_for_design_id(content, target_id):
                        remaining.append(change)
                        errors.append(
                            f'Change {idx}: Could not find target data-design-id="{target_id}" in {resolved_path}'
                        )
                        logger.warning(
                            "[DesignMode Sync] (source-mapping) Change %d/%d move target designId not found in %s: %s",
                            idx,
                            len(changes),
                            resolved_path,
                            target_id,
                        )
                        continue

                    updated_content, did_apply = _apply_move_change_by_design_id_anchor(
                        content=content,
                        file_path=resolved_path,
                        design_id=design_id,
                        anchor=to_value,
                    )
            else:
                # Backward compatibility: older move changes used a raw swap target designId.
                target_id = to_value

                if not _find_opening_tag_bounds_for_design_id(content, target_id):
                    remaining.append(change)
                    errors.append(
                        f'Change {idx}: Could not find target data-design-id="{target_id}" in {resolved_path}'
                    )
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Change %d/%d target designId not found in %s: %s",
                        idx,
                        len(changes),
                        resolved_path,
                        target_id,
                    )
                    continue

                updated_content, did_apply = _apply_swap_change_by_design_ids(
                    content=content,
                    file_path=resolved_path,
                    design_id=design_id,
                    target_design_id=target_id,
                )
        elif change.type == "attribute" and change.property == "icon":
            # Handle icon changes
            icon_name, svg_inner = _extract_icon_payload_from_change(change)
            if not icon_name and not svg_inner:
                remaining.append(change)
                errors.append(
                    f"Change {idx}: Missing icon payload for attribute change"
                )
                logger.warning(
                    "[DesignMode Sync] (source-mapping) Change %d/%d missing icon payload",
                    idx,
                    len(changes),
                )
                continue

            updated_content, did_apply = _apply_icon_change_by_design_id(
                content=content,
                file_path=resolved_path,
                design_id=design_id,
                icon_name=icon_name,
                svg_inner=svg_inner,
            )
            if not did_apply and icon_name:
                item_id = _extract_item_id_from_icon_design_id(design_id)
                if item_id:
                    updated_content, did_apply = (
                        _apply_icon_change_by_item_id_assignment(
                            content=content,
                            file_path=resolved_path,
                            item_id=item_id,
                            icon_name=icon_name,
                        )
                    )
        elif change.type == "delete":
            # Handle delete changes - remove the element from the source
            updated_content, did_apply = _apply_delete_change_by_design_id(
                content=content,
                file_path=resolved_path,
                design_id=design_id,
            )
        else:
            remaining.append(change)
            errors.append(f"Change {idx}: Unsupported change type '{change.type}'")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d unsupported type: %s",
                idx,
                len(changes),
                change.type,
            )
            continue

        if not did_apply:
            if change.type == "style":
                to_value = None
                if isinstance(change.value, dict):
                    to_value = change.value.get("to")
                if to_value is not None:
                    css_ok, css_path = await _apply_style_change_as_css_override(
                        sandbox=sandbox,
                        manifest_path=manifest_path,
                        design_id=design_id,
                        css_prop=str(change.property or ""),
                        css_value="" if to_value is None else str(to_value),
                    )
                    if css_ok:
                        applied_count += 1
                        logger.info(
                            "[DesignMode Sync] (source-mapping) Change %d/%d applied as CSS override in %s (source patch failed)",
                            idx,
                            len(changes),
                            css_path,
                        )
                        continue

            remaining.append(change)
            errors.append(f"Change {idx}: Could not apply change in {resolved_path}")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d failed to apply in %s (designId=%s)",
                idx,
                len(changes),
                resolved_path,
                design_id,
            )
            continue

        try:
            ok = await sandbox.write_file(updated_content, resolved_path)
        except Exception as exc:
            ok = False
            errors.append(f"Change {idx}: Failed to write {resolved_path}: {exc}")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d failed to write %s: %s",
                idx,
                len(changes),
                resolved_path,
                exc,
            )

        if ok:
            applied_count += 1
            logger.info(
                "[DesignMode Sync] (source-mapping) Change %d/%d applied in %s",
                idx,
                len(changes),
                resolved_path,
            )
        else:
            remaining.append(change)
            errors.append(f"Change {idx}: Failed to persist changes to {resolved_path}")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d failed to persist in %s",
                idx,
                len(changes),
                resolved_path,
            )

    await _emit_design_mode_sync_progress(
        session_id=session_id,
        processed=len(changes),
        total=len(changes),
        applied=applied_count,
        errors=len(errors),
        current=None,
        done=True,
    )
    return applied_count, errors, remaining


async def _apply_changes_with_ai(
    *,
    sandbox: Any,
    session: Any,
    changes: List[StyleChange],
) -> tuple[int, List[str], List[StyleChange]]:
    """Apply multiple changes with a single LLM request, returning (applied_count, errors, remaining_changes)."""
    errors: List[str] = []
    indexed_changes = list(enumerate(changes, start=1))

    eligible: List[tuple[int, StyleChange]] = []
    remaining: List[StyleChange] = []
    for idx, change in indexed_changes:
        if not change.elementContext:
            remaining.append(change)
            errors.append(f"Change {idx}: Missing element context")
            continue
        eligible.append((idx, change))

    if not eligible:
        return 0, errors, remaining

    llm_config = await _get_llm_config_for_session(session)
    llm_config.temperature = 0.1
    client = get_client(llm_config)

    workspace_roots: List[str] = []
    try:
        workspace_roots = await _get_workspace_top_level_dirs(sandbox)
    except Exception:
        workspace_roots = []

    if workspace_roots:
        logger.info(
            "[DesignMode Sync] /workspace top-level dirs: %s",
            ", ".join(workspace_roots[:10])
            + (" ..." if len(workspace_roots) > 10 else ""),
        )

    source_hints: Dict[int, str] = {}
    try:
        source_hints = await _build_source_hints_for_changes(sandbox, eligible)
    except Exception:
        source_hints = {}

    candidate_files: Dict[int, str] = {}
    for idx, hint in source_hints.items():
        if not isinstance(hint, str):
            continue
        match = re.search(r"(?m)^\s*-\s*candidate_file:\s*(?P<path>\S+)\s*$", hint)
        if not match:
            continue
        candidate = match.group("path").strip()
        if candidate:
            candidate_files[idx] = candidate

    prompt = _build_batch_sync_prompt(
        eligible,
        workspace_roots=workspace_roots,
        source_hints=source_hints,
    )
    logger.info(
        "[DesignMode Sync] Using model=%s api_type=%s for %d change(s)",
        llm_config.model,
        llm_config.api_type,
        len(eligible),
    )
    logger.info("[DesignMode Sync] Batch prompt:\n%s", _truncate_for_log(prompt))

    try:
        assistant_blocks, _raw_metrics = await client.agenerate(
            messages=[[TextPrompt(text=prompt)]],
            max_tokens=8192,
            system_prompt="",
            temperature=0.1,
            tools=[DESIGN_MODE_SYNC_PLAN_TOOL],
            tool_choice={"type": "any"},
        )

        await _track_llm_usage_and_charge(
            session_id=str(getattr(session, "id", "")),
            model_name=llm_config.model,
            raw_metrics=_raw_metrics,
        )
    except Exception as e:
        logger.error("[DesignMode Sync] LLM request failed: %s", e, exc_info=True)
        errors.append(f"LLM request failed: {str(e)}")
        remaining.extend([change for _, change in eligible])
        return 0, errors, remaining

    plan: Optional[Dict[int, Dict[str, Any]]] = None
    tool_calls = [
        block
        for block in assistant_blocks
        if isinstance(block, ToolCall)
        and block.tool_name == DESIGN_MODE_SYNC_PLAN_TOOL_NAME
    ]
    if tool_calls:
        tool_payload = tool_calls[0].tool_input
        try:
            tool_payload_json = json.dumps(tool_payload, ensure_ascii=False)
        except Exception:
            tool_payload_json = str(tool_payload)
        logger.info(
            "[DesignMode Sync] Tool payload (%s):\n%s",
            DESIGN_MODE_SYNC_PLAN_TOOL_NAME,
            _truncate_for_log(tool_payload_json),
        )
        plan = _parse_batch_ai_tool_input(tool_payload)

    if not plan:
        response_text = "".join(
            block.text for block in assistant_blocks if isinstance(block, TextResult)
        ).strip()
        if response_text:
            logger.info(
                "[DesignMode Sync] Batch response (text):\n%s",
                # _truncate_for_log(response_text),
                response_text,
            )
            plan = _parse_batch_ai_response(response_text)
            if not plan:
                plan = _parse_batch_ai_text_plan(response_text)
                if plan:
                    logger.info("[DesignMode Sync] Parsed sync plan from text response")

    if not plan:
        errors.append("Failed to parse AI sync plan (tool, JSON, or text plan)")
        remaining.extend([change for _, change in eligible])
        return 0, errors, remaining

    applied_count = 0
    for idx, change in eligible:
        entry = plan.get(idx)
        if not isinstance(entry, dict):
            remaining.append(change)
            errors.append(f"Change {idx}: Missing plan entry from AI")
            continue

        file_path = entry.get("file_path")
        modifications = entry.get("modifications")
        change_type = entry.get("change_type") or "unknown"

        hinted_file = candidate_files.get(idx)
        if isinstance(hinted_file, str) and hinted_file.strip().startswith(
            "/workspace/"
        ):
            if (
                isinstance(file_path, str)
                and file_path.strip()
                and file_path.strip() != hinted_file
            ):
                logger.info(
                    "[DesignMode Sync] Overriding AI file_path for change %d: %s -> %s",
                    idx,
                    file_path.strip(),
                    hinted_file,
                )
            file_path = hinted_file

        if not isinstance(file_path, str) or not file_path.strip():
            remaining.append(change)
            errors.append(f"Change {idx}: Missing/invalid file_path from AI")
            continue
        if not isinstance(modifications, list) or len(modifications) == 0:
            remaining.append(change)
            errors.append(f"Change {idx}: Missing/empty modifications from AI")
            continue

        success = await _execute_file_modification(
            sandbox=sandbox,
            file_path=file_path,
            modifications=modifications,
            change_type=str(change_type),
        )

        if success:
            applied_count += 1
        else:
            remaining.append(change)
            errors.append(f"Change {idx}: Failed to apply file modification")

    return applied_count, errors, remaining


@router.post("/sync-state", response_model=SyncStateResponse)
async def sync_persisted_design_changes(
    current_user: CurrentUser,
    request: SyncStateRequest,
) -> SyncStateResponse:
    """
    Sync the session's persisted design-mode state to the sandbox.

    This uses the saved pending changes in `sessions.session_metadata["design_mode"]["changes"]`
    so that a refresh/session re-entry + Save applies the same edits to the sandbox.
    """
    try:
        session_uuid = uuid.UUID(request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id") from exc

    session = await Sessions.get_session_by_id(session_uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    metadata = session.session_metadata or {}
    design_mode = metadata.get("design_mode") or {}
    changes = _parse_persisted_design_changes(design_mode.get("changes") or [])

    total = len(changes)
    if total == 0:
        return SyncStateResponse(
            success=False,
            applied=0,
            total=0,
            remaining=0,
            errors=[],
            summary="No pending Design Mode changes found for this session.",
            remaining_changes=[],
            event_id=None,
        )

    logger.info(
        "Sync-state request: %d persisted changes for session %s",
        total,
        request.session_id,
    )

    # Get sandbox for file operations using V1 sandbox system
    try:
        sandbox = await _get_v1_sandbox_for_session(session_uuid)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get sandbox: %s", e)
        raise HTTPException(status_code=500, detail="Sandbox not available") from e

    applied_count, errors, remaining_changes = await _apply_changes_with_source_mapping(
        sandbox=sandbox,
        changes=changes,
        session_id=session_uuid,
    )

    all_applied = applied_count == total and len(errors) == 0

    # Persist remaining (failed) changes back to session metadata so user can retry.
    updated_at = int(time.time() * 1000)
    updated_design_state = {
        "changes": [change.model_dump() for change in remaining_changes],
        "updated_at": updated_at,
    }

    summary: str
    if all_applied:
        summary = (
            f"Synced {applied_count} design change"
            f"{'' if applied_count == 1 else 's'} from Design Mode into your sandbox. "
            "Switching back to Build Mode."
        )
    elif applied_count > 0:
        summary = (
            f"Partially synced Design Mode changes: applied {applied_count}/{total}. "
            "Some changes couldn't be applied due to source-mapping mismatches or missing `data-design-id` in the sandbox source. "
            "Re-enter Design Mode to review the pending changes and try Save again."
        )
    else:
        summary = (
            "I couldn't apply the saved Design Mode changes to the sandbox due to source-mapping mismatches or missing `data-design-id` in the sandbox source. "
            "Re-enter Design Mode to review the pending changes and try Save again."
        )

    event_id: Optional[str] = None
    async with get_db_session_local() as db:
        db_session = await Sessions.find_session_by_id(db=db, session_id=session_uuid)
        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")

        db_session.session_metadata = {
            **(db_session.session_metadata or {}),
            "design_mode": updated_design_state,
        }
        db.add(db_session)

        # Save a chat-visible assistant message so session reloads keep the sync summary.
        sync_event = RealtimeEvent(
            type=EventType.AGENT_RESPONSE,
            session_id=session_uuid,
            content={"text": summary},
        )
        await Events.save_event_db_session(
            db=db,
            session_id=session_uuid,
            event=sync_event,
        )
        event_id = str(sync_event.id)
        await db.flush()

    logger.info(
        "Sync-state complete: applied %d/%d, remaining %d, errors %d",
        applied_count,
        total,
        len(remaining_changes),
        len(errors),
    )
    if errors:
        logger.warning(
            "[DesignMode Sync] Sync-state errors (%d):\n%s",
            len(errors),
            _truncate_for_log("\n".join(errors), limit=8000),
        )
    if remaining_changes:
        try:
            remaining_summary: List[str] = []
            for change in remaining_changes[:10]:
                ctx = change.elementContext
                design_id = (
                    (ctx.designId if ctx and isinstance(ctx.designId, str) else None)
                    or (change.designId if isinstance(change.designId, str) else None)
                    or ""
                )
                remaining_summary.append(
                    f"{design_id} ({change.type}:{change.property})"
                )
            logger.info(
                "[DesignMode Sync] Remaining changes (first %d/%d): %s",
                min(10, len(remaining_changes)),
                len(remaining_changes),
                ", ".join([s for s in remaining_summary if s]),
            )
        except Exception:
            pass

    return SyncStateResponse(
        success=all_applied and applied_count > 0,
        applied=applied_count,
        total=total,
        remaining=len(remaining_changes),
        errors=errors,
        summary=summary,
        remaining_changes=remaining_changes,
        event_id=event_id,
    )


# ==========================================
# AI-Powered Change Application
# ==========================================


async def _apply_change_with_ai(
    sandbox: Any,
    change: StyleChange,
    session_id: str,
) -> bool:
    """
    Apply a design change to source files using AI.

    Strategy:
    1. Analyze the change and element context
    2. Use AI to search for the source file and location
    3. Determine the change type (Tailwind, CSS, inline style, text)
    4. Apply the appropriate modification
    5. Verify the change was applied

    Returns:
        True if successfully applied, False otherwise
    """
    try:
        ctx = change.elementContext
        if not ctx:
            logger.warning(f"No element context for change {change.designId}")
            return False

        # Build comprehensive prompt for AI
        prompt = _build_sync_prompt(change, ctx)

        logger.info(
            "[DesignMode Sync] Prompt (designId=%s type=%s property=%s):\n%s",
            change.designId,
            change.type,
            change.property,
            (prompt[:1000] + "\n...[truncated]") if len(prompt) > 1000 else prompt,
        )

        # Use session-agnostic defaults; relies on configured provider env vars/keys.
        llm_config = LLMConfig(temperature=0.1)
        client = get_client(llm_config)

        # Get AI response
        assistant_blocks, _raw_metrics = await client.agenerate(
            messages=[[TextPrompt(text=prompt)]],
            max_tokens=2000,
            system_prompt="",
            temperature=0.1,
            tools=[],
            tool_choice=None,
        )

        await _track_llm_usage_and_charge(
            session_id=session_id,
            model_name=llm_config.model,
            raw_metrics=_raw_metrics,
        )

        response_text = "".join(
            block.text for block in assistant_blocks if isinstance(block, TextResult)
        ).strip()

        logger.info(
            "[DesignMode Sync] Raw response (designId=%s): %s",
            change.designId,
            (
                (response_text[:1000] + "\n...[truncated]")
                if len(response_text) > 1000
                else response_text
            ),
        )

        if not response_text:
            logger.error("Empty AI response")
            return False

        # Parse AI response
        result = _parse_ai_response(response_text)

        if not result:
            logger.error("Failed to parse AI response")
            return False

        # Execute the file modification
        success = await _execute_file_modification(
            sandbox=sandbox,
            file_path=result["file_path"],
            modifications=result["modifications"],
            change_type=result["change_type"],
        )

        return success

    except Exception as e:
        logger.error(f"Error in _apply_change_with_ai: {e}", exc_info=True)
        return False


def _build_sync_prompt(change: StyleChange, ctx: ElementContext) -> str:
    """
    Build an intelligent prompt for AI to locate and modify source files.

    The prompt guides AI to:
    1. Identify the element in source code
    2. Determine styling approach (Tailwind, CSS, inline)
    3. Provide specific file modifications
    """

    # Build element description
    element_desc = f"<{ctx.tagName}"
    if ctx.id:
        element_desc += f' id="{ctx.id}"'
    if ctx.className:
        element_desc += f' class="{ctx.className}"'
    element_desc += ">"

    # Build parent context
    parent_context = ""
    if ctx.parentChain:
        parent_context = "\nParent hierarchy: " + " > ".join(
            [
                f"<{p['tag']}"
                + (f" class='{p['className']}'" if p.get("className") else "")
                + ">"
                for p in ctx.parentChain
            ]
        )

    # Determine change description based on type
    if change.type == "style":
        old_value = change.value.get("from", "")
        new_value = change.value.get("to", "")

        # Map CSS properties to Tailwind classes if applicable
        tailwind_hint = _get_tailwind_hint(change.property, old_value, new_value)

        change_desc = f"""
**Style Change:**
- Property: {change.property}
- Old value: {old_value}
- New value: {new_value}
{tailwind_hint}
"""
    elif change.type == "text":
        change_desc = f"""
**Text Change:**
- Old text: {change.value.get("from", "")}
- New text: {change.value.get("to", "")}
"""
    else:
        change_desc = f"**Change:** {change.type} - {change.property}"

    return build_design_mode_single_sync_prompt(
        element_desc=element_desc,
        xpath=ctx.xpath or "N/A",
        parent_context=parent_context,
        outer_html_preview=ctx.outerHTML[:200] if ctx.outerHTML else "N/A",
        change_desc=change_desc,
    )


def _get_tailwind_hint(property: str, old_value: str, new_value: str) -> str:
    """Generate Tailwind class mapping hints for common CSS properties."""

    # Common Tailwind mappings
    tailwind_mappings = {
        "background-color": {
            "rgb(59, 130, 246)": "bg-blue-500",
            "rgb(239, 68, 68)": "bg-red-500",
            "rgb(34, 197, 94)": "bg-green-500",
            "#ef4444": "bg-red-500",
            "#3b82f6": "bg-blue-500",
            "#22c55e": "bg-green-500",
            "#eab308": "bg-yellow-500",
            "#a855f7": "bg-purple-500",
            "#ec4899": "bg-pink-500",
            "#f97316": "bg-orange-500",
        },
        "color": {
            "rgb(0, 0, 0)": "text-black",
            "rgb(255, 255, 255)": "text-white",
            "rgb(59, 130, 246)": "text-blue-500",
            "#000000": "text-black",
            "#ffffff": "text-white",
        },
        "font-size": {
            "12px": "text-xs",
            "14px": "text-sm",
            "16px": "text-base",
            "18px": "text-lg",
            "20px": "text-xl",
            "24px": "text-2xl",
            "30px": "text-3xl",
            "36px": "text-4xl",
        },
        "padding": {
            "4px": "p-1",
            "8px": "p-2",
            "12px": "p-3",
            "16px": "p-4",
            "20px": "p-5",
            "24px": "p-6",
        },
    }

    mapping = tailwind_mappings.get(property, {})
    old_class = mapping.get(old_value)
    new_class = mapping.get(new_value)

    if old_class and new_class:
        return f"\n- Likely Tailwind change: {old_class} → {new_class}"

    return ""


def _parse_ai_response(content: str) -> Optional[Dict[str, Any]]:
    """Parse AI response JSON."""
    try:
        # Extract JSON from response (in case there's additional text)
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            logger.error("No JSON found in AI response")
            return None

        result = json.loads(json_match.group(0))

        # Validate required fields
        if not result.get("file_path") or not result.get("modifications"):
            logger.error("Missing required fields in AI response")
            return None

        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing AI response: {e}")
        return None


def _normalize_workspace_file_path(file_path: str) -> Optional[str]:
    """
    Normalize a potentially workspace-relative path into an absolute sandbox path.

    Design Mode sync is expected to only modify files under `/workspace`.
    """
    if not isinstance(file_path, str):
        return None

    path = file_path.strip()
    if not path:
        return None

    # Strip trivial wrappers from LLMs.
    if len(path) >= 2 and path[0] == path[-1] and path[0] in {"`", '"', "'"}:
        path = path[1:-1].strip()

    path = path.replace("\\", "/")
    if path.startswith("file://"):
        path = path[len("file://") :]
    if path.startswith("workspace/"):
        path = f"/{path}"
    elif path == "workspace":
        path = "/workspace"

    if not path:
        return None

    if path.startswith("/workspace/"):
        normalized = posixpath.normpath(path)
    elif path.startswith("/"):
        # Keep Design Mode sync safely scoped to workspace.
        logger.warning(
            "[DesignMode Sync] Rejecting non-workspace absolute path: %s", path
        )
        return None
    else:
        normalized = posixpath.normpath(posixpath.join("/workspace", path))

    if normalized == "/workspace":
        logger.warning("[DesignMode Sync] Rejecting workspace root path: %s", file_path)
        return None

    if not normalized.startswith("/workspace/"):
        logger.warning(
            "[DesignMode Sync] Rejecting path escaping workspace: %s -> %s",
            file_path,
            normalized,
        )
        return None

    return normalized


def _workspace_relative_path(normalized_workspace_path: str) -> Optional[str]:
    if not isinstance(normalized_workspace_path, str):
        return None
    path = normalized_workspace_path.strip()
    if not path.startswith("/workspace/"):
        return None
    rel = path[len("/workspace/") :]
    if not rel or rel.startswith("/"):
        return None
    rel = posixpath.normpath(rel)
    if rel.startswith("../") or rel == "..":
        return None
    return rel


async def _get_workspace_top_level_dirs(sandbox: Any) -> List[str]:
    """
    List top-level directories directly under `/workspace` (cached per sandbox object).

    These are used both for prompting (so the model can return absolute paths) and
    for resolving workspace-relative paths.
    """
    cache_key = "design_mode_workspace_roots"
    cached = getattr(sandbox, cache_key, None)
    if isinstance(cached, list) and all(isinstance(item, str) for item in cached):
        return cached

    roots: List[str] = []
    try:
        roots_out = await sandbox.run_cmd(
            "find /workspace -maxdepth 1 -mindepth 1 -type d -print"
        )
        roots = [
            line.strip() for line in (roots_out or "").splitlines() if line.strip()
        ]
    except Exception:
        roots = []

    ignored_basenames = {
        ".git",
        "node_modules",
        "__pycache__",
        ".cache",
        ".next",
        "dist",
        "build",
    }
    filtered: List[str] = []
    for root in roots:
        base = posixpath.basename(root.rstrip("/"))
        if base in ignored_basenames:
            continue
        if not root.startswith("/workspace/"):
            continue
        filtered.append(root)

    filtered.sort()
    try:
        setattr(sandbox, cache_key, filtered)
    except Exception:
        pass
    return filtered


async def _read_file_with_workspace_fallback(
    sandbox: Any, normalized_workspace_path: str
) -> tuple[str, str]:
    """
    Read a file from the sandbox, with fallbacks for projects nested under `/workspace/<project>/...`.

    Returns:
        (content, resolved_path)
    """
    last_error: Optional[Exception] = None

    def _coerce_text(content: Any) -> Optional[str]:
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if isinstance(content, (bytes, bytearray)):
            try:
                return bytes(content).decode("utf-8")
            except Exception:
                return None
        return None

    # 1) Direct read.
    try:
        content = await sandbox.read_file(normalized_workspace_path)
        text = _coerce_text(content)
        if text is not None:
            return text, normalized_workspace_path
    except Exception as exc:
        last_error = exc

    relative_path = _workspace_relative_path(normalized_workspace_path)
    if not relative_path:
        if last_error:
            raise last_error
        raise FileNotFoundError(normalized_workspace_path)

    # 2) Try `/workspace/*/<relative_path>` for each top-level directory.
    for root in await _get_workspace_top_level_dirs(sandbox):
        candidate = posixpath.normpath(posixpath.join(root, relative_path))
        if not candidate.startswith("/workspace/"):
            continue
        try:
            content = await sandbox.read_file(candidate)
            text = _coerce_text(content)
            if text is not None:
                return text, candidate
        except Exception as exc:
            last_error = exc

    # 3) Fallback: `find` by suffix anywhere in /workspace (excluding heavy dirs).
    try:
        pattern = f"*/{relative_path}"
        find_cmd = (
            "find /workspace -type f "
            "-not -path '*/node_modules/*' "
            "-not -path '*/.git/*' "
            "-not -path '*/dist/*' "
            "-not -path '*/build/*' "
            "-not -path '*/.next/*' "
            f"-path {shlex.quote(pattern)} "
            "-print -quit"
        )
        found = (await sandbox.run_cmd(find_cmd) or "").strip()
        if found:
            content = await sandbox.read_file(found)
            text = _coerce_text(content)
            if text is not None:
                return text, found
    except Exception as exc:
        last_error = exc

    if last_error:
        raise last_error
    raise FileNotFoundError(normalized_workspace_path)


async def _execute_file_modification(
    sandbox: Any,
    file_path: str,
    modifications: List[Dict[str, str]],
    change_type: str,
) -> bool:
    """
    Execute file modifications in the sandbox.

    Args:
        sandbox: Sandbox instance
        file_path: Path to the file to modify
        modifications: List of modifications to apply
        change_type: Type of change (tailwind, css, inline, text)

    Returns:
        True if successful, False otherwise
    """
    try:
        normalized_file_path = _normalize_workspace_file_path(file_path)
        if not normalized_file_path:
            logger.error("[DesignMode Sync] Invalid file_path from AI: %s", file_path)
            return False

        # Cache resolved paths on the sandbox object to avoid repeated lookups.
        cache_key = f"design_mode_resolved_paths"
        resolved_cache = getattr(sandbox, cache_key, None)
        if not isinstance(resolved_cache, dict):
            resolved_cache = {}
            try:
                setattr(sandbox, cache_key, resolved_cache)
            except Exception:
                resolved_cache = {}

        cached = resolved_cache.get(normalized_file_path)
        if isinstance(cached, str) and cached.startswith("/workspace/"):
            normalized_file_path = cached

        if normalized_file_path != file_path:
            logger.info(
                "[DesignMode Sync] Normalized file_path: %s -> %s",
                file_path,
                normalized_file_path,
            )

        # Read the file
        try:
            content, resolved_file_path = await _read_file_with_workspace_fallback(
                sandbox, normalized_file_path
            )
            if resolved_file_path != normalized_file_path:
                logger.info(
                    "[DesignMode Sync] Resolved file_path: %s -> %s",
                    normalized_file_path,
                    resolved_file_path,
                )
                resolved_cache[normalized_file_path] = resolved_file_path
                normalized_file_path = resolved_file_path
        except Exception as e:
            logger.error("Failed to read file %s: %s", normalized_file_path, e)
            return False

        if not content:
            logger.error("File %s is empty or doesn't exist", normalized_file_path)
            return False

        def _build_compact_with_index_map(value: str) -> tuple[str, List[int]]:
            compact_chars: List[str] = []
            index_map: List[int] = []
            for i, ch in enumerate(value):
                if ch.isspace():
                    continue
                if ch in {"'", '"'}:
                    ch = '"'
                compact_chars.append(ch)
                index_map.append(i)
            return "".join(compact_chars), index_map

        def _find_unique_whitespace_insensitive_match(
            haystack: str, needle: str
        ) -> Optional[tuple[int, int]]:
            if not needle:
                return None

            hay_compact, hay_map = _build_compact_with_index_map(haystack)
            needle_compact, _ = _build_compact_with_index_map(needle)
            if not needle_compact:
                return None

            first = hay_compact.find(needle_compact)
            if first == -1:
                return None

            second = hay_compact.find(needle_compact, first + 1)
            if second != -1:
                return None

            start = hay_map[first]
            end = hay_map[first + len(needle_compact) - 1] + 1
            return start, end

        # Apply modifications
        modified_content = content
        applied_any = False
        already_present_any = False
        failed_any = False
        for mod in modifications:
            if mod.get("type") == "replace":
                old_str = mod.get("old", "")
                new_str = mod.get("new", "")

                if not old_str:
                    logger.warning("Empty 'old' string in modification")
                    continue

                # Check if old string exists
                if old_str not in modified_content:
                    if (
                        isinstance(new_str, str)
                        and new_str
                        and new_str in modified_content
                    ):
                        logger.info(
                            "[DesignMode Sync] Replacement already present; skipping: %s...",
                            new_str[:100],
                        )
                        already_present_any = True
                        continue

                    match = _find_unique_whitespace_insensitive_match(
                        modified_content, old_str
                    )
                    if match:
                        start, end = match
                        original_slice = modified_content[start:end]
                        modified_content = (
                            modified_content[:start] + new_str + modified_content[end:]
                        )
                        applied_any = True
                        logger.info(
                            "[DesignMode Sync] Applied whitespace-insensitive replacement: %s... → %s...",
                            original_slice[:50],
                            str(new_str)[:50],
                        )
                        continue

                    logger.warning(
                        "[DesignMode Sync] String not found in file: %s...",
                        old_str[:100],
                    )
                    failed_any = True
                    continue

                # Replace (exact match)
                modified_content = modified_content.replace(old_str, new_str, 1)
                applied_any = True
                logger.info(
                    "[DesignMode Sync] Applied replacement: %s... → %s...",
                    old_str[:50],
                    str(new_str)[:50],
                )

        if applied_any:
            # Write the modified content back
            try:
                await sandbox.write_file(modified_content, normalized_file_path)
                logger.info("Successfully modified %s", normalized_file_path)
                return True
            except Exception as e:
                logger.error("Failed to write file %s: %s", normalized_file_path, e)
                return False

        if already_present_any and not failed_any:
            logger.info(
                "[DesignMode Sync] All requested modifications already present; no write needed."
            )
            return True

        logger.warning("No modifications were applied to the file")
        return False

    except Exception as e:
        logger.error(f"Error executing file modification: {e}", exc_info=True)
        return False


# ==========================================
# Slide Design Mode Endpoints
# ==========================================


class SlideSyncChange(BaseModel):
    """A single design change to apply to a slide."""

    design_id: str
    type: str  # 'style', 'text', 'attribute'
    property: str
    value: Dict[str, Optional[str]]  # {from: str | null, to: str | null}


class SlideSyncBatchRequest(BaseModel):
    """Request to sync design changes to a slide."""

    session_id: str
    presentation_name: str
    slide_number: int
    changes: List[SlideSyncChange]


class SlideSyncBatchResponse(BaseModel):
    """Response from slide sync batch."""

    success: bool
    processed: int = 0
    failed: int = 0
    errors: List[str] = []


class SlideDeckSyncChange(BaseModel):
    """A single design change to apply to a slide in a deck."""

    slide_number: int
    design_id: str
    type: str  # 'style', 'text', 'attribute'
    property: str
    value: Dict[str, Optional[str]]  # {from: str | null, to: str | null}


class SlideDeckSyncBatchRequest(BaseModel):
    """Request to sync design changes across multiple slides."""

    session_id: str
    presentation_name: str
    changes: List[SlideDeckSyncChange]


class SlideDeckSyncBatchResponse(BaseModel):
    """Response from slide deck sync batch."""

    success: bool
    processed: int = 0
    failed: int = 0
    errors: List[str] = []


# NOTE: Slide Design Mode endpoints have moved to `ii_agent.server.api.design_mode_slides`.
# These legacy handlers are kept temporarily to ease rebases, but are no longer registered.
# @router.get("/slide-proxy", response_class=HTMLResponse)
async def slide_proxy_design_mode(
    current_user: CurrentUser,
    session_id: str = Query(..., description="Session ID"),
    presentation_name: str = Query(..., description="Presentation name"),
    slide_number: int = Query(..., description="Slide number (1-based)"),
) -> HTMLResponse:
    """
    Proxy endpoint that fetches slide HTML from database and injects design mode runtime.

    This endpoint:
    1. Validates the user owns the session
    2. Fetches slide HTML from the database
    3. Injects the design mode runtime script into <head>
    4. Returns the modified HTML
    """
    from sqlalchemy import select, and_
    from ii_agent.db.models import SlideContent, Session

    async with get_db_session_local() as db_session:
        # Validate session ownership
        session_result = await db_session.execute(
            select(Session).where(
                and_(
                    Session.id == session_id,
                    Session.user_id == current_user.id,
                )
            )
        )
        session = session_result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=404, detail="Session not found or access denied"
            )

        # Fetch slide from database
        slide_result = await db_session.execute(
            select(SlideContent).where(
                and_(
                    SlideContent.session_id == session_id,
                    SlideContent.presentation_name == presentation_name,
                    SlideContent.slide_number == slide_number,
                )
            )
        )
        slide = slide_result.scalar_one_or_none()

        if not slide:
            raise HTTPException(
                status_code=404,
                detail=f"Slide {slide_number} not found in presentation '{presentation_name}'",
            )

        html = slide.slide_content or ""
        if not html.strip():
            raise HTTPException(status_code=404, detail="Slide has no content")

        # Inject design mode runtime (without URL rewriting for slides)
        modified_html = _inject_runtime_script_only(html)

        return HTMLResponse(
            content=modified_html,
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )


# @router.get("/slide-deck-proxy", response_class=HTMLResponse)
async def slide_deck_proxy_design_mode(
    current_user: CurrentUser,
    session_id: str = Query(..., description="Session ID"),
    presentation_name: str = Query(..., description="Presentation name"),
) -> HTMLResponse:
    """
    Proxy endpoint that fetches all slide HTML from database and returns a single
    vertically-stacked "deck" document with the design mode runtime injected.
    """
    from sqlalchemy import select, and_
    from ii_agent.db.models import SlideContent, Session

    async with get_db_session_local() as db_session:
        session_result = await db_session.execute(
            select(Session).where(
                and_(
                    Session.id == session_id,
                    Session.user_id == current_user.id,
                )
            )
        )
        session = session_result.scalar_one_or_none()
        if not session:
            raise HTTPException(
                status_code=404, detail="Session not found or access denied"
            )

        slides_result = await db_session.execute(
            select(SlideContent)
            .where(
                and_(
                    SlideContent.session_id == session_id,
                    SlideContent.presentation_name == presentation_name,
                )
            )
            .order_by(SlideContent.slide_number.asc())
        )
        slides = slides_result.scalars().all()
        if not slides:
            raise HTTPException(status_code=404, detail="No slides found")

        deck_html = _build_slide_deck_html(
            [
                (int(getattr(slide, "slide_number", 0) or 0), slide.slide_content or "")
                for slide in slides
            ]
        )
        modified_html = _inject_runtime_script_only(deck_html)

        return HTMLResponse(
            content=modified_html,
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )


def _inject_runtime_script_only(html: str) -> str:
    """
    Inject the design mode runtime script into HTML without URL rewriting.
    Used for slides where all resources should already be absolute.
    """
    if "<head>" in html:
        html = html.replace("<head>", f"<head>\n{DESIGN_MODE_RUNTIME_SCRIPT}\n", 1)
    elif "<head " in html:
        html = re.sub(
            r"(<head[^>]*>)", rf"\1\n{DESIGN_MODE_RUNTIME_SCRIPT}\n", html, count=1
        )
    elif "<html>" in html or "<html " in html:
        html = re.sub(
            r"(<html[^>]*>)",
            rf"\1\n<head>\n{DESIGN_MODE_RUNTIME_SCRIPT}\n</head>\n",
            html,
            count=1,
        )
    else:
        html = f"{DESIGN_MODE_RUNTIME_SCRIPT}\n{html}"

    return html


def _extract_slide_head_and_body(html: str) -> tuple[str, str]:
    head_match = re.search(r"<head[^>]*>(.*?)</head>", html, flags=re.I | re.S)
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.I | re.S)

    head = head_match.group(1) if head_match else ""
    body = body_match.group(1) if body_match else html

    # Remove wrappers if the slide HTML didn't have a <body>.
    body = re.sub(r"<!doctype[^>]*>", "", body, flags=re.I)
    body = re.sub(r"</?html[^>]*>", "", body, flags=re.I)
    body = re.sub(r"</?head[^>]*>", "", body, flags=re.I)
    body = re.sub(r"</?body[^>]*>", "", body, flags=re.I)
    return head, body


def _scope_css_for_slide(css_text: str, slide_number: int) -> str:
    """
    Scope slide CSS to a container to reduce cross-slide style collisions in the deck.
    This mirrors the lightweight selector prefixing used in the frontend SlidesViewer.
    """
    slide_scope = f'[data-slide-number="{slide_number}"]'

    def repl(match: re.Match[str]) -> str:
        selector = match.group(1)
        # Skip outer @-blocks (but still allow inner selectors to be scoped).
        if "@keyframes" in selector or "@media" in selector:
            return match.group(0)

        parts: List[str] = []
        for raw in selector.split(","):
            sel = raw.strip()
            if not sel:
                continue

            if sel == ":root":
                parts.append(":root")
                continue
            if sel.startswith("@"):
                parts.append(sel)
                continue
            # Rewrite root selectors to target the slide canvas instead of the deck document body.
            if sel in ("html", "body"):
                sel = ".ii-slide-canvas"
            else:
                sel = re.sub(
                    r"^html\\s+body(?=[\\s\\.#:\\[]|$)",
                    ".ii-slide-canvas",
                    sel,
                    flags=re.I,
                )
                sel = re.sub(
                    r"^body(?=[\\s\\.#:\\[]|$)",
                    ".ii-slide-canvas",
                    sel,
                    flags=re.I,
                )
                sel = re.sub(
                    r"^html(?=[\\s\\.#:\\[]|$)",
                    ".ii-slide-canvas",
                    sel,
                    flags=re.I,
                )
            if sel == "*":
                parts.append(f"{slide_scope} *")
                continue

            parts.append(f"{slide_scope} {sel}")

        if not parts:
            return match.group(0)
        return ", ".join(parts) + " {"

    return re.sub(r"([^{}]+){", repl, css_text)


def _build_slide_deck_html(slides: List[tuple[int, str]]) -> str:
    """
    Build a single HTML document containing all slides stacked vertically.
    """
    links: List[str] = []
    scoped_styles: List[str] = []
    slide_sections: List[str] = []

    for slide_number, html in slides:
        if not slide_number:
            continue
        if not html or not html.strip():
            continue

        head, body = _extract_slide_head_and_body(html)

        # Collect and strip style tags from both head and body.
        style_texts = re.findall(r"<style[^>]*>(.*?)</style>", head, flags=re.I | re.S)
        style_texts += re.findall(r"<style[^>]*>(.*?)</style>", body, flags=re.I | re.S)
        body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.I | re.S)

        # Collect link tags (fonts, etc.).
        links.extend(re.findall(r"<link\b[^>]*>", head, flags=re.I))

        # Scope inline styles.
        for css in style_texts:
            scoped_styles.append(_scope_css_for_slide(css, slide_number))

        slide_sections.append(
            f"""
<div class="ii-slide-wrapper" data-slide-number="{slide_number}">
  <div class="ii-slide-canvas">
    {body}
  </div>
</div>
""".strip()
        )

    # De-duplicate link tags by exact text.
    unique_links: List[str] = []
    seen = set()
    for link in links:
        normalized = link.strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_links.append(normalized)

    deck_base_css = """
html, body {
  margin: 0;
  padding: 0;
  background: #e5e7eb;
}
.ii-slide-deck {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 32px;
  padding: 20px;
  box-sizing: border-box;
  pointer-events: none;
}
.ii-slide-wrapper {
  width: 1280px;
  height: 720px;
  background: #ffffff;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 18px 60px rgba(0,0,0,0.12);
  pointer-events: none;
}
.ii-slide-canvas {
  width: 100%;
  height: 100%;
  overflow: hidden;
  pointer-events: auto;
}
""".strip()

    combined_styles = "\n\n".join(scoped_styles)

    head_parts: List[str] = [
        '<meta charset="utf-8" />',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f"<style>{deck_base_css}</style>",
        "\n".join(unique_links),
        f"<style>{combined_styles}</style>" if combined_styles else "",
    ]
    head_html = "\n".join([p for p in head_parts if p.strip()])
    body_html = (
        '\n<div class="ii-slide-deck">\n' + "\n".join(slide_sections) + "\n</div>\n"
    )

    return (
        f"<!doctype html><html><head>{head_html}</head><body>{body_html}</body></html>"
    )


# @router.post("/slide-sync-batch", response_model=SlideSyncBatchResponse)
async def slide_sync_batch(
    request: SlideSyncBatchRequest,
    current_user: CurrentUser,
) -> SlideSyncBatchResponse:
    """
    Apply design mode changes to a slide in the database.
    """
    from sqlalchemy import select, and_
    from datetime import datetime, timezone
    from ii_agent.db.models import SlideContent, Session

    async with get_db_session_local() as db_session:
        # Validate session ownership
        session_result = await db_session.execute(
            select(Session).where(
                and_(
                    Session.id == request.session_id,
                    Session.user_id == current_user.id,
                )
            )
        )
        session = session_result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=404, detail="Session not found or access denied"
            )

        # Fetch slide from database
        slide_result = await db_session.execute(
            select(SlideContent).where(
                and_(
                    SlideContent.session_id == request.session_id,
                    SlideContent.presentation_name == request.presentation_name,
                    SlideContent.slide_number == request.slide_number,
                )
            )
        )
        slide = slide_result.scalar_one_or_none()

        if not slide:
            raise HTTPException(
                status_code=404,
                detail=f"Slide {request.slide_number} not found",
            )

        html = slide.slide_content or ""
        if not html.strip():
            return SlideSyncBatchResponse(
                success=False, errors=["Slide has no content"]
            )

        # Apply changes to HTML
        modified_html = html
        processed = 0
        failed = 0
        errors: List[str] = []

        for change in request.changes:
            try:
                new_value = change.value.get("to", "")
                design_id = change.design_id

                if change.type == "style":
                    modified_html = _apply_slide_style_change(
                        modified_html, design_id, change.property, new_value or ""
                    )
                    processed += 1
                elif change.type == "text":
                    modified_html = _apply_slide_text_change(
                        modified_html, design_id, new_value or ""
                    )
                    processed += 1
                elif change.type == "attribute" and change.property == "icon":
                    modified_html = _apply_slide_icon_change(
                        modified_html, design_id, new_value or ""
                    )
                    processed += 1
                else:
                    failed += 1
                    errors.append(f"Unknown change type: {change.type}")

            except Exception as e:
                logger.error(f"Failed to apply change for {change.design_id}: {e}")
                failed += 1
                errors.append(f"Failed: {change.design_id}: {str(e)}")

        # Save modified HTML back to database
        if processed > 0:
            slide.slide_content = modified_html
            slide.updated_at = datetime.now(timezone.utc)
            metadata = slide.slide_metadata or {}
            metadata["last_design_mode_sync"] = datetime.now(timezone.utc).isoformat()
            slide.slide_metadata = metadata
            await db_session.commit()

        return SlideSyncBatchResponse(
            success=failed == 0,
            processed=processed,
            failed=failed,
            errors=errors,
        )


# @router.post("/slide-deck-sync-batch", response_model=SlideDeckSyncBatchResponse)
async def slide_deck_sync_batch(
    request: SlideDeckSyncBatchRequest,
    current_user: CurrentUser,
) -> SlideDeckSyncBatchResponse:
    """
    Apply design mode changes across multiple slides in the database.
    """
    from sqlalchemy import select, and_
    from datetime import datetime, timezone
    from ii_agent.db.models import SlideContent, Session

    if not request.changes:
        return SlideDeckSyncBatchResponse(
            success=True, processed=0, failed=0, errors=[]
        )

    async with get_db_session_local() as db_session:
        session_result = await db_session.execute(
            select(Session).where(
                and_(
                    Session.id == request.session_id,
                    Session.user_id == current_user.id,
                )
            )
        )
        session = session_result.scalar_one_or_none()
        if not session:
            raise HTTPException(
                status_code=404, detail="Session not found or access denied"
            )

        slide_numbers = sorted(
            {
                int(change.slide_number)
                for change in request.changes
                if int(change.slide_number) > 0
            }
        )
        if not slide_numbers:
            return SlideDeckSyncBatchResponse(
                success=False,
                processed=0,
                failed=len(request.changes),
                errors=["Missing slide numbers"],
            )

        slides_result = await db_session.execute(
            select(SlideContent).where(
                and_(
                    SlideContent.session_id == request.session_id,
                    SlideContent.presentation_name == request.presentation_name,
                    SlideContent.slide_number.in_(slide_numbers),
                )
            )
        )
        slides = slides_result.scalars().all()
        slide_by_number = {
            int(s.slide_number): s
            for s in slides
            if getattr(s, "slide_number", None) is not None
        }

        processed = 0
        failed = 0
        errors: List[str] = []
        updated_any = False

        # Apply changes grouped by slide.
        changes_by_slide: Dict[int, List[SlideDeckSyncChange]] = {}
        for change in request.changes:
            sn = int(change.slide_number)
            if sn <= 0:
                failed += 1
                errors.append(f"Invalid slide number for {change.design_id}")
                continue
            changes_by_slide.setdefault(sn, []).append(change)

        for sn, changes in changes_by_slide.items():
            slide = slide_by_number.get(sn)
            if not slide:
                failed += len(changes)
                errors.append(f"Slide {sn} not found")
                continue

            html = slide.slide_content or ""
            if not html.strip():
                failed += len(changes)
                errors.append(f"Slide {sn} has no content")
                continue

            modified_html = html
            for change in changes:
                try:
                    new_value = change.value.get("to", "")
                    design_id = change.design_id

                    if change.type == "style":
                        modified_html = _apply_slide_style_change(
                            modified_html, design_id, change.property, new_value or ""
                        )
                        processed += 1
                    elif change.type == "text":
                        modified_html = _apply_slide_text_change(
                            modified_html, design_id, new_value or ""
                        )
                        processed += 1
                    elif change.type == "attribute" and change.property == "icon":
                        modified_html = _apply_slide_icon_change(
                            modified_html, design_id, new_value or ""
                        )
                        processed += 1
                    else:
                        failed += 1
                        errors.append(f"Unknown change type: {change.type}")
                except Exception as exc:
                    logger.error(
                        "Failed to apply deck change for slide %s design_id=%s: %s",
                        sn,
                        change.design_id,
                        exc,
                    )
                    failed += 1
                    errors.append(f"Failed slide {sn} {change.design_id}: {str(exc)}")

            if modified_html != html:
                slide.slide_content = modified_html
                slide.updated_at = datetime.now(timezone.utc)
                metadata = slide.slide_metadata or {}
                metadata["last_design_mode_sync"] = datetime.now(
                    timezone.utc
                ).isoformat()
                slide.slide_metadata = metadata
                updated_any = True

        if updated_any:
            await db_session.commit()

        return SlideDeckSyncBatchResponse(
            success=failed == 0,
            processed=processed,
            failed=failed,
            errors=errors,
        )


class SlideDeckSyncStateRequest(BaseModel):
    """Request body for syncing persisted slide design-mode changes."""

    session_id: str
    presentation_name: str


class SlideDeckSyncStateResponse(BaseModel):
    """Response for syncing persisted slide design-mode changes."""

    success: bool
    applied: int
    total: int
    remaining: int
    errors: List[str]
    summary: str
    remaining_changes: List[StyleChange]
    event_id: Optional[str] = None


def _sanitize_slide_presentation_name(name: str) -> str:
    if not isinstance(name, str):
        return "presentation"
    sanitized = name.strip().replace(" ", "_")
    sanitized = "".join(c for c in sanitized if c.isalnum() or c in ("_", "-"))
    return sanitized or "presentation"


def _apply_slide_style_change_with_status(
    html: str, design_id: str, prop: str, value: str
) -> tuple[str, bool]:
    css_prop = re.sub(r"([A-Z])", r"-\1", prop).lower().lstrip("-")
    pattern = rf'(<[^>]*data-design-id=["\']){re.escape(design_id)}(["\'][^>]*)(style=["\'])([^"\']*)(["\']\s*/?>)'

    def add_style(m: re.Match[str]) -> str:
        before_style = m.group(4)
        before_style = re.sub(
            rf"{re.escape(css_prop)}\s*:\s*[^;]+;?\s*", "", before_style
        )
        if value:
            new_style = (
                f"{before_style.rstrip('; ')}"
                f"{'; ' if before_style.strip() else ''}"
                f"{css_prop}: {value};"
            )
        else:
            new_style = before_style.rstrip("; ")
        return f"{m.group(1)}{design_id}{m.group(2)}{m.group(3)}{new_style}{m.group(5)}"

    new_html, count = re.subn(pattern, add_style, html, count=1)

    if count == 0:
        pattern2 = (
            rf'(<[^>]*data-design-id=["\']){re.escape(design_id)}(["\'])([^>]*)(>)'
        )

        def add_style_attr(m: re.Match[str]) -> str:
            if value:
                return (
                    f'{m.group(1)}{design_id}{m.group(2)} style="{css_prop}: {value};"'
                    f"{m.group(3)}{m.group(4)}"
                )
            return m.group(0)

        new_html, count = re.subn(pattern2, add_style_attr, html, count=1)

    return new_html, count > 0


def _apply_slide_text_change_with_status(
    html: str, design_id: str, text: str
) -> tuple[str, bool]:
    # Delegate to the slide HTML patcher so text edits preserve nested markup/icons
    # (runtime updates only direct text nodes, not innerHTML).
    from ii_agent.tools.slide_design_mode.html_patch import (
        apply_slide_text_change_with_status,
    )

    return apply_slide_text_change_with_status(html, design_id, text)


def _apply_slide_icon_change_with_status(
    html: str, design_id: str, icon_data: str
) -> tuple[str, bool]:
    """
    Apply an icon change to slide HTML.

    Supports two icon formats:
    1. SVG icons (Lucide, etc.): Replace SVG inner content
    2. Material Icons (<i> or <span> with class containing 'material-icons'): Replace text content
    """
    # Parse icon_data - it may be JSON with {name, svg} or just raw SVG/icon name
    icon_name = ""
    svg_inner = ""
    try:
        data = json.loads(icon_data)
        icon_name = data.get("name", "")
        svg_inner = data.get("svg", "")
    except (json.JSONDecodeError, TypeError):
        # Might be raw SVG or icon name
        if icon_data.strip().startswith("<"):
            svg_inner = icon_data
        else:
            icon_name = icon_data

    # First, check if this is a Material Icons element (text-based icon)
    # Use a more flexible approach: find the element by design_id, then check if it has material-icons class
    if icon_name:
        # Pattern to find any element with the design_id
        element_pattern = rf'(<(?:i|span)[^>]*data-design-id=["\']){re.escape(design_id)}(["\'][^>]*>)(.*?)(</(?:i|span)>)'

        match = re.search(element_pattern, html, flags=re.DOTALL | re.IGNORECASE)
        if match:
            # Check if the element has material-icons class
            opening_tag = match.group(1) + design_id + match.group(2)
            if (
                "material-icons" in opening_tag.lower()
                or "material-symbols" in opening_tag.lower()
            ):
                # Replace text content with the new icon name
                new_html = (
                    html[: match.start()]
                    + match.group(1)
                    + design_id
                    + match.group(2)
                    + icon_name
                    + match.group(4)
                    + html[match.end() :]
                )
                return new_html, True

    # If no SVG inner content and no Material Icon match, fail
    if not svg_inner:
        return html, False

    # Try to apply as SVG icon
    pattern = rf'(<svg[^>]*data-design-id=["\']){re.escape(design_id)}(["\'][^>]*>)(.*?)(</svg>)'

    def replace_svg_content(m: re.Match[str]) -> str:
        return f"{m.group(1)}{design_id}{m.group(2)}{svg_inner}{m.group(4)}"

    new_html, count = re.subn(
        pattern, replace_svg_content, html, count=1, flags=re.DOTALL | re.IGNORECASE
    )
    if count > 0:
        return new_html, True

    # Fallback: design_id might be on a wrapper element rather than the <svg>.
    span = _find_element_span_for_design_id(html, design_id)
    if not span:
        return html, False

    start, end = span
    fragment = html[start:end]
    svg_start = fragment.lower().find("<svg")
    if svg_start == -1:
        # Slides generated with icon fonts (e.g. Material Icons) may not have any <svg>.
        # Convert the first material icon ligature element into an inline SVG so Lucide icon edits persist.
        wrapped_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" '
            'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            f"{svg_inner}</svg>"
        )

        material_pattern = r'(<(span|i)\b[^>]*class=["\'][^"\']*(?:material-icons|material-symbols[^"\']*)[^"\']*["\'][^>]*>)(.*?)(</\2>)'

        def replace_material(m: re.Match[str]) -> str:
            return f"{m.group(1)}{wrapped_svg}{m.group(4)}"

        replaced_fragment, count = re.subn(
            material_pattern,
            replace_material,
            fragment,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if count > 0:
            updated_html = html[:start] + replaced_fragment + html[end:]
            return updated_html, True

        return html, False

    svg_open_end = _find_tag_end(fragment, svg_start)
    if svg_open_end is None:
        return html, False

    svg_open_tag = fragment[svg_start : svg_open_end + 1]
    svg_tag_name = _extract_opening_tag_name(svg_open_tag) or "svg"

    # Find the matching closing tag for the first svg in the fragment.
    svg_close_end = _find_matching_closing_tag_end(
        fragment, svg_open_end + 1, svg_tag_name
    )
    if svg_close_end is None:
        return html, False

    svg_close_start = fragment.rfind("</", svg_open_end + 1, svg_close_end + 1)
    if svg_close_start == -1:
        return html, False

    updated_fragment = (
        fragment[: svg_open_end + 1] + svg_inner + fragment[svg_close_start:]
    )
    updated_html = html[:start] + updated_fragment + html[end:]
    return updated_html, True


# @router.post("/slide-deck-sync-state", response_model=SlideDeckSyncStateResponse)
async def sync_persisted_slide_deck_changes(
    current_user: CurrentUser,
    request: SlideDeckSyncStateRequest,
) -> SlideDeckSyncStateResponse:
    """
    Sync the session's persisted slide design-mode state to the DB + sandbox.

    Uses the saved pending changes in `sessions.session_metadata["design_mode"]["changes"]`
    so a refresh/session re-entry + Save applies the same edits.
    """
    from sqlalchemy import select, and_
    from datetime import datetime, timezone
    from ii_agent.db.models import SlideContent

    try:
        session_uuid = uuid.UUID(request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id") from exc

    session = await Sessions.get_session_by_id(session_uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    metadata = session.session_metadata or {}
    design_mode = metadata.get("design_mode") or {}
    changes = _parse_persisted_design_changes(design_mode.get("changes") or [])

    total = len(changes)
    if total == 0:
        return SlideDeckSyncStateResponse(
            success=False,
            applied=0,
            total=0,
            remaining=0,
            errors=[],
            summary="No pending Slide Design Mode changes found for this session.",
            remaining_changes=[],
            event_id=None,
        )

    async with get_db_session_local() as db:
        slides_result = await db.execute(
            select(SlideContent)
            .where(
                and_(
                    SlideContent.session_id == request.session_id,
                    SlideContent.presentation_name == request.presentation_name,
                )
            )
            .order_by(SlideContent.slide_number.asc())
        )
        slides = slides_result.scalars().all()
        if not slides:
            return SlideDeckSyncStateResponse(
                success=False,
                applied=0,
                total=total,
                remaining=total,
                errors=["No slides found for this presentation"],
                summary="No slides found for this presentation.",
                remaining_changes=changes,
                event_id=None,
            )

        slide_by_number = {
            int(s.slide_number): s
            for s in slides
            if getattr(s, "slide_number", None) is not None
        }

        applied_to_slide: Dict[int, List[StyleChange]] = {}
        remaining_changes: List[StyleChange] = []
        errors: List[str] = []
        updated_any = False

        safe_name = _sanitize_slide_presentation_name(request.presentation_name)
        presentation_dir = f"/workspace/presentations/{safe_name}"

        # Match website Design Mode semantics: progress totals represent "changes", not internal sub-steps.
        total_steps = total
        processed_steps = 0
        applied_count = 0
        error_count = 0

        logger.info(
            "[SlideDesignMode Sync] Starting sync for session=%s presentation=%s with %d changes",
            session_uuid,
            request.presentation_name,
            total_steps,
        )

        await _emit_design_mode_sync_progress(
            session_id=session_uuid,
            processed=0,
            total=total_steps,
            applied=0,
            errors=0,
            current=1,
            done=False,
        )

        # Apply changes to DB HTML first.
        for idx, change in enumerate(changes, start=1):
            await _emit_design_mode_sync_progress(
                session_id=session_uuid,
                processed=processed_steps,
                total=total_steps,
                applied=applied_count,
                errors=error_count,
                current=processed_steps + 1,
                done=False,
            )
            processed_steps += 1

            # Log each change being processed (like website design mode)
            to_preview = None
            try:
                if isinstance(change.value, dict):
                    to_preview = change.value.get("to")
            except Exception:
                to_preview = None
            logger.info(
                "[SlideDesignMode Sync] Change %d/%d: designId=%s type=%s property=%s to=%s",
                idx,
                len(changes),
                change.designId,
                change.type,
                change.property,
                str(to_preview)[:100] if to_preview else None,
            )

            slide_number = getattr(change, "slideNumber", None)
            if slide_number is None and getattr(change, "elementContext", None):
                slide_number = getattr(change.elementContext, "slideNumber", None)
            try:
                slide_number_int = int(slide_number)
            except Exception:
                slide_number_int = 0

            if slide_number_int <= 0:
                remaining_changes.append(change)
                error_count += 1
                errors.append(f"Change {idx}: Missing slideNumber")
                continue

            slide = slide_by_number.get(slide_number_int)
            if not slide:
                remaining_changes.append(change)
                error_count += 1
                errors.append(f"Change {idx}: Slide {slide_number_int} not found")
                continue

            html = slide.slide_content or ""
            if not html.strip():
                remaining_changes.append(change)
                error_count += 1
                errors.append(f"Change {idx}: Slide {slide_number_int} has no content")
                continue

            try:
                new_value = ""
                try:
                    new_value = (
                        change.value.get("to", "")
                        if isinstance(change.value, dict)
                        else ""
                    )
                except Exception:
                    new_value = ""

                did_apply = False
                modified_html = html

                if change.type == "style":
                    modified_html, did_apply = _apply_slide_style_change_with_status(
                        html, change.designId, change.property, new_value or ""
                    )
                elif change.type == "text":
                    modified_html, did_apply = _apply_slide_text_change_with_status(
                        html, change.designId, new_value or ""
                    )
                elif change.type == "attribute" and change.property == "icon":
                    modified_html, did_apply = _apply_slide_icon_change_with_status(
                        html, change.designId, new_value or ""
                    )
                elif change.type == "delete":
                    modified_html, did_apply = _apply_delete_change_by_design_id(
                        content=html,
                        file_path=f"slide_{slide_number_int}",
                        design_id=change.designId,
                    )
                elif change.type == "move":
                    # Handle move/swap changes
                    if not new_value:
                        remaining_changes.append(change)
                        error_count += 1
                        errors.append(f"Change {idx}: Missing move target")
                        logger.warning(
                            "[SlideDesignMode Sync] Change %d/%d missing move target",
                            idx,
                            len(changes),
                        )
                        continue

                    # Check for anchor-based move (before:<id> / after:<id> / only)
                    if (
                        new_value == "only"
                        or new_value.startswith("before:")
                        or new_value.startswith("after:")
                    ):
                        if new_value == "only":
                            # "only" means no move needed
                            modified_html, did_apply = html, True
                        else:
                            target_id = (
                                new_value.split(":", 1)[1].strip()
                                if ":" in new_value
                                else ""
                            )
                            if not target_id:
                                remaining_changes.append(change)
                                error_count += 1
                                errors.append(
                                    f"Change {idx}: Invalid move anchor '{new_value}'"
                                )
                                logger.warning(
                                    "[SlideDesignMode Sync] Change %d/%d invalid move anchor: %s",
                                    idx,
                                    len(changes),
                                    new_value,
                                )
                                continue

                            modified_html, did_apply = (
                                _apply_move_change_by_design_id_anchor(
                                    content=html,
                                    file_path=f"slide_{slide_number_int}",
                                    design_id=change.designId,
                                    anchor=new_value,
                                )
                            )
                    else:
                        # Backward compatibility: older move changes used a raw swap target designId
                        target_id = new_value
                        modified_html, did_apply = _apply_swap_change_by_design_ids(
                            content=html,
                            file_path=f"slide_{slide_number_int}",
                            design_id=change.designId,
                            target_design_id=target_id,
                        )
                else:
                    remaining_changes.append(change)
                    error_count += 1
                    errors.append(
                        f"Change {idx}: Unsupported change type: {change.type}"
                    )
                    continue

                if not did_apply:
                    remaining_changes.append(change)
                    error_count += 1
                    errors.append(
                        f"Change {idx}: Could not find design_id={change.designId} on slide {slide_number_int}"
                    )
                    continue

                if modified_html != html:
                    slide.slide_content = modified_html
                    slide.updated_at = datetime.now(timezone.utc)
                    meta = slide.slide_metadata or {}
                    meta["last_design_mode_sync"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    slide.slide_metadata = meta
                    updated_any = True

                applied_to_slide.setdefault(slide_number_int, []).append(change)
            except Exception as exc:
                remaining_changes.append(change)
                error_count += 1
                errors.append(
                    f"Change {idx}: Failed to apply slide change: {change.designId}: {str(exc)}"
                )

        # Flush progress to show "N/N" before the sandbox write phase begins.
        await _emit_design_mode_sync_progress(
            session_id=session_uuid,
            processed=processed_steps,
            total=total_steps,
            applied=applied_count,
            errors=error_count,
            current=None,
            done=False,
        )

        if updated_any:
            await db.commit()

        # Sync slides to sandbox as individual HTML files (best-effort).
        try:
            sandbox = await _get_v1_sandbox_for_session(session_uuid)
            await sandbox.run_cmd(f"mkdir -p {shlex.quote(presentation_dir)}")
        except Exception as exc:
            # If sandbox is unavailable, keep applied changes as remaining so user can retry sync.
            for sn, applied_list in applied_to_slide.items():
                remaining_changes.extend(applied_list)
            errors.append(f"Sandbox not available: {str(exc)}")
            error_count += 1
            applied_to_slide = {}
            sandbox = None

        for slide in slides:
            if not sandbox:
                continue

            try:
                sn = int(slide.slide_number)
                filename = f"slide_{sn:03d}.html"
                file_path = f"{presentation_dir}/{filename}"
                await sandbox.write_file(slide.slide_content or "", file_path)

                # Count as "applied" only after the sandbox write succeeded.
                if sn in applied_to_slide:
                    applied_count += len(applied_to_slide[sn])
                    applied_to_slide.pop(sn, None)
            except Exception as exc:
                sn = int(getattr(slide, "slide_number", 0) or 0)
                if sn in applied_to_slide:
                    remaining_changes.extend(applied_to_slide[sn])
                    applied_to_slide.pop(sn, None)
                errors.append(f"Failed to write slide {sn} to sandbox: {str(exc)}")
                error_count += 1

        # Best-effort write metadata.json (does not affect applied/remaining).
        if sandbox:
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                metadata_path = f"{presentation_dir}/metadata.json"
                existing_raw = None
                try:
                    existing_raw = await sandbox.read_file(metadata_path)
                except Exception:
                    existing_raw = None

                parsed: Dict[str, Any] = {}
                if isinstance(existing_raw, str) and existing_raw.strip():
                    try:
                        parsed = json.loads(existing_raw)
                    except Exception:
                        parsed = {}

                presentation_meta = (
                    parsed.get("presentation") if isinstance(parsed, dict) else None
                )
                if not isinstance(presentation_meta, dict):
                    presentation_meta = {}
                if not presentation_meta.get("created_at"):
                    presentation_meta["created_at"] = now_iso
                presentation_meta["updated_at"] = now_iso
                presentation_meta["name"] = request.presentation_name
                presentation_meta["title"] = (
                    request.presentation_name or "Untitled Presentation"
                )
                if "description" not in presentation_meta:
                    presentation_meta["description"] = ""

                existing_slides = {}
                slides_meta = parsed.get("slides") if isinstance(parsed, dict) else None
                if isinstance(slides_meta, list):
                    for item in slides_meta:
                        if not isinstance(item, dict):
                            continue
                        num = item.get("number")
                        if isinstance(num, int):
                            existing_slides[num] = item

                new_slides_meta = []
                for slide in slides:
                    sn = int(slide.slide_number)
                    filename = f"slide_{sn:03d}.html"
                    prev = existing_slides.get(sn, {})
                    created_at = (
                        prev.get("created_at") if isinstance(prev, dict) else None
                    )
                    if not isinstance(created_at, str) or not created_at:
                        created_at = now_iso
                    new_slides_meta.append(
                        {
                            "id": f"slide_{sn:03d}",
                            "number": sn,
                            "title": slide.slide_title or "",
                            "description": "",
                            "type": (
                                prev.get("type", "content")
                                if isinstance(prev, dict)
                                else "content"
                            ),
                            "filename": filename,
                            "file_path": f"presentations/{safe_name}/{filename}",
                            "preview_url": f"/workspace/presentations/{safe_name}/{filename}",
                            "created_at": created_at,
                            "updated_at": now_iso,
                        }
                    )

                final_meta = {
                    "presentation": presentation_meta,
                    "slides": new_slides_meta,
                }
                await sandbox.write_file(
                    json.dumps(final_meta, indent=2, ensure_ascii=False),
                    metadata_path,
                )
            except Exception as exc:
                logger.warning(
                    "[SlideDesignMode] Failed to write metadata.json: %s",
                    exc,
                )

        await _emit_design_mode_sync_progress(
            session_id=session_uuid,
            processed=total_steps,
            total=total_steps,
            applied=applied_count,
            errors=error_count,
            current=None,
            done=True,
        )

        logger.info(
            "[SlideDesignMode Sync] Completed sync for session=%s: applied=%d/%d errors=%d remaining=%d",
            session_uuid,
            applied_count,
            total_steps,
            error_count,
            len(remaining_changes),
        )
        if errors:
            logger.warning(
                "[SlideDesignMode Sync] Errors during sync: %s",
                errors[:10],  # Log first 10 errors
            )

        # Persist remaining changes back to session metadata so user can retry.
        updated_at = int(time.time() * 1000)
        updated_design_state = {
            "changes": [change.model_dump() for change in remaining_changes],
            "updated_at": updated_at,
        }

        all_applied = (
            applied_count == total and error_count == 0 and len(remaining_changes) == 0
        )

        if all_applied:
            summary = (
                f"Synced {applied_count} slide design change"
                f"{'' if applied_count == 1 else 's'} into your slide deck and sandbox. "
                "Switching back to Build Mode."
            )
        elif applied_count > 0:
            summary = (
                f"Partially synced slide Design Mode changes: applied {applied_count}/{total}. "
                "Re-enter Design Mode to review the pending changes and try Save again."
            )
        else:
            summary = (
                "I couldn't apply the saved Slide Design Mode changes. "
                "Re-enter Design Mode to review the pending changes and try Save again."
            )

        event_id: Optional[str] = None
        db_session = await Sessions.find_session_by_id(db=db, session_id=session_uuid)
        if not db_session:
            raise HTTPException(status_code=404, detail="Session not found")
        db_session.session_metadata = {
            **(db_session.session_metadata or {}),
            "design_mode": updated_design_state,
        }
        db.add(db_session)

        sync_event = RealtimeEvent(
            type=EventType.AGENT_RESPONSE,
            session_id=session_uuid,
            content={"text": summary},
        )
        await Events.save_event_db_session(
            db=db,
            session_id=session_uuid,
            event=sync_event,
        )
        event_id = str(sync_event.id)
        await db.flush()

        return SlideDeckSyncStateResponse(
            success=all_applied,
            applied=applied_count,
            total=total,
            remaining=len(remaining_changes),
            errors=errors,
            summary=summary,
            remaining_changes=remaining_changes,
            event_id=event_id,
        )


def _apply_slide_style_change(html: str, design_id: str, prop: str, value: str) -> str:
    """Apply a style change to an element in slide HTML."""
    css_prop = re.sub(r"([A-Z])", r"-\1", prop).lower().lstrip("-")

    # Try element with existing style attribute
    pattern = rf'(<[^>]*data-design-id=["\']){re.escape(design_id)}(["\'][^>]*)(style=["\'])([^"\']*)(["\']\s*/?>)'

    def add_style(m):
        before_style = m.group(4)
        before_style = re.sub(
            rf"{re.escape(css_prop)}\s*:\s*[^;]+;?\s*", "", before_style
        )
        if value:
            new_style = f"{before_style.rstrip('; ')}{'; ' if before_style.strip() else ''}{css_prop}: {value};"
        else:
            new_style = before_style.rstrip("; ")
        return f"{m.group(1)}{design_id}{m.group(2)}{m.group(3)}{new_style}{m.group(5)}"

    new_html, count = re.subn(pattern, add_style, html, count=1)

    if count == 0:
        pattern2 = (
            rf'(<[^>]*data-design-id=["\']){re.escape(design_id)}(["\'])([^>]*)(>)'
        )

        def add_style_attr(m):
            if value:
                return f'{m.group(1)}{design_id}{m.group(2)} style="{css_prop}: {value};"{m.group(3)}{m.group(4)}'
            return m.group(0)

        new_html, count = re.subn(pattern2, add_style_attr, html, count=1)

    return new_html


def _apply_slide_text_change(html: str, design_id: str, text: str) -> str:
    """Apply a text content change to an element in slide HTML."""
    pattern = rf'(<[^>]*data-design-id=["\']){re.escape(design_id)}(["\'][^>]*>)(.*?)(</[^>]+>)'

    def replace_text(m):
        return f"{m.group(1)}{design_id}{m.group(2)}{text}{m.group(4)}"

    new_html, _ = re.subn(pattern, replace_text, html, count=1, flags=re.DOTALL)
    return new_html


def _apply_slide_icon_change(html: str, design_id: str, icon_data: str) -> str:
    """Apply an icon change to an element in slide HTML (SVG or Material Icons)."""
    updated, _ = _apply_slide_icon_change_with_status(html, design_id, icon_data)
    return updated
