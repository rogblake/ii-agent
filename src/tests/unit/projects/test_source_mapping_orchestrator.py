"""Unit tests for source_mapping_sync/_orchestrator.py."""

from __future__ import annotations

import uuid
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from ii_agent.projects.design.schemas import ElementContext, StyleChange
from ii_agent.projects.design.source_mapping_sync._orchestrator import (
    _apply_changes_with_source_mapping,
    _emit_design_mode_sync_progress,
    _emit_sync_progress,
    apply_changes_with_source_mapping,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_element_context(**kwargs) -> ElementContext:
    defaults = {
        "designId": "did-1",
        "tagName": "div",
        "className": "container",
        "textContent": None,
        "outerHTML": None,
        "reactSource": None,
    }
    defaults.update(kwargs)
    return ElementContext(**defaults)


def _make_style_change(
    design_id: str = "did-1",
    change_type: str = "style",
    prop: str = "color",
    value: dict | None = None,
    element_context: ElementContext | None = None,
) -> StyleChange:
    return StyleChange(
        designId=design_id,
        type=change_type,
        property=prop,
        value=value if value is not None else {"to": "red"},
        timestamp=1234567890,
        elementContext=element_context,
    )


def _make_sandbox(
    search_output: str = "",
    file_content: str = "",
    write_raises: Exception | None = None,
) -> MagicMock:
    """Build a sandbox mock with sensible defaults."""
    sandbox = MagicMock()
    sandbox.run_command = AsyncMock(return_value=search_output)
    sandbox.read_file = AsyncMock(return_value=file_content)
    if write_raises:
        sandbox.write_file = AsyncMock(side_effect=write_raises)
    else:
        sandbox.write_file = AsyncMock(return_value=None)
    return sandbox


def _content_with_design_id(design_id: str, tag: str = "div") -> str:
    return f'<{tag} data-design-id="{design_id}" className="foo">Content</{tag}>'


# ---------------------------------------------------------------------------
# _emit_sync_progress
# ---------------------------------------------------------------------------


class TestEmitSyncProgress:
    @pytest.mark.asyncio
    async def test_does_nothing_when_emit_progress_is_none(self):
        # Should not raise when emit_progress is None
        await _emit_sync_progress(
            emit_progress=None,
            session_id=None,
            processed=1,
            total=5,
            applied=1,
            errors=0,
        )

    @pytest.mark.asyncio
    async def test_calls_emit_progress_with_correct_args(self):
        emit_progress = AsyncMock()
        session_id = uuid.uuid4()
        await _emit_sync_progress(
            emit_progress=emit_progress,
            session_id=session_id,
            processed=2,
            total=10,
            applied=1,
            errors=1,
            current=3,
            done=False,
        )
        emit_progress.assert_called_once_with(
            session_id=session_id,
            processed=2,
            total=10,
            applied=1,
            errors=1,
            current=3,
            done=False,
        )

    @pytest.mark.asyncio
    async def test_calls_emit_progress_done(self):
        emit_progress = AsyncMock()
        await _emit_sync_progress(
            emit_progress=emit_progress,
            session_id=None,
            processed=5,
            total=5,
            applied=5,
            errors=0,
            current=None,
            done=True,
        )
        call_kwargs = emit_progress.call_args[1]
        assert call_kwargs["done"] is True
        assert call_kwargs["current"] is None


# ---------------------------------------------------------------------------
# _emit_design_mode_sync_progress
# ---------------------------------------------------------------------------


class TestEmitDesignModeSyncProgress:
    @pytest.mark.asyncio
    async def test_delegates_to_emit_sync_progress(self):
        emit_progress = AsyncMock()
        session_id = uuid.uuid4()
        await _emit_design_mode_sync_progress(
            emit_progress=emit_progress,
            session_id=session_id,
            processed=1,
            total=5,
            applied=1,
            errors=0,
            done=True,
        )
        emit_progress.assert_called_once()

    @pytest.mark.asyncio
    async def test_works_with_none_emit_progress(self):
        await _emit_design_mode_sync_progress(
            emit_progress=None,
            session_id=None,
            processed=0,
            total=0,
            applied=0,
            errors=0,
        )


# ---------------------------------------------------------------------------
# apply_changes_with_source_mapping (public facade)
# ---------------------------------------------------------------------------


class TestApplyChangesWithSourceMappingFacade:
    @pytest.mark.asyncio
    async def test_delegates_to_internal(self):
        """The public facade should call the internal function."""
        with patch(
            "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_changes_with_source_mapping",
            new=AsyncMock(return_value=(1, [], [])),
        ) as mock_internal:
            sandbox = _make_sandbox()
            changes = [_make_style_change()]
            session_id = uuid.uuid4()

            result = await apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=changes,
                session_id=session_id,
            )

            mock_internal.assert_called_once_with(
                sandbox=sandbox,
                changes=changes,
                session_id=session_id,
                emit_progress=None,
            )
            assert result == (1, [], [])


