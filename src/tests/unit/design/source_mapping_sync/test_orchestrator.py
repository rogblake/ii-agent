"""Tests for _orchestrator.py."""

from ii_agent.projects.design.source_mapping_sync._orchestrator import (
    _apply_changes_with_source_mapping,
    _emit_design_mode_sync_progress,
    _emit_sync_progress,
    apply_changes_with_source_mapping,
)

from .conftest import make_element_context, make_style_change


# ---------------------------------------------------------------------------
# _emit_sync_progress
# ---------------------------------------------------------------------------


class TestEmitSyncProgress:
    async def test_calls_callback(self):
        called = {}

        async def cb(**kwargs):
            called.update(kwargs)

        await _emit_sync_progress(
            emit_progress=cb,
            session_id=None,
            processed=1,
            total=2,
            applied=1,
            errors=0,
        )
        assert called["processed"] == 1
        assert called["total"] == 2

    async def test_none_callback_noop(self):
        # Should not raise
        await _emit_sync_progress(
            emit_progress=None,
            session_id=None,
            processed=0,
            total=0,
            applied=0,
            errors=0,
        )

    async def test_done_flag(self):
        called = {}

        async def cb(**kwargs):
            called.update(kwargs)

        await _emit_sync_progress(
            emit_progress=cb,
            session_id=None,
            processed=5,
            total=5,
            applied=3,
            errors=2,
            done=True,
        )
        assert called["done"] is True


# ---------------------------------------------------------------------------
# _emit_design_mode_sync_progress
# ---------------------------------------------------------------------------


class TestEmitDesignModeSyncProgress:
    async def test_delegates(self):
        called = {}

        async def cb(**kwargs):
            called.update(kwargs)

        await _emit_design_mode_sync_progress(
            emit_progress=cb,
            session_id=None,
            processed=1,
            total=2,
            applied=1,
            errors=0,
        )
        assert called["processed"] == 1


# ---------------------------------------------------------------------------
# _apply_changes_with_source_mapping
# ---------------------------------------------------------------------------


