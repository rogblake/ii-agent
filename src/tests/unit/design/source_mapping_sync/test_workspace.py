"""Tests for _workspace.py."""

import pytest

from ii_agent.projects.design.source_mapping_sync._workspace import (
    _normalize_react_source_file_name,
    _normalize_workspace_file_path,
    _normalize_workspace_path,
    _parse_search_paths,
    _score_globals_css_candidate,
    _score_source_path,
    _workspace_relative_path,
    _get_workspace_top_level_dirs,
    _read_file_with_workspace_fallback,
    _search_workspace_for_fixed_string,
)


# ---------------------------------------------------------------------------
# _normalize_workspace_file_path
# ---------------------------------------------------------------------------


class TestNormalizeWorkspaceFilePath:
    def test_absolute_workspace_path(self):
        assert _normalize_workspace_file_path("/workspace/src/App.tsx") == "/workspace/src/App.tsx"

    def test_relative_path(self):
        assert _normalize_workspace_file_path("src/App.tsx") == "/workspace/src/App.tsx"

    def test_workspace_prefix(self):
        assert _normalize_workspace_file_path("workspace/src/App.tsx") == "/workspace/src/App.tsx"

    def test_file_uri(self):
        assert (
            _normalize_workspace_file_path("file:///workspace/src/App.tsx")
            == "/workspace/src/App.tsx"
        )

    def test_quote_wrapped(self):
        assert _normalize_workspace_file_path('"workspace/src/App.tsx"') == "/workspace/src/App.tsx"

    def test_backtick_wrapped(self):
        assert _normalize_workspace_file_path("`workspace/src/App.tsx`") == "/workspace/src/App.tsx"

    def test_backslash(self):
        result = _normalize_workspace_file_path("workspace\\src\\App.tsx")
        assert result == "/workspace/src/App.tsx"

    def test_reject_non_workspace_absolute(self):
        assert _normalize_workspace_file_path("/usr/local/file.txt") is None

    def test_reject_root(self):
        assert _normalize_workspace_file_path("workspace") is None

    def test_traversal_attack(self):
        assert _normalize_workspace_file_path("../../etc/passwd") is None

    def test_empty(self):
        assert _normalize_workspace_file_path("") is None

    def test_none(self):
        assert _normalize_workspace_file_path(None) is None

    def test_just_spaces(self):
        assert _normalize_workspace_file_path("   ") is None

    def test_normalizes_dots(self):
        result = _normalize_workspace_file_path("/workspace/src/../src/App.tsx")
        assert result == "/workspace/src/App.tsx"


# ---------------------------------------------------------------------------
# _normalize_workspace_path (alias)
# ---------------------------------------------------------------------------


class TestNormalizeWorkspacePath:
    def test_alias(self):
        assert _normalize_workspace_path("src/App.tsx") == _normalize_workspace_file_path(
            "src/App.tsx"
        )


# ---------------------------------------------------------------------------
# _normalize_react_source_file_name
# ---------------------------------------------------------------------------


class TestNormalizeReactSourceFileName:
    def test_simple(self):
        assert _normalize_react_source_file_name("src/App.tsx") == "src/App.tsx"

    def test_hash_query(self):
        assert _normalize_react_source_file_name("src/App.tsx#123?v=1") == "src/App.tsx"

    def test_url(self):
        result = _normalize_react_source_file_name("http://localhost:3000/src/App.tsx")
        assert result == "src/App.tsx"

    def test_webpack(self):
        result = _normalize_react_source_file_name("webpack:///./src/App.tsx")
        assert result == "src/App.tsx"

    def test_host_path_with_src(self):
        result = _normalize_react_source_file_name("/Users/dev/project/src/App.tsx")
        assert result == "src/App.tsx"

    def test_host_path_no_src(self):
        result = _normalize_react_source_file_name("/Users/dev/project/App.tsx")
        assert result is None

    def test_dot_slash(self):
        assert _normalize_react_source_file_name("./src/App.tsx") == "src/App.tsx"

    def test_empty(self):
        assert _normalize_react_source_file_name("") is None

    def test_none(self):
        assert _normalize_react_source_file_name(None) is None

    def test_non_string(self):
        assert _normalize_react_source_file_name(42) is None


