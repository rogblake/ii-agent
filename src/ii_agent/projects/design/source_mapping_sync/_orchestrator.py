"""Main orchestration loop for source-mapping sync."""

from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ii_agent.core.logger import logger
from ii_agent.projects.design.schemas import StyleChange
from ii_agent.projects.design.source_mapping_sync._constants import (
    DESIGN_MODE_MANIFEST_FILENAME,
    _truncate_for_log,
)
from ii_agent.projects.design.source_mapping_sync._backfill import (
    _backfill_design_id_in_source_from_class_name,
    _backfill_design_id_in_source_from_component_callsite,
    _backfill_design_id_in_source_from_react_source,
    _backfill_design_id_in_source_from_text_search,
)
from ii_agent.projects.design.source_mapping_sync._manifest import (
    _load_design_mode_manifest_mapping,
)
from ii_agent.projects.design.source_mapping_sync._mutations import (
    _apply_delete_change_by_design_id,
    _apply_icon_change_by_design_id,
    _apply_icon_change_by_item_id_assignment,
    _apply_move_change_by_design_id_anchor,
    _apply_style_change_as_css_override,
    _apply_style_change_by_design_id,
    _apply_swap_change_by_design_ids,
    _apply_text_change_by_design_id,
    _extract_icon_name_from_change,
    _extract_icon_payload_from_change,
    _extract_item_id_from_icon_design_id,
    _find_best_source_file_for_design_id,
    _find_best_source_file_for_icon_item_id,
    _find_icon_by_dynamic_pattern,
)
from ii_agent.projects.design.source_mapping_sync._tag_utils import (
    _find_opening_tag_bounds_for_design_id,
)
from ii_agent.projects.design.source_mapping_sync._verify import (
    _verify_design_mode_target_matches_context,
)
from ii_agent.projects.design.source_mapping_sync._workspace import (
    _read_file_with_workspace_fallback,
)


async def _emit_sync_progress(
    *,
    emit_progress: Optional[Callable[..., Awaitable[None]]],
    session_id: Optional[uuid.UUID],
    processed: int,
    total: int,
    applied: int,
    errors: int,
    current: Optional[int] = None,
    done: bool = False,
) -> None:
    if emit_progress is None:
        return
    await emit_progress(
        session_id=session_id,
        processed=processed,
        total=total,
        applied=applied,
        errors=errors,
        current=current,
        done=done,
    )


async def _emit_design_mode_sync_progress(
    *,
    emit_progress: Optional[Callable[..., Awaitable[None]]],
    session_id: Optional[uuid.UUID],
    processed: int,
    total: int,
    applied: int,
    errors: int,
    current: Optional[int] = None,
    done: bool = False,
) -> None:
    await _emit_sync_progress(
        emit_progress=emit_progress,
        session_id=session_id,
        processed=processed,
        total=total,
        applied=applied,
        errors=errors,
        current=current,
        done=done,
    )


async def _apply_changes_with_source_mapping(
    *,
    sandbox: Any,
    changes: List[StyleChange],
    session_id: Optional[uuid.UUID] = None,
    emit_progress: Optional[Callable[..., Awaitable[None]]] = None,
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
        emit_progress=emit_progress,
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
            emit_progress=emit_progress,
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
                                    await sandbox.write_file(
                                        cand_resolved_path, updated_candidate
                                    )
                                    ok = True
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
            await sandbox.write_file(resolved_path, updated_content)
            ok = True
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
        emit_progress=emit_progress,
        session_id=session_id,
        processed=len(changes),
        total=len(changes),
        applied=applied_count,
        errors=len(errors),
        current=None,
        done=True,
    )
    return applied_count, errors, remaining


async def apply_changes_with_source_mapping(
    *,
    sandbox: Any,
    changes: List[StyleChange],
    session_id: Optional[uuid.UUID] = None,
    emit_progress: Optional[Callable[..., Awaitable[None]]] = None,
) -> tuple[int, List[str], List[StyleChange]]:
    return await _apply_changes_with_source_mapping(
        sandbox=sandbox,
        changes=changes,
        session_id=session_id,
        emit_progress=emit_progress,
    )