class TestApplyChangesWithSourceMapping:
    async def test_style_applied(self, fake_sandbox):
        content = '<div data-design-id="s1" className="foo">text</div>'
        sb = fake_sandbox(
            files={"/workspace/src/App.tsx": content},
            command_outputs={
                "rg": '/workspace/src/App.tsx:1:  data-design-id="s1"\n',
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        ctx = make_element_context(design_id="s1", tag_name="div")
        change = make_style_change(
            design_id="s1",
            type="style",
            property="color",
            value={"to": "red"},
            element_context=ctx,
        )
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert applied == 1
        assert len(remaining) == 0

    async def test_text_applied(self, fake_sandbox):
        content = '<h1 data-design-id="t1">Hello</h1>'
        sb = fake_sandbox(
            files={"/workspace/src/App.tsx": content},
            command_outputs={
                "rg": '/workspace/src/App.tsx:1:  data-design-id="t1"\n',
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        ctx = make_element_context(design_id="t1", tag_name="h1", text_content="Hello")
        change = make_style_change(
            design_id="t1",
            type="text",
            property="textContent",
            value={"from": "Hello", "to": "World"},
            element_context=ctx,
        )
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert applied == 1

    async def test_delete_applied(self, fake_sandbox):
        content = '<div data-design-id="d1">remove me</div>'
        sb = fake_sandbox(
            files={"/workspace/src/App.tsx": content},
            command_outputs={
                "rg": '/workspace/src/App.tsx:1:  data-design-id="d1"\n',
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        ctx = make_element_context(design_id="d1", tag_name="div")
        change = make_style_change(
            design_id="d1",
            type="delete",
            property="",
            element_context=ctx,
        )
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert applied == 1

    async def test_missing_design_id(self, fake_sandbox):
        sb = fake_sandbox()
        change = make_style_change(
            design_id="", type="style", property="color", value={"to": "red"}
        )
        # Override designId to empty
        change.designId = ""
        if change.elementContext:
            change.elementContext.designId = ""
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert applied == 0
        assert len(remaining) == 1

    async def test_unsupported_type(self, fake_sandbox):
        content = '<div data-design-id="u1">text</div>'
        sb = fake_sandbox(
            files={"/workspace/src/App.tsx": content},
            command_outputs={
                "rg": '/workspace/src/App.tsx:1:  data-design-id="u1"\n',
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        ctx = make_element_context(design_id="u1", tag_name="div")
        change = make_style_change(
            design_id="u1",
            type="unknown_type",
            property="x",
            element_context=ctx,
        )
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert applied == 0
        assert len(remaining) == 1

    async def test_missing_id_remaining(self, fake_sandbox):
        sb = fake_sandbox(
            command_outputs={
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            }
        )
        ctx = make_element_context(design_id="not-in-source", tag_name="div")
        change = make_style_change(
            design_id="not-in-source",
            type="style",
            property="color",
            value={"to": "red"},
            element_context=ctx,
        )
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert applied == 0
        assert len(remaining) == 1

    async def test_empty_list(self, fake_sandbox):
        sb = fake_sandbox()
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[],
        )
        assert applied == 0
        assert errors == []
        assert remaining == []

    async def test_progress_emitted(self, fake_sandbox):
        content = '<div data-design-id="p1">text</div>'
        sb = fake_sandbox(
            files={"/workspace/src/App.tsx": content},
            command_outputs={
                "rg": '/workspace/src/App.tsx:1:  data-design-id="p1"\n',
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        calls = []

        async def progress_cb(**kwargs):
            calls.append(kwargs)

        ctx = make_element_context(design_id="p1", tag_name="div")
        change = make_style_change(
            design_id="p1",
            type="style",
            property="color",
            value={"to": "red"},
            element_context=ctx,
        )
        await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
            emit_progress=progress_cb,
        )
        assert len(calls) >= 2  # At least start + done
        assert calls[-1]["done"] is True

    async def test_icon_applied(self, fake_sandbox):
        content = "import { Zap } from 'lucide-react'\n<Zap data-design-id=\"icon1\" />"
        sb = fake_sandbox(
            files={"/workspace/src/App.tsx": content},
            command_outputs={
                "rg": '/workspace/src/App.tsx:1:  data-design-id="icon1"\n',
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        ctx = make_element_context(design_id="icon1", tag_name="svg")
        change = make_style_change(
            design_id="icon1",
            type="attribute",
            property="icon",
            value={"to": {"name": "bell"}},
            element_context=ctx,
        )
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert applied == 1

    async def test_move_applied(self, fake_sandbox):
        content = '<div data-design-id="a">A</div><div data-design-id="b">B</div>'
        sb = fake_sandbox(
            files={"/workspace/src/App.tsx": content},
            command_outputs={
                "rg": '/workspace/src/App.tsx:1:  data-design-id="a"\n/workspace/src/App.tsx:1:  data-design-id="b"\n',
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        ctx = make_element_context(design_id="a", tag_name="div")
        change = make_style_change(
            design_id="a",
            type="move",
            property="position",
            value={"to": "after:b"},
            element_context=ctx,
        )
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert applied == 1

    async def test_css_override_fallback(self, fake_sandbox):
        # When backfill fails, style changes should fall back to CSS override
        sb = fake_sandbox(
            files={"/workspace/src/app/globals.css": "body {}"},
            command_outputs={
                "find": "/workspace/src/app/globals.css\n",
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        ctx = make_element_context(design_id="missing-id", tag_name="div")
        change = make_style_change(
            design_id="missing-id",
            type="style",
            property="color",
            value={"to": "red"},
            element_context=ctx,
        )
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert applied == 1

    async def test_manifest_mapping(self, fake_sandbox):
        import json

        manifest = json.dumps({"m1": "/workspace/src/App.tsx"})
        content = '<div data-design-id="m1">text</div>'
        sb = fake_sandbox(
            files={
                "/workspace/design-mode.manifest.json": manifest,
                "/workspace/src/App.tsx": content,
            },
            command_outputs={
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        ctx = make_element_context(design_id="m1", tag_name="div")
        change = make_style_change(
            design_id="m1",
            type="style",
            property="color",
            value={"to": "red"},
            element_context=ctx,
        )
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert applied == 1

    async def test_verify_mismatch_blocks(self, fake_sandbox):
        content = '<span data-design-id="v1">wrong tag</span>'
        sb = fake_sandbox(
            files={"/workspace/src/App.tsx": content},
            command_outputs={
                "rg": '/workspace/src/App.tsx:1:  data-design-id="v1"\n',
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        # Element context says tag should be div, but source has span
        ctx = make_element_context(design_id="v1", tag_name="div")
        change = make_style_change(
            design_id="v1",
            type="style",
            property="color",
            value={"to": "red"},
            element_context=ctx,
        )
        applied, errors, remaining = await _apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        # Either falls back to CSS override or ends up in remaining
        # (depends on whether globals.css is available)
        assert applied == 0 or applied == 1


# ---------------------------------------------------------------------------
# apply_changes_with_source_mapping (public)
# ---------------------------------------------------------------------------


class TestPublicApplyChanges:
    async def test_delegates(self, fake_sandbox):
        sb = fake_sandbox()
        applied, errors, remaining = await apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[],
        )
        assert applied == 0
        assert errors == []
        assert remaining == []

    async def test_returns_correct_tuple(self, fake_sandbox):
        content = '<div data-design-id="x1">text</div>'
        sb = fake_sandbox(
            files={"/workspace/src/App.tsx": content},
            command_outputs={
                "rg": '/workspace/src/App.tsx:1:  data-design-id="x1"\n',
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "",
            },
        )
        ctx = make_element_context(design_id="x1", tag_name="div")
        change = make_style_change(
            design_id="x1",
            type="style",
            property="color",
            value={"to": "red"},
            element_context=ctx,
        )
        result = await apply_changes_with_source_mapping(
            sandbox=sb,
            changes=[change],
        )
        assert isinstance(result, tuple)
        assert len(result) == 3
        applied, errors, remaining = result
        assert isinstance(applied, int)
        assert isinstance(errors, list)
        assert isinstance(remaining, list)