# ---------------------------------------------------------------------------
# _workspace_relative_path
# ---------------------------------------------------------------------------


class TestWorkspaceRelativePath:
    def test_normal(self):
        assert _workspace_relative_path("/workspace/src/App.tsx") == "src/App.tsx"

    def test_non_workspace(self):
        assert _workspace_relative_path("/other/src/App.tsx") is None

    def test_root(self):
        assert _workspace_relative_path("/workspace/") is None

    def test_traversal(self):
        assert _workspace_relative_path("/workspace/../etc/passwd") is None

    def test_none(self):
        assert _workspace_relative_path(None) is None

    def test_nested(self):
        assert _workspace_relative_path("/workspace/a/b/c.tsx") == "a/b/c.tsx"


# ---------------------------------------------------------------------------
# _score_source_path
# ---------------------------------------------------------------------------


class TestScoreSourcePath:
    def test_tsx_ranked_first(self):
        assert _score_source_path("src/App.tsx") < _score_source_path("src/App.jsx")

    def test_src_preferred(self):
        assert _score_source_path("/workspace/src/App.tsx") < _score_source_path(
            "/workspace/App.tsx"
        )

    def test_shorter_preferred(self):
        s1 = _score_source_path("/workspace/src/App.tsx")
        s2 = _score_source_path("/workspace/src/components/deep/App.tsx")
        assert s1 < s2

    def test_html_vs_jsx(self):
        assert _score_source_path("file.jsx") < _score_source_path("file.html")

    def test_unknown_ext(self):
        score = _score_source_path("file.py")
        assert score[0] == 9  # ext_rank

    def test_empty(self):
        score = _score_source_path("")
        assert score[0] == 9


# ---------------------------------------------------------------------------
# _parse_search_paths
# ---------------------------------------------------------------------------


class TestParseSearchPaths:
    def test_grep_output(self):
        output = "/workspace/src/App.tsx:10:  some code\n/workspace/src/Other.tsx:5:  other"
        result = _parse_search_paths(output)
        assert result == ["/workspace/src/App.tsx", "/workspace/src/Other.tsx"]

    def test_dedup(self):
        output = "/workspace/a.tsx:1: x\n/workspace/a.tsx:2: y"
        result = _parse_search_paths(output)
        assert result == ["/workspace/a.tsx"]

    def test_order_preserved(self):
        output = "/workspace/b.tsx:1: x\n/workspace/a.tsx:2: y"
        result = _parse_search_paths(output)
        assert result == ["/workspace/b.tsx", "/workspace/a.tsx"]

    def test_empty(self):
        assert _parse_search_paths("") == []

    def test_malformed(self):
        assert _parse_search_paths("not a grep line") == []


# ---------------------------------------------------------------------------
# _score_globals_css_candidate
# ---------------------------------------------------------------------------


class TestScoreGlobalsCssCandidate:
    def test_src_app_globals(self):
        assert _score_globals_css_candidate("/workspace/src/app/globals.css") == 0

    def test_app_globals(self):
        assert _score_globals_css_candidate("/workspace/app/globals.css") == 1

    def test_src_styles(self):
        assert _score_globals_css_candidate("/workspace/src/styles/globals.css") == 2

    def test_unrecognized(self):
        assert _score_globals_css_candidate("/workspace/other/custom.css") == 9

    def test_empty(self):
        assert _score_globals_css_candidate("") == 9


# ---------------------------------------------------------------------------
# _get_workspace_top_level_dirs (async)
# ---------------------------------------------------------------------------


