"""
Slide Design Mode API endpoints.

Keeps slide-specific proxy + sync logic isolated from the website/general Design Mode endpoints.
"""

import json
import logging
import re
import shlex
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.db.manager import Events, Sessions, get_db_session_local
from ii_agent.server.api.deps import CurrentUser
from ii_agent.tools.slide_design_mode import (
    apply_slide_icon_change,
    apply_slide_icon_change_with_status,
    apply_slide_style_change,
    apply_slide_style_change_with_status,
    apply_slide_text_change,
    apply_slide_text_change_with_status,
    build_slide_deck_html,
    sanitize_slide_presentation_name,
)

# Reuse the existing design-mode runtime + shared helpers (progress + move/swap parsing).
from ii_agent.server.api.design_mode import (  # noqa: PLC0415
    DESIGN_MODE_RUNTIME_SCRIPT,
    StyleChange,
    _apply_delete_change_by_design_id,
    _apply_move_change_by_design_id_anchor,
    _apply_swap_change_by_design_ids,
    _emit_design_mode_sync_progress,
    _get_v1_sandbox_for_session,
    _parse_persisted_design_changes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/design-mode", tags=["Design Mode"])

_EDITABLE_CLASS_NAMES = {"editable", "editable-img", "editing"}


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


def _sanitize_legacy_editable_artifacts(html: str) -> str:
    """
    Remove legacy EditableHtmlRenderer artifacts from stored slide HTML.

    We used to wrap text nodes in `<span class="editable" data-edit-id="...">`
    and inject styles that show the orange "click to edit" affordance. Slide Design
    Mode has its own selection UX (blue box), so these artifacts should never
    appear in either build mode or design mode.
    """

    if not html or not html.strip():
        return html

    # Drop EditableHtmlRenderer-specific <style> blocks.
    style_re = re.compile(r"<style[^>]*>(.*?)</style>", flags=re.I | re.S)

    def strip_style(match: re.Match[str]) -> str:
        css_text = match.group(1) or ""
        hay = css_text.lower()
        if ".editable" not in hay:
            return match.group(0)
        markers = ("#ff6b75", ".editable-img", ".drop-zone", ".image-preview")
        if any(m in hay for m in markers):
            return ""
        return match.group(0)

    html = style_re.sub(strip_style, html)

    # Unwrap text spans created by the renderer.
    span_re = re.compile(
        r"<span\b[^>]*\bdata-edit-id\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)[^>]*>(.*?)</span>",
        flags=re.I | re.S,
    )
    for _ in range(4):
        new_html = span_re.sub(r"\1", html)
        if new_html == html:
            break
        html = new_html

    # Strip renderer attributes.
    html = re.sub(
        r"\sdata-edit-id\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
        "",
        html,
        flags=re.I,
    )
    html = re.sub(
        r"\sdata-img-id\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
        "",
        html,
        flags=re.I,
    )
    html = re.sub(
        r"\scontenteditable(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?",
        "",
        html,
        flags=re.I,
    )

    # Strip renderer classes.
    class_attr_re = re.compile(r"(\s+)class\s*=\s*(['\"])(.*?)\2", flags=re.I | re.S)

    def strip_classes(match: re.Match[str]) -> str:
        leading = match.group(1)
        quote = match.group(2)
        classes_raw = match.group(3) or ""
        classes = [c for c in re.split(r"\s+", classes_raw.strip()) if c]
        filtered = [c for c in classes if c not in _EDITABLE_CLASS_NAMES]
        if not filtered:
            return ""
        return f'{leading}class={quote}{" ".join(filtered)}{quote}'

    html = class_attr_re.sub(strip_classes, html)

    return html


@router.get("/slide-proxy", response_class=HTMLResponse)
async def slide_proxy_design_mode(
    current_user: CurrentUser,
    session_id: str = Query(..., description="Session ID"),
    presentation_name: str = Query(..., description="Presentation name"),
    slide_number: int = Query(..., description="Slide number (1-based)"),
) -> HTMLResponse:
    """
    Proxy endpoint that fetches slide HTML from database and injects design mode runtime.
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

        html = _sanitize_legacy_editable_artifacts(slide.slide_content or "")
        if not html.strip():
            raise HTTPException(status_code=404, detail="Slide has no content")

        modified_html = _inject_runtime_script_only(html)

        return HTMLResponse(
            content=modified_html,
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )


@router.get("/slide-deck-proxy", response_class=HTMLResponse)
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

        deck_html = build_slide_deck_html(
            [
                (
                    int(getattr(slide, "slide_number", 0) or 0),
                    _sanitize_legacy_editable_artifacts(slide.slide_content or ""),
                )
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


@router.post("/slide-sync-batch", response_model=SlideSyncBatchResponse)
async def slide_sync_batch(
    request: SlideSyncBatchRequest,
    current_user: CurrentUser,
) -> SlideSyncBatchResponse:
    """
    Apply design mode changes to a slide in the database.
    """

    from sqlalchemy import select, and_
    from ii_agent.db.models import SlideContent, Session

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
            raise HTTPException(status_code=404, detail="Slide not found")

        html = slide.slide_content or ""
        if not html.strip():
            raise HTTPException(status_code=404, detail="Slide has no content")

        processed = 0
        failed = 0
        errors: List[str] = []
        modified_html = html

        for change in request.changes:
            try:
                new_value = change.value.get("to", "")
                design_id = change.design_id

                if change.type == "style":
                    modified_html = apply_slide_style_change(
                        modified_html, design_id, change.property, new_value or ""
                    )
                    processed += 1
                elif change.type == "text":
                    modified_html = apply_slide_text_change(
                        modified_html, design_id, new_value or ""
                    )
                    processed += 1
                elif change.type == "attribute" and change.property == "icon":
                    modified_html = apply_slide_icon_change(
                        modified_html, design_id, new_value or ""
                    )
                    processed += 1
                else:
                    failed += 1
                    errors.append(f"Unknown change type: {change.type}")
            except Exception as exc:
                logger.error("Failed to apply change for %s: %s", change.design_id, exc)
                failed += 1
                errors.append(f"Failed: {change.design_id}: {str(exc)}")

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


@router.post("/slide-deck-sync-batch", response_model=SlideDeckSyncBatchResponse)
async def slide_deck_sync_batch(
    request: SlideDeckSyncBatchRequest,
    current_user: CurrentUser,
) -> SlideDeckSyncBatchResponse:
    """
    Apply design mode changes across multiple slides in the database.
    """

    from sqlalchemy import select, and_
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
                        modified_html = apply_slide_style_change(
                            modified_html, design_id, change.property, new_value or ""
                        )
                        processed += 1
                    elif change.type == "text":
                        modified_html = apply_slide_text_change(
                            modified_html, design_id, new_value or ""
                        )
                        processed += 1
                    elif change.type == "attribute" and change.property == "icon":
                        modified_html = apply_slide_icon_change(
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


@router.post("/slide-deck-sync-state", response_model=SlideDeckSyncStateResponse)
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

        safe_name = sanitize_slide_presentation_name(request.presentation_name)
        presentation_dir = f"/workspace/presentations/{safe_name}"

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
                    modified_html, did_apply = apply_slide_style_change_with_status(
                        html, change.designId, change.property, new_value or ""
                    )
                elif change.type == "text":
                    modified_html, did_apply = apply_slide_text_change_with_status(
                        html, change.designId, new_value or ""
                    )
                elif change.type == "attribute" and change.property == "icon":
                    modified_html, did_apply = apply_slide_icon_change_with_status(
                        html, change.designId, new_value or ""
                    )
                elif change.type == "delete":
                    modified_html, did_apply = _apply_delete_change_by_design_id(
                        content=html,
                        file_path=f"slide_{slide_number_int}",
                        design_id=change.designId,
                    )
                elif change.type == "move":
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

                    if (
                        new_value == "only"
                        or new_value.startswith("before:")
                        or new_value.startswith("after:")
                    ):
                        if new_value == "only":
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

        try:
            sandbox = await _get_v1_sandbox_for_session(session_uuid)
            await sandbox.run_cmd(f"mkdir -p {shlex.quote(presentation_dir)}")
        except Exception as exc:
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
                    "[SlideDesignMode] Failed to write metadata.json: %s", exc
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
            logger.warning("[SlideDesignMode Sync] Errors during sync: %s", errors[:10])

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
