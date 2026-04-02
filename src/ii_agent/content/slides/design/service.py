"""Service layer for slide design domain - business logic only."""

from __future__ import annotations

import json
import shlex
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings
from ii_agent.core.logger import logger
from ii_agent.projects.design.utils.deck_builder import build_slide_deck_html
from ii_agent.projects.design.utils.html_patch import (
    apply_slide_icon_change,
    apply_slide_style_change,
    apply_slide_text_change,
    apply_slide_delete_change_with_status,
    apply_slide_icon_change_with_status,
    apply_slide_move_change_with_status,
    apply_slide_style_change_with_status,
    apply_slide_swap_change_with_status,
    apply_slide_text_change_with_status,
    sanitize_slide_presentation_name,
)
from ii_agent.projects.design.utils.runtime_injector import (
    inject_runtime_script_only,
    sanitize_legacy_editable_artifacts,
)
from ii_agent.projects.design.exceptions import (
    DesignSandboxUnavailableError,
    DesignSessionNotFoundError,
    DesignSessionAccessDeniedError,
    DesignValidationError,
)
from ii_agent.projects.design.models import DesignSyncCounters, PersistedDesignSyncResult
from ii_agent.projects.design.schemas import StyleChange
from ii_agent.content.slides.design.exceptions import DesignSlideNotFoundError
from ii_agent.content.slides.design.repository import SlideDesignRepository
from ii_agent.content.slides.design.schemas import (
    SlideDeckSyncBatchRequest,
    SlideDeckSyncBatchResponse,
    SlideDeckSyncStateRequest,
    SlideDeckSyncStateResponse,
    SlideSyncBatchRequest,
    SlideSyncBatchResponse,
)
from ii_agent.agents.sandboxes.service import SandboxService

ProgressCallback = Callable[..., Awaitable[None]]
SummaryCallback = Callable[[str], Awaitable[str | None]]