class TestGetWorkspaceTopLevelDirs:
    async def test_filtered_dirs(self, fake_sandbox):
        sb = fake_sandbox(
            command_outputs={
                "find /workspace": "/workspace/myapp\n/workspace/.git\n/workspace/node_modules\n/workspace/src\n"
            }
        )
        result = await _get_workspace_top_level_dirs(sb)
        assert "/workspace/myapp" in result
        assert "/workspace/src" in result
        assert "/workspace/.git" not in result
        assert "/workspace/node_modules" not in result

    async def test_caching(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={"find /workspace": "/workspace/myapp\n"})
        result1 = await _get_workspace_top_level_dirs(sb)
        # Modify command output — should still get cached
        sb._command_outputs = {}
        result2 = await _get_workspace_top_level_dirs(sb)
        assert result1 == result2

    async def test_empty(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={})
        result = await _get_workspace_top_level_dirs(sb)
        assert result == []

    async def test_exception(self, fake_sandbox):
        sb = fake_sandbox()

        async def failing_run(cmd):
            raise RuntimeError("fail")

        sb.run_command = failing_run
        result = await _get_workspace_top_level_dirs(sb)
        assert result == []

    async def test_non_workspace_filtered(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={"find /workspace": "/other/dir\n/workspace/src\n"})
        result = await _get_workspace_top_level_dirs(sb)
        assert "/other/dir" not in result


# ---------------------------------------------------------------------------
# _read_file_with_workspace_fallback (async)
# ---------------------------------------------------------------------------


class TestReadFileWithWorkspaceFallback:
    async def test_direct_read(self, fake_sandbox):
        sb = fake_sandbox(files={"/workspace/src/App.tsx": "content"})
        content, path = await _read_file_with_workspace_fallback(sb, "/workspace/src/App.tsx")
        assert content == "content"
        assert path == "/workspace/src/App.tsx"

    async def test_nested_fallback(self, fake_sandbox):
        sb = fake_sandbox(
            files={"/workspace/myapp/src/App.tsx": "nested"},
            command_outputs={"find /workspace": "/workspace/myapp\n"},
        )
        content, path = await _read_file_with_workspace_fallback(sb, "/workspace/src/App.tsx")
        assert content == "nested"
        assert path == "/workspace/myapp/src/App.tsx"

    async def test_find_fallback(self, fake_sandbox):
        sb = fake_sandbox(
            files={"/workspace/deep/src/App.tsx": "found"},
            command_outputs={
                "find /workspace -maxdepth 1": "",
                "find /workspace -type f": "/workspace/deep/src/App.tsx\n",
            },
        )
        content, path = await _read_file_with_workspace_fallback(sb, "/workspace/src/App.tsx")
        assert content == "found"

    async def test_all_fail(self, fake_sandbox):
        sb = fake_sandbox(
            command_outputs={"find /workspace -maxdepth 1": "", "find /workspace -type f": ""}
        )
        with pytest.raises(FileNotFoundError):
            await _read_file_with_workspace_fallback(sb, "/workspace/src/App.tsx")

    async def test_bytes_decoded(self, fake_sandbox):
        sb = fake_sandbox()

        # Override read_file to return bytes
        async def read_bytes(path):
            return b"bytes content"

        sb.read_file = read_bytes
        content, path = await _read_file_with_workspace_fallback(sb, "/workspace/src/App.tsx")
        assert content == "bytes content"

    async def test_resolved_path(self, fake_sandbox):
        sb = fake_sandbox(files={"/workspace/src/App.tsx": "data"})
        _, resolved = await _read_file_with_workspace_fallback(sb, "/workspace/src/App.tsx")
        assert resolved == "/workspace/src/App.tsx"


# ---------------------------------------------------------------------------
# _search_workspace_for_fixed_string (async)
# ---------------------------------------------------------------------------


class TestSearchWorkspaceForFixedString:
    async def test_returns_output(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={"rg": "/workspace/a.tsx:1:match\n"})
        result = await _search_workspace_for_fixed_string(sb, "match")
        assert "/workspace/a.tsx" in result

    async def test_exception_returns_empty(self, fake_sandbox):
        sb = fake_sandbox()

        async def failing_run(cmd):
            raise RuntimeError("fail")

        sb.run_command = failing_run
        result = await _search_workspace_for_fixed_string(sb, "test")
        assert result == ""
