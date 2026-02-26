"""Tests for _manifest.py."""

import json

import pytest

from ii_agent.projects.design.source_mapping_sync._manifest import (
    _load_design_mode_manifest_mapping,
    _parse_design_mode_manifest_mapping,
)


# ---------------------------------------------------------------------------
# _parse_design_mode_manifest_mapping
# ---------------------------------------------------------------------------

class TestParseDesignModeManifestMapping:
    def test_v1_ids_format(self):
        data = {"version": 1, "ids": {"abc": "/workspace/src/App.tsx"}}
        result = _parse_design_mode_manifest_mapping(json.dumps(data))
        assert "abc" in result
        assert result["abc"] == ["/workspace/src/App.tsx"]

    def test_v1_elements_format(self):
        data = {
            "version": 1,
            "elements": [
                {"design_id": "abc", "file_path": "/workspace/src/App.tsx"},
            ],
        }
        result = _parse_design_mode_manifest_mapping(json.dumps(data))
        assert "abc" in result

    def test_camel_case_keys(self):
        data = {
            "version": 1,
            "elements": [
                {"designId": "abc", "filePath": "/workspace/src/App.tsx"},
            ],
        }
        result = _parse_design_mode_manifest_mapping(json.dumps(data))
        assert "abc" in result

    def test_legacy_flat(self):
        data = {"abc": "/workspace/src/App.tsx"}
        result = _parse_design_mode_manifest_mapping(json.dumps(data))
        assert "abc" in result

    def test_normalizes_paths(self):
        data = {"abc": "src/App.tsx"}
        result = _parse_design_mode_manifest_mapping(json.dumps(data))
        assert result["abc"] == ["/workspace/src/App.tsx"]

    def test_dedup(self):
        data = {
            "version": 1,
            "ids": {"abc": "/workspace/src/App.tsx"},
        }
        result = _parse_design_mode_manifest_mapping(json.dumps(data))
        assert len(result["abc"]) == 1

    def test_multiple_paths_via_elements(self):
        data = {
            "version": 1,
            "elements": [
                {"design_id": "abc", "file_path": "/workspace/src/A.tsx"},
                {"design_id": "abc", "file_path": "/workspace/src/B.tsx"},
            ],
        }
        result = _parse_design_mode_manifest_mapping(json.dumps(data))
        assert len(result["abc"]) == 2

    def test_reject_non_workspace(self):
        data = {"abc": "/usr/local/file.tsx"}
        result = _parse_design_mode_manifest_mapping(json.dumps(data))
        assert "abc" not in result

    def test_empty_string(self):
        assert _parse_design_mode_manifest_mapping("") == {}

    def test_none(self):
        assert _parse_design_mode_manifest_mapping(None) == {}

    def test_invalid_json(self):
        assert _parse_design_mode_manifest_mapping("not json") == {}

    def test_non_dict(self):
        assert _parse_design_mode_manifest_mapping(json.dumps([1, 2, 3])) == {}

    def test_empty_id(self):
        data = {"version": 1, "ids": {"": "/workspace/src/App.tsx"}}
        result = _parse_design_mode_manifest_mapping(json.dumps(data))
        assert len(result) == 0

    def test_empty_path(self):
        data = {"version": 1, "ids": {"abc": ""}}
        result = _parse_design_mode_manifest_mapping(json.dumps(data))
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _load_design_mode_manifest_mapping (async)
# ---------------------------------------------------------------------------

class TestLoadDesignModeManifestMapping:
    async def test_loads_and_parses(self, fake_sandbox):
        manifest = json.dumps({"abc": "/workspace/src/App.tsx"})
        sb = fake_sandbox(files={"/workspace/design-mode.manifest.json": manifest})
        path, mapping = await _load_design_mode_manifest_mapping(sb)
        assert path == "/workspace/design-mode.manifest.json"
        assert "abc" in mapping

    async def test_caching(self, fake_sandbox):
        manifest = json.dumps({"abc": "/workspace/src/App.tsx"})
        sb = fake_sandbox(files={"/workspace/design-mode.manifest.json": manifest})
        path1, mapping1 = await _load_design_mode_manifest_mapping(sb)
        path2, mapping2 = await _load_design_mode_manifest_mapping(sb)
        assert path1 == path2
        assert mapping1 == mapping2

    async def test_file_not_found(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={
            "find /workspace -maxdepth 1": "",
            "find /workspace -type f": "",
        })
        path, mapping = await _load_design_mode_manifest_mapping(sb)
        assert path is None
        assert mapping == {}

    async def test_resolved_path(self, fake_sandbox):
        manifest = json.dumps({"abc": "/workspace/src/A.tsx"})
        sb = fake_sandbox(
            files={"/workspace/myapp/design-mode.manifest.json": manifest},
            command_outputs={
                "find /workspace -maxdepth 1": "/workspace/myapp\n",
            },
        )
        path, mapping = await _load_design_mode_manifest_mapping(sb)
        assert path == "/workspace/myapp/design-mode.manifest.json"
        assert "abc" in mapping