class SlideDesignService:
    """Domain service for slide design mode workflows."""

    def __init__(
        self,
        *,
        repo: SlideDesignRepository,
        sandbox_service: SandboxService,
        config: Settings,
    ) -> None:
        self._repo = repo
        self._sandbox_service = sandbox_service
        self._config = config

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_session_for_request(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        user_id: str,
    ) -> Any:
        session = await self._repo.get_session(db, session_id=session_id)
        if not session:
            raise DesignSessionNotFoundError("Session not found")
        if str(getattr(session, "user_id", "")) != str(user_id):
            raise DesignSessionAccessDeniedError("Access denied")
        return session

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def get_slide_proxy_html(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        user_id: str,
        presentation_name: str,
        slide_number: int,
    ) -> str:
        if not await self._repo.get_session_for_user(
            db,
            session_id=session_id,
            user_id=user_id,
        ):
            raise DesignSessionNotFoundError("Session not found or access denied")

        slide = await self._repo.get_slide(
            db,
            session_id=session_id,
            presentation_name=presentation_name,
            slide_number=slide_number,
        )
        if not slide:
            raise DesignSlideNotFoundError(
                f"Slide {slide_number} not found in presentation '{presentation_name}'"
            )
        html = sanitize_legacy_editable_artifacts(slide.slide_content or "")
        if not html.strip():
            raise DesignSlideNotFoundError("Slide has no content")
        return inject_runtime_script_only(html)

    async def get_slide_deck_proxy_html(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        user_id: str,
        presentation_name: str,
    ) -> str:
        if not await self._repo.get_session_for_user(
            db,
            session_id=session_id,
            user_id=user_id,
        ):
            raise DesignSessionNotFoundError("Session not found or access denied")

        slides = await self._repo.get_presentation_slides(
            db,
            session_id=session_id,
            presentation_name=presentation_name,
        )
        if not slides:
            raise DesignSlideNotFoundError("No slides found")

        deck_html = build_slide_deck_html(
            [
                (
                    int(getattr(slide, "slide_number", 0) or 0),
                    sanitize_legacy_editable_artifacts(slide.slide_content or ""),
                )
                for slide in slides
            ]
        )
        return inject_runtime_script_only(deck_html)

    async def apply_slide_sync_batch(
        self,
        db: AsyncSession,
        *,
        request: SlideSyncBatchRequest,
        user_id: str,
    ) -> SlideSyncBatchResponse:
        if not await self._repo.get_session_for_user(
            db,
            session_id=request.session_id,
            user_id=user_id,
        ):
            raise DesignSessionNotFoundError("Session not found or access denied")

        slide = await self._repo.get_slide(
            db,
            session_id=request.session_id,
            presentation_name=request.presentation_name,
            slide_number=request.slide_number,
        )
        if not slide:
            raise DesignSlideNotFoundError("Slide not found")

        html = slide.slide_content or ""
        if not html.strip():
            raise DesignSlideNotFoundError("Slide has no content")

        counters = DesignSyncCounters()
        modified_html = html

        for change in request.changes:
            try:
                new_value = (change.value or {}).get("to") or ""
                design_id = change.design_id
                if change.type == "style":
                    modified_html = apply_slide_style_change(
                        modified_html,
                        design_id,
                        change.property,
                        new_value,
                    )
                    counters.processed += 1
                elif change.type == "text":
                    modified_html = apply_slide_text_change(
                        modified_html,
                        design_id,
                        new_value,
                    )
                    counters.processed += 1
                elif change.type == "attribute" and change.property == "icon":
                    modified_html = apply_slide_icon_change(
                        modified_html,
                        design_id,
                        new_value,
                    )
                    counters.processed += 1
                else:
                    counters.failed += 1
                    counters.errors.append(f"Unknown change type: {change.type}")
            except Exception as exc:
                counters.failed += 1
                counters.errors.append(f"Failed: {change.design_id}: {exc}")

        if modified_html != html:
            await self._repo.update_slide_html(
                db,
                slide=slide,
                html=modified_html,
                mark_synced=True,
            )

        return SlideSyncBatchResponse(
            success=counters.failed == 0,
            processed=counters.processed,
            failed=counters.failed,
            errors=counters.errors,
        )

    async def apply_slide_deck_sync_batch(
        self,
        db: AsyncSession,
        *,
        request: SlideDeckSyncBatchRequest,
        user_id: str,
    ) -> SlideDeckSyncBatchResponse:
        if not request.changes:
            return SlideDeckSyncBatchResponse(success=True, processed=0, failed=0, errors=[])

        if not await self._repo.get_session_for_user(
            db,
            session_id=request.session_id,
            user_id=user_id,
        ):
            raise DesignSessionNotFoundError("Session not found or access denied")

        slides = await self._repo.get_presentation_slides(
            db,
            session_id=request.session_id,
            presentation_name=request.presentation_name,
        )
        slide_by_number = {
            int(slide.slide_number): slide
            for slide in slides
            if getattr(slide, "slide_number", None) is not None
        }

        counters = DesignSyncCounters()
        changes_by_slide: dict[int, list[Any]] = defaultdict(list)
        for change in request.changes:
            if change.slide_number <= 0:
                counters.failed += 1
                counters.errors.append(f"Invalid slide number for {change.design_id}")
                continue
            changes_by_slide[int(change.slide_number)].append(change)

        for slide_number, slide_changes in changes_by_slide.items():
            slide = slide_by_number.get(slide_number)
            if not slide:
                counters.failed += len(slide_changes)
                counters.errors.append(f"Slide {slide_number} not found")
                continue
            html = slide.slide_content or ""
            if not html.strip():
                counters.failed += len(slide_changes)
                counters.errors.append(f"Slide {slide_number} has no content")
                continue

            modified_html = html
            for change in slide_changes:
                try:
                    new_value = (change.value or {}).get("to") or ""
                    design_id = change.design_id
                    if change.type == "style":
                        modified_html = apply_slide_style_change(
                            modified_html,
                            design_id,
                            change.property,
                            new_value,
                        )
                        counters.processed += 1
                    elif change.type == "text":
                        modified_html = apply_slide_text_change(
                            modified_html,
                            design_id,
                            new_value,
                        )
                        counters.processed += 1
                    elif change.type == "attribute" and change.property == "icon":
                        modified_html = apply_slide_icon_change(
                            modified_html,
                            design_id,
                            new_value,
                        )
                        counters.processed += 1
                    else:
                        counters.failed += 1
                        counters.errors.append(f"Unknown change type: {change.type}")
                except Exception as exc:
                    counters.failed += 1
                    counters.errors.append(f"Failed slide {slide_number} {change.design_id}: {exc}")

            if modified_html != html:
                await self._repo.update_slide_html(
                    db,
                    slide=slide,
                    html=modified_html,
                    mark_synced=True,
                )

        return SlideDeckSyncBatchResponse(
            success=counters.failed == 0,
            processed=counters.processed,
            failed=counters.failed,
            errors=counters.errors,
        )

    async def sync_persisted_slide_deck_changes(
        self,
        db: AsyncSession,
        *,
        request: SlideDeckSyncStateRequest,
        user_id: str,
        on_progress: ProgressCallback | None = None,
        on_summary: SummaryCallback | None = None,
    ) -> SlideDeckSyncStateResponse:
        session = await self._get_session_for_request(
            db,
            session_id=request.session_id,
            user_id=user_id,
        )

        session_uuid = request.session_id
        if not isinstance(session_uuid, uuid.UUID):
            raise DesignValidationError("Invalid session_id")

        raw_changes, raw_redo, _ = self._repo.get_design_state(session)
        changes = self._parse_persisted_design_changes(raw_changes)
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

        slides = await self._repo.get_presentation_slides(
            db,
            session_id=request.session_id,
            presentation_name=request.presentation_name,
        )
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
            int(slide.slide_number): slide
            for slide in slides
            if getattr(slide, "slide_number", None) is not None
        }

        counters = DesignSyncCounters()
        applied_candidate_indexes_by_slide: dict[int, list[int]] = defaultdict(list)

        if on_progress:
            await on_progress(
                session_id=session_uuid,
                processed=0,
                total=total,
                applied=0,
                errors=0,
                current=1,
                done=False,
            )

        for idx, change in enumerate(changes):
            if on_progress:
                await on_progress(
                    session_id=session_uuid,
                    processed=idx,
                    total=total,
                    applied=counters.applied,
                    errors=counters.failed,
                    current=idx + 1,
                    done=False,
                )
            counters.processed += 1

            slide_number = self._extract_slide_number(change)
            if slide_number <= 0:
                counters.failed += 1
                counters.errors.append(f"Change {idx + 1}: Missing slideNumber")
                continue

            slide = slide_by_number.get(slide_number)
            if not slide:
                counters.failed += 1
                counters.errors.append(f"Change {idx + 1}: Slide {slide_number} not found")
                continue

            html = slide.slide_content or ""
            if not html.strip():
                counters.failed += 1
                counters.errors.append(f"Change {idx + 1}: Slide {slide_number} has no content")
                continue

            new_value = ""
            if isinstance(change.value, dict):
                maybe_to = change.value.get("to")
                if isinstance(maybe_to, str):
                    new_value = maybe_to

            xpath = change.elementContext.xpath if change.elementContext else None
            changed_html, did_apply, reason = self._apply_single_change(
                html,
                design_id=change.designId,
                change_type=change.type,
                property_name=change.property,
                new_value=new_value,
                xpath=xpath,
                slide_number=slide_number,
            )
            if not did_apply:
                counters.failed += 1
                counters.errors.append(
                    reason
                    or (
                        f"Change {idx + 1}: Could not locate "
                        f"design_id={change.designId} on slide {slide_number}"
                    )
                )
                continue

            if changed_html != html:
                await self._repo.update_slide_html(
                    db,
                    slide=slide,
                    html=changed_html,
                    mark_synced=True,
                )
            applied_candidate_indexes_by_slide[slide_number].append(idx)

        synced_indexes: set[int] = set()
        sandbox_error = None
        if applied_candidate_indexes_by_slide:
            try:
                sandbox = await self._sandbox_service.get_sandbox_by_session_id(
                    db, session_id=session_uuid
                )
                if not sandbox:
                    raise DesignSandboxUnavailableError(
                        f"No active sandbox found for session {request.session_id}"
                    )
                safe_name = sanitize_slide_presentation_name(request.presentation_name)
                presentation_dir = f"{self._config.workspace_path}/presentations/{safe_name}"
                await sandbox.run_command(f"mkdir -p {shlex.quote(presentation_dir)}")

                # Keep sandbox deck files complete by writing every slide, while counting
                # applied changes only for slides that had successful mutations in this run.
                for slide in slides:
                    slide_number = int(getattr(slide, "slide_number", 0) or 0)
                    if slide_number <= 0:
                        continue
                    indexes = applied_candidate_indexes_by_slide.get(slide_number, [])
                    filename = f"slide_{slide_number:03d}.html"
                    file_path = f"{presentation_dir}/{filename}"
                    try:
                        await sandbox.write_file(file_path, slide.slide_content or "")
                        if indexes:
                            synced_indexes.update(indexes)
                    except Exception as exc:
                        counters.errors.append(
                            f"Failed to write slide {slide_number} to sandbox: {exc}"
                        )
                        if indexes:
                            counters.failed += len(indexes)

                try:
                    await self._write_presentation_metadata(
                        sandbox=sandbox,
                        presentation_dir=presentation_dir,
                        presentation_name=request.presentation_name,
                        safe_name=safe_name,
                        slides=slides,
                    )
                except Exception as exc:
                    logger.warning("[DesignMode] Failed writing metadata.json: {}", exc)
            except Exception as exc:
                sandbox_error = str(exc)
                counters.errors.append(f"Sandbox not available: {sandbox_error}")

        counters.applied = len(synced_indexes)
        remaining_changes = [
            change for idx, change in enumerate(changes) if idx not in synced_indexes
        ]

        updated_at = int(time.time() * 1000)
        await self._repo.update_design_state(
            db,
            session=session,
            changes=[change.model_dump() for change in remaining_changes],
            redo_changes=[c for c in raw_redo if isinstance(c, dict)],
            updated_at=updated_at,
        )

        if on_progress:
            await on_progress(
                session_id=session_uuid,
                processed=total,
                total=total,
                applied=counters.applied,
                errors=counters.failed,
                current=None,
                done=True,
            )

        result = self._build_persisted_sync_result(
            total=total,
            applied=counters.applied,
            remaining_changes=remaining_changes,
            errors=counters.errors,
            sandbox_error=sandbox_error,
        )

        if on_summary:
            event_id = await on_summary(result.summary)
            result.event_id = event_id

        return SlideDeckSyncStateResponse(
            success=result.success,
            applied=result.applied,
            total=result.total,
            remaining=len(result.remaining_changes),
            errors=result.errors,
            summary=result.summary,
            remaining_changes=result.remaining_changes,
            event_id=result.event_id,
        )

    # ------------------------------------------------------------------
    # Private / static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_single_change(
        html: str,
        *,
        design_id: str,
        change_type: str,
        property_name: str,
        new_value: str,
        xpath: Optional[str] = None,
        slide_number: Optional[int] = None,
    ) -> tuple[str, bool, Optional[str]]:
        try:
            if change_type == "style":
                updated, ok = apply_slide_style_change_with_status(
                    html,
                    design_id,
                    property_name,
                    new_value,
                    xpath=xpath,
                    slide_number=slide_number,
                )
                return updated, ok, None if ok else "Style target not found"
            if change_type == "text":
                updated, ok = apply_slide_text_change_with_status(
                    html,
                    design_id,
                    new_value,
                    xpath=xpath,
                    slide_number=slide_number,
                )
                return updated, ok, None if ok else "Text target not found"
            if change_type == "attribute" and property_name == "icon":
                updated, ok = apply_slide_icon_change_with_status(
                    html,
                    design_id,
                    new_value,
                    xpath=xpath,
                    slide_number=slide_number,
                )
                return updated, ok, None if ok else "Icon target not found"
            if change_type == "delete":
                updated, ok = apply_slide_delete_change_with_status(
                    html,
                    design_id=design_id,
                    file_path=f"slide_{slide_number or 0}",
                )
                return updated, ok, None if ok else "Delete target not found"
            if change_type == "move":
                updated, ok = apply_slide_move_change_with_status(
                    html,
                    design_id=design_id,
                    anchor=new_value,
                    file_path=f"slide_{slide_number or 0}",
                )
                return updated, ok, None if ok else "Move target not found"
            if change_type == "swap":
                updated, ok = apply_slide_swap_change_with_status(
                    html,
                    design_id=design_id,
                    target_design_id=new_value,
                    file_path=f"slide_{slide_number or 0}",
                )
                return updated, ok, None if ok else "Swap target not found"
            return html, False, f"Unsupported change type: {change_type}"
        except Exception as exc:
            logger.warning(
                "[DesignMode] Failed applying change design_id={} type={} property={}: {}",
                design_id,
                change_type,
                property_name,
                exc,
            )
            return html, False, str(exc)

    @staticmethod
    def _extract_slide_number(change: StyleChange) -> int:
        value = change.slideNumber
        if value is None and change.elementContext:
            value = change.elementContext.slideNumber
        try:
            return int(value)
        except Exception:
            return 0

    @staticmethod
    def _parse_persisted_design_changes(raw_changes: Any) -> list[StyleChange]:
        if not isinstance(raw_changes, list):
            return []
        parsed: list[StyleChange] = []
        for item in raw_changes:
            if not isinstance(item, dict):
                continue
            try:
                parsed.append(StyleChange.model_validate(item))
            except Exception:
                continue
        parsed.sort(key=lambda change: int(getattr(change, "timestamp", 0) or 0))
        return parsed

    def _build_persisted_sync_result(
        self,
        *,
        total: int,
        applied: int,
        remaining_changes: list[StyleChange],
        errors: list[str],
        sandbox_error: Optional[str],
    ) -> PersistedDesignSyncResult:
        remaining = len(remaining_changes)
        success = applied == total and remaining == 0 and not errors
        if success:
            summary = (
                f"Synced {applied} slide design change"
                f"{'' if applied == 1 else 's'} into your slide deck and sandbox."
            )
        elif applied > 0:
            summary = (
                f"Partially synced slide design changes: applied {applied}/{total}. "
                "Re-enter Design Mode to review pending changes and retry Save."
            )
        elif sandbox_error:
            summary = (
                "I could not sync slide changes because the sandbox was unavailable. "
                "Retry after sandbox is ready."
            )
        else:
            summary = (
                "I could not apply the saved slide design changes. "
                "Re-enter Design Mode to review pending changes and retry Save."
            )
        return PersistedDesignSyncResult(
            success=success,
            applied=applied,
            total=total,
            remaining_changes=remaining_changes,
            errors=errors,
            summary=summary,
        )

    async def _write_presentation_metadata(
        self,
        *,
        sandbox: Any,
        presentation_dir: str,
        presentation_name: str,
        safe_name: str,
        slides: list[Any],
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        metadata_path = f"{presentation_dir}/metadata.json"
        parsed: dict[str, Any] = {}
        try:
            existing_raw = await sandbox.read_file(metadata_path)
            if isinstance(existing_raw, str) and existing_raw.strip():
                parsed = json.loads(existing_raw)
        except Exception:
            parsed = {}

        presentation_meta = parsed.get("presentation") if isinstance(parsed, dict) else None
        if not isinstance(presentation_meta, dict):
            presentation_meta = {}
        if not presentation_meta.get("created_at"):
            presentation_meta["created_at"] = now_iso
        presentation_meta["updated_at"] = now_iso
        presentation_meta["name"] = presentation_name
        presentation_meta["title"] = presentation_name or "Untitled Presentation"
        presentation_meta.setdefault("description", "")

        previous_slides = {}
        slides_meta = parsed.get("slides") if isinstance(parsed, dict) else None
        if isinstance(slides_meta, list):
            for item in slides_meta:
                if not isinstance(item, dict):
                    continue
                number = item.get("number")
                if isinstance(number, int):
                    previous_slides[number] = item

        next_slides_meta = []
        for slide in slides:
            slide_number = int(slide.slide_number)
            filename = f"slide_{slide_number:03d}.html"
            previous = previous_slides.get(slide_number, {})
            created_at = previous.get("created_at") if isinstance(previous, dict) else None
            if not isinstance(created_at, str) or not created_at:
                created_at = now_iso
            next_slides_meta.append(
                {
                    "id": f"slide_{slide_number:03d}",
                    "number": slide_number,
                    "title": slide.slide_title or "",
                    "description": "",
                    "type": (
                        previous.get("type", "content") if isinstance(previous, dict) else "content"
                    ),
                    "filename": filename,
                    "file_path": f"presentations/{safe_name}/{filename}",
                    "preview_url": f"{self._config.workspace_path}/presentations/{safe_name}/{filename}",
                    "created_at": created_at,
                    "updated_at": now_iso,
                }
            )

        payload = {
            "presentation": presentation_meta,
            "slides": next_slides_meta,
        }
        await sandbox.write_file(
            metadata_path,
            json.dumps(payload, indent=2, ensure_ascii=False),
        )