# ---------------------------------------------------------------------------
# _apply_changes_with_source_mapping - core orchestration
# ---------------------------------------------------------------------------


class TestApplyChangesWithSourceMapping:
    @pytest.mark.asyncio
    async def test_empty_changes_returns_zero_applied(self):
        sandbox = _make_sandbox()
        with patch(
            "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
            new=AsyncMock(return_value=(None, {})),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[],
            )
        assert applied == 0
        assert errors == []
        assert remaining == []

    @pytest.mark.asyncio
    async def test_change_without_design_id_added_to_remaining(self):
        change = _make_style_change(design_id="", element_context=None)
        # The designId field is required in the model, so set it empty via override.
        change.designId = ""

        sandbox = _make_sandbox()
        with patch(
            "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
            new=AsyncMock(return_value=(None, {})),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )
        assert applied == 0
        assert len(remaining) == 1
        assert any("designId" in e for e in errors)

    @pytest.mark.asyncio
    async def test_uses_manifest_file_path_when_available(self):
        design_id = "did-manifest"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(design_id=design_id)

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(file_path, {design_id: [file_path]})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_by_design_id",
                return_value=("updated content", True),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 1
        assert remaining == []

    @pytest.mark.asyncio
    async def test_falls_back_to_workspace_search_when_not_in_manifest(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(design_id=design_id)

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {design_id: [file_path, "other.tsx"]})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_by_design_id",
                return_value=("updated content", True),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )
        assert applied == 1

    @pytest.mark.asyncio
    async def test_file_read_failure_adds_to_remaining(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        change = _make_style_change(design_id=design_id)

        sandbox = _make_sandbox()

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(side_effect=IOError("disk error")),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 0
        assert len(remaining) == 1
        assert any("Failed to read" in e for e in errors)

    @pytest.mark.asyncio
    async def test_missing_style_to_value_adds_to_remaining(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(design_id=design_id, value={})  # No "to" key

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 0
        assert len(remaining) == 1
        assert any("to' value" in e for e in errors)

    @pytest.mark.asyncio
    async def test_write_failure_adds_to_remaining(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(design_id=design_id)

        sandbox = _make_sandbox(
            file_content=content,
            write_raises=IOError("disk full"),
        )

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_by_design_id",
                return_value=("updated content", True),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 0
        assert len(remaining) == 1
        assert any("Failed to write" in e for e in errors)

    @pytest.mark.asyncio
    async def test_mismatch_guard_adds_to_remaining(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(design_id=design_id)

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(False, "tag mismatch"),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_as_css_override",
                new=AsyncMock(return_value=(False, None)),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 0
        assert len(remaining) == 1

    @pytest.mark.asyncio
    async def test_mismatch_bypassed_via_css_override(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(design_id=design_id)

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(False, "tag mismatch"),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_as_css_override",
                new=AsyncMock(return_value=(True, "/workspace/src/globals.css")),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 1
        assert remaining == []

    @pytest.mark.asyncio
    async def test_unsupported_change_type_adds_to_remaining(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(design_id=design_id, change_type="unsupported")

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 0
        assert len(remaining) == 1
        assert any("Unsupported" in e for e in errors)

    @pytest.mark.asyncio
    async def test_text_change_missing_from_to_adds_to_remaining(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(
            design_id=design_id,
            change_type="text",
            value={"to": "New"},  # Missing "from"
        )

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 0
        assert len(remaining) == 1
        assert any("from/to" in e for e in errors)

    @pytest.mark.asyncio
    async def test_delete_change_applied_successfully(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = f'<div>\n  <p data-design-id="{design_id}">Delete me</p>\n</div>'
        change = _make_style_change(design_id=design_id, change_type="delete")

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_delete_change_by_design_id",
                return_value=("updated content", True),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 1
        assert remaining == []

    @pytest.mark.asyncio
    async def test_move_change_with_only_anchor(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(
            design_id=design_id,
            change_type="move",
            value={"to": "only"},
        )

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 1
        assert remaining == []

    @pytest.mark.asyncio
    async def test_move_change_with_missing_to_value_adds_to_remaining(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(
            design_id=design_id,
            change_type="move",
            value={},  # No "to"
        )

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 0
        assert len(remaining) == 1
        assert any("move target" in e for e in errors)

    @pytest.mark.asyncio
    async def test_emit_progress_called_at_start_and_end(self):
        emit_progress = AsyncMock()

        sandbox = _make_sandbox()
        with patch(
            "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
            new=AsyncMock(return_value=(None, {})),
        ):
            await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[],
                emit_progress=emit_progress,
            )

        # At minimum: initial call + done call
        assert emit_progress.call_count >= 2
        final_call_kwargs = emit_progress.call_args[1]
        assert final_call_kwargs["done"] is True
        assert final_call_kwargs["processed"] == 0

    @pytest.mark.asyncio
    async def test_manifest_load_failure_continues_with_empty_manifest(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(design_id=design_id)

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(side_effect=Exception("manifest error")),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_by_design_id",
                return_value=("updated", True),
            ),
        ):
            # Should not raise even though manifest load fails.
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 1

    @pytest.mark.asyncio
    async def test_backfill_attempted_when_design_id_not_found(self):
        design_id = "did-backfill"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        ctx = _make_element_context(designId=design_id)
        change = _make_style_change(design_id=design_id, element_context=ctx)

        sandbox = _make_sandbox(file_content=content)
        backfilled_content = (
            f'<div data-design-id="{design_id}" className="foo">Content</div>'
        )

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=None),  # Not found in workspace
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._backfill_design_id_in_source_from_react_source",
                new=AsyncMock(return_value=(file_path, backfilled_content)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(backfilled_content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_by_design_id",
                return_value=("updated", True),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 1

    @pytest.mark.asyncio
    async def test_icon_change_with_missing_payload_adds_to_remaining(self):
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(
            design_id=design_id,
            change_type="attribute",
            prop="icon",
            value={"to": None},  # Missing payload
        )

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 0
        assert len(remaining) == 1
        assert any("icon payload" in e for e in errors)

    @pytest.mark.asyncio
    async def test_multiple_changes_processed(self):
        """Test that multiple changes are processed and progress is tracked."""
        file_path = "/workspace/src/App.tsx"

        changes = [
            _make_style_change(design_id=f"did-{i}") for i in range(3)
        ]

        def make_content(design_id: str) -> str:
            return _content_with_design_id(design_id)

        sandbox = _make_sandbox()
        emit_progress = AsyncMock()

        call_count = 0

        async def mock_find_best(*args, **kwargs) -> str:
            return file_path

        async def mock_read(*args, **kwargs):
            nonlocal call_count
            design_id = f"did-{call_count % 3}"
            call_count += 1
            return make_content(design_id), file_path

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(side_effect=mock_find_best),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(side_effect=mock_read),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_by_design_id",
                return_value=("updated", True),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=changes,
                emit_progress=emit_progress,
            )

        assert applied == 3
        assert remaining == []

    @pytest.mark.asyncio
    async def test_manifest_drift_triggers_workspace_search(self):
        """When manifest file doesn't contain the design ID, falls back to workspace search."""
        design_id = "did-1"
        manifest_path = "/workspace/project/design-mode.manifest.json"
        file_path = "/workspace/project/src/App.tsx"
        # Content does NOT have the design ID (simulating drift).
        content_without_id = "<div className='foo'>Content</div>"
        content_with_id = _content_with_design_id(design_id)

        change = _make_style_change(design_id=design_id)
        sandbox = _make_sandbox()

        read_side_effects = [
            (content_without_id, file_path),  # First read from manifest path (drift)
            (content_with_id, file_path),  # Second read after workspace search
        ]

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(manifest_path, {design_id: [file_path]})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(side_effect=read_side_effects),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_by_design_id",
                return_value=("updated", True),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 1

    @pytest.mark.asyncio
    async def test_css_override_fallback_when_apply_fails(self):
        """When style apply fails, falls back to CSS override."""
        design_id = "did-1"
        file_path = "/workspace/src/App.tsx"
        content = _content_with_design_id(design_id)
        change = _make_style_change(design_id=design_id)

        sandbox = _make_sandbox(file_content=content)

        with (
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
                new=AsyncMock(return_value=(None, {})),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._find_best_source_file_for_design_id",
                new=AsyncMock(return_value=file_path),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._read_file_with_workspace_fallback",
                new=AsyncMock(return_value=(content, file_path)),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._verify_design_mode_target_matches_context",
                return_value=(True, ""),
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_by_design_id",
                return_value=(content, False),  # Apply failed
            ),
            patch(
                "ii_agent.projects.design.source_mapping_sync._orchestrator._apply_style_change_as_css_override",
                new=AsyncMock(return_value=(True, "/workspace/src/globals.css")),
            ),
        ):
            applied, errors, remaining = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[change],
            )

        assert applied == 1
        assert remaining == []

    @pytest.mark.asyncio
    async def test_returns_correct_tuple_structure(self):
        """Return value should be (int, List[str], List[StyleChange])."""
        sandbox = _make_sandbox()
        with patch(
            "ii_agent.projects.design.source_mapping_sync._orchestrator._load_design_mode_manifest_mapping",
            new=AsyncMock(return_value=(None, {})),
        ):
            result = await _apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=[],
            )

        assert isinstance(result, tuple)
        assert len(result) == 3
        applied_count, errors, remaining = result
        assert isinstance(applied_count, int)
        assert isinstance(errors, list)
        assert isinstance(remaining, list)
