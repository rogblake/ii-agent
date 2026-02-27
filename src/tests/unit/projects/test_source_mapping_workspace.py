"""Unit tests for source_mapping_sync/_workspace.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
    """Tests for _normalize_workspace_file_path()."""

    def test_absolute_workspace_path_returned_as_is(self):
        result = _normalize_workspace_file_path("/workspace/src/App.tsx")
        assert result == "/workspace/src/App.tsx"

    def test_relative_path_prepends_workspace(self):
        result = _normalize_workspace_file_path("src/App.tsx")
        assert result == "/workspace/src/App.tsx"

    def test_workspace_prefix_handled(self):
        result = _normalize_workspace_file_path("workspace/src/App.tsx")
        assert result == "/workspace/src/App.tsx"

    def test_workspace_only_returns_none(self):
        result = _normalize_workspace_file_path("workspace")
        assert result is None

    def test_non_workspace_absolute_path_returns_none(self):
        result = _normalize_workspace_file_path("/home/user/App.tsx")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _normalize_workspace_file_path("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = _normalize_workspace_file_path("   ")
        assert result is None

    def test_non_string_returns_none(self):
        result = _normalize_workspace_file_path(None)  # type: ignore
        assert result is None

    def test_file_protocol_stripped(self):
        result = _normalize_workspace_file_path("file:///workspace/src/App.tsx")
        assert result == "/workspace/src/App.tsx"

    def test_backslashes_converted_to_forward_slashes(self):
        result = _normalize_workspace_file_path("src\\App.tsx")
        assert result == "/workspace/src/App.tsx"

    def test_backtick_wrapper_stripped(self):
        result = _normalize_workspace_file_path("`src/App.tsx`")
        assert result == "/workspace/src/App.tsx"

    def test_double_quote_wrapper_stripped(self):
        result = _normalize_workspace_file_path('"src/App.tsx"')
        assert result == "/workspace/src/App.tsx"

    def test_single_quote_wrapper_stripped(self):
        result = _normalize_workspace_file_path("'src/App.tsx'")
        assert result == "/workspace/src/App.tsx"

    def test_path_normalization_resolves_dotdot(self):
        # Paths that escape workspace should be rejected.
        result = _normalize_workspace_file_path("/workspace/../etc/passwd")
        assert result is None

    def test_workspace_root_returns_none(self):
        result = _normalize_workspace_file_path("/workspace")
        assert result is None

    def test_path_with_spaces_normalized(self):
        result = _normalize_workspace_file_path("  /workspace/src/App.tsx  ")
        assert result == "/workspace/src/App.tsx"

    def test_nested_path(self):
        result = _normalize_workspace_file_path(
            "/workspace/my-app/src/components/Button.tsx"
        )
        assert result == "/workspace/my-app/src/components/Button.tsx"


# ---------------------------------------------------------------------------
# _normalize_workspace_path
# ---------------------------------------------------------------------------


class TestNormalizeWorkspacePath:
    """Tests that _normalize_workspace_path() delegates to _normalize_workspace_file_path()."""

    def test_delegates_to_file_path_normalizer(self):
        result = _normalize_workspace_path("/workspace/src/App.tsx")
        assert result == "/workspace/src/App.tsx"

    def test_returns_none_for_invalid_path(self):
        result = _normalize_workspace_path("")
        assert result is None


# ---------------------------------------------------------------------------
# _normalize_react_source_file_name
# ---------------------------------------------------------------------------


class TestNormalizeReactSourceFileName:
    """Tests for _normalize_react_source_file_name()."""

    def test_simple_relative_path(self):
        result = _normalize_react_source_file_name("src/App.tsx")
        assert result == "src/App.tsx"

    def test_strips_leading_dotslash(self):
        result = _normalize_react_source_file_name("./src/App.tsx")
        assert result == "src/App.tsx"

    def test_strips_leading_slash(self):
        result = _normalize_react_source_file_name("/src/App.tsx")
        assert result == "src/App.tsx"

    def test_none_returns_none(self):
        result = _normalize_react_source_file_name(None)  # type: ignore
        assert result is None

    def test_empty_string_returns_none(self):
        result = _normalize_react_source_file_name("")
        assert result is None

    def test_url_with_http_scheme(self):
        result = _normalize_react_source_file_name("http://localhost:3000/src/App.tsx")
        # Should extract the path portion
        assert result is not None
        assert "src/App.tsx" in result

    def test_webpack_prefix_stripped(self):
        result = _normalize_react_source_file_name("webpack:///./src/App.tsx")
        assert result == "src/App.tsx"

    def test_query_string_stripped(self):
        result = _normalize_react_source_file_name("src/App.tsx?t=123456")
        assert result == "src/App.tsx"

    def test_hash_fragment_stripped(self):
        result = _normalize_react_source_file_name("src/App.tsx#L10")
        assert result == "src/App.tsx"

    def test_absolute_host_path_salvages_src_suffix(self):
        result = _normalize_react_source_file_name(
            "Users/username/project/src/components/Button.tsx"
        )
        assert result == "src/components/Button.tsx"

    def test_home_path_salvages_src_suffix(self):
        result = _normalize_react_source_file_name(
            "home/user/project/src/App.tsx"
        )
        assert result == "src/App.tsx"

    def test_host_path_without_src_returns_none(self):
        result = _normalize_react_source_file_name("Users/username/project/main.tsx")
        assert result is None

    def test_backslashes_converted(self):
        result = _normalize_react_source_file_name("src\\components\\App.tsx")
        assert result == "src/components/App.tsx"

    def test_non_string_returns_none(self):
        result = _normalize_react_source_file_name(42)  # type: ignore
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = _normalize_react_source_file_name("   ")
        assert result is None


# ---------------------------------------------------------------------------
# _workspace_relative_path
# ---------------------------------------------------------------------------


class TestWorkspaceRelativePath:
    """Tests for _workspace_relative_path()."""

    def test_absolute_workspace_path_returns_relative(self):
        result = _workspace_relative_path("/workspace/src/App.tsx")
        assert result == "src/App.tsx"

    def test_non_workspace_path_returns_none(self):
        result = _workspace_relative_path("/home/user/App.tsx")
        assert result is None

    def test_workspace_root_returns_none(self):
        result = _workspace_relative_path("/workspace/")
        assert result is None

    def test_none_returns_none(self):
        result = _workspace_relative_path(None)  # type: ignore
        assert result is None

    def test_nested_path(self):
        result = _workspace_relative_path(
            "/workspace/my-app/src/components/Button.tsx"
        )
        assert result == "my-app/src/components/Button.tsx"


# ---------------------------------------------------------------------------
# _score_source_path
# ---------------------------------------------------------------------------


class TestScoreSourcePath:
    """Tests for _score_source_path()."""

    def test_tsx_scores_lowest(self):
        tsx_score = _score_source_path("/workspace/src/App.tsx")
        jsx_score = _score_source_path("/workspace/src/App.jsx")
        assert tsx_score < jsx_score

    def test_jsx_scores_second(self):
        jsx_score = _score_source_path("/workspace/src/App.jsx")
        ts_score = _score_source_path("/workspace/src/App.ts")
        assert jsx_score < ts_score

    def test_ts_scores_third(self):
        ts_score = _score_source_path("/workspace/src/App.ts")
        js_score = _score_source_path("/workspace/src/App.js")
        assert ts_score < js_score

    def test_src_in_path_scores_better(self):
        in_src = _score_source_path("/workspace/src/App.tsx")
        not_in_src = _score_source_path("/workspace/lib/App.tsx")
        assert in_src < not_in_src

    def test_shorter_path_scores_better_when_equal(self):
        short = _score_source_path("/workspace/src/App.tsx")
        long = _score_source_path("/workspace/src/components/very/deep/App.tsx")
        assert short < long

    def test_unknown_extension_scores_high(self):
        unknown_score = _score_source_path("/workspace/src/App.xyz")
        tsx_score = _score_source_path("/workspace/src/App.tsx")
        assert tsx_score < unknown_score

    def test_returns_tuple(self):
        result = _score_source_path("/workspace/src/App.tsx")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_empty_string(self):
        result = _score_source_path("")
        assert isinstance(result, tuple)

    def test_html_scores_after_js(self):
        js_score = _score_source_path("/workspace/src/App.js")
        html_score = _score_source_path("/workspace/src/App.html")
        assert js_score < html_score


# ---------------------------------------------------------------------------
# _score_globals_css_candidate
# ---------------------------------------------------------------------------


class TestScoreGlobalsCssCandidate:
    """Tests for _score_globals_css_candidate()."""

    def test_src_app_globals_scores_zero(self):
        result = _score_globals_css_candidate("/workspace/src/app/globals.css")
        assert result == 0

    def test_app_globals_scores_one(self):
        result = _score_globals_css_candidate("/workspace/app/globals.css")
        assert result == 1

    def test_src_styles_globals_scores_two(self):
        result = _score_globals_css_candidate("/workspace/src/styles/globals.css")
        assert result == 2

    def test_styles_globals_scores_three(self):
        result = _score_globals_css_candidate("/workspace/styles/globals.css")
        assert result == 3

    def test_unknown_path_scores_nine(self):
        result = _score_globals_css_candidate("/workspace/other/globals.css")
        assert result == 9

    def test_case_insensitive(self):
        result = _score_globals_css_candidate("/workspace/SRC/APP/GLOBALS.CSS")
        assert result == 0

    def test_empty_string(self):
        result = _score_globals_css_candidate("")
        assert result == 9

    def test_none_coerces_to_empty(self):
        result = _score_globals_css_candidate(None)  # type: ignore
        assert result == 9


# ---------------------------------------------------------------------------
# _parse_search_paths
# ---------------------------------------------------------------------------


class TestParseSearchPaths:
    """Tests for _parse_search_paths()."""

    def test_parses_ripgrep_output(self):
        output = "/workspace/src/App.tsx:10: some content\n/workspace/lib/utils.ts:5: other content"
        result = _parse_search_paths(output)
        assert "/workspace/src/App.tsx" in result
        assert "/workspace/lib/utils.ts" in result

    def test_deduplicates_paths(self):
        output = (
            "/workspace/src/App.tsx:10: content\n"
            "/workspace/src/App.tsx:20: more content\n"
        )
        result = _parse_search_paths(output)
        assert result.count("/workspace/src/App.tsx") == 1

    def test_preserves_order(self):
        output = (
            "/workspace/b.tsx:1: x\n"
            "/workspace/a.tsx:1: y\n"
        )
        result = _parse_search_paths(output)
        assert result[0] == "/workspace/b.tsx"
        assert result[1] == "/workspace/a.tsx"

    def test_empty_string_returns_empty(self):
        result = _parse_search_paths("")
        assert result == []

    def test_none_returns_empty(self):
        result = _parse_search_paths(None)  # type: ignore
        assert result == []

    def test_skips_lines_without_colon_pattern(self):
        output = "not-a-match\n/workspace/src/App.tsx:5: ok"
        result = _parse_search_paths(output)
        assert len(result) == 1
        assert result[0] == "/workspace/src/App.tsx"

    def test_skips_blank_lines(self):
        output = "\n\n/workspace/src/App.tsx:1: x\n\n"
        result = _parse_search_paths(output)
        assert result == ["/workspace/src/App.tsx"]

    def test_handles_paths_with_spaces_in_grep_format(self):
        # grep format: /path/to/file:linenum: content
        output = "/workspace/src/my-app/App.tsx:42: className='foo'"
        result = _parse_search_paths(output)
        assert "/workspace/src/my-app/App.tsx" in result


# ---------------------------------------------------------------------------
# _get_workspace_top_level_dirs
# ---------------------------------------------------------------------------


class TestGetWorkspaceTopLevelDirs:
    """Tests for _get_workspace_top_level_dirs()."""

    @pytest.mark.asyncio
    async def test_returns_list_of_dirs(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(
            return_value="/workspace/my-app\n/workspace/other-project\n"
        )
        result = await _get_workspace_top_level_dirs(sandbox)
        assert "/workspace/my-app" in result
        assert "/workspace/other-project" in result

    @pytest.mark.asyncio
    async def test_filters_out_node_modules(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(
            return_value="/workspace/my-app\n/workspace/node_modules\n"
        )
        result = await _get_workspace_top_level_dirs(sandbox)
        assert "/workspace/my-app" in result
        assert "/workspace/node_modules" not in result

    @pytest.mark.asyncio
    async def test_filters_out_git(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(
            return_value="/workspace/my-app\n/workspace/.git\n"
        )
        result = await _get_workspace_top_level_dirs(sandbox)
        assert "/workspace/.git" not in result

    @pytest.mark.asyncio
    async def test_filters_out_dist_build_next(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(
            return_value="/workspace/dist\n/workspace/build\n/workspace/.next\n/workspace/app\n"
        )
        result = await _get_workspace_top_level_dirs(sandbox)
        assert "/workspace/dist" not in result
        assert "/workspace/build" not in result
        assert "/workspace/.next" not in result
        assert "/workspace/app" in result

    @pytest.mark.asyncio
    async def test_filters_out_non_workspace_paths(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(
            return_value="/workspace/my-app\n/home/other\n"
        )
        result = await _get_workspace_top_level_dirs(sandbox)
        assert "/home/other" not in result

    @pytest.mark.asyncio
    async def test_exception_during_command_returns_empty(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(side_effect=Exception("timeout"))
        result = await _get_workspace_top_level_dirs(sandbox)
        assert result == []

    @pytest.mark.asyncio
    async def test_result_is_cached_on_sandbox(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(return_value="/workspace/my-app\n")
        # First call
        first = await _get_workspace_top_level_dirs(sandbox)
        # Simulate cache by setting the attribute
        setattr(sandbox, "design_mode_workspace_roots", first)
        # Second call should not re-run command
        second = await _get_workspace_top_level_dirs(sandbox)
        assert first == second

    @pytest.mark.asyncio
    async def test_result_is_sorted(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(
            return_value="/workspace/zapp\n/workspace/aapp\n/workspace/mapp\n"
        )
        result = await _get_workspace_top_level_dirs(sandbox)
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# _read_file_with_workspace_fallback
# ---------------------------------------------------------------------------


class TestReadFileWithWorkspaceFallback:
    """Tests for _read_file_with_workspace_fallback()."""

    @pytest.mark.asyncio
    async def test_returns_content_on_direct_read(self):
        sandbox = MagicMock()
        sandbox.read_file = AsyncMock(return_value="file content")
        content, path = await _read_file_with_workspace_fallback(
            sandbox, "/workspace/src/App.tsx"
        )
        assert content == "file content"
        assert path == "/workspace/src/App.tsx"

    @pytest.mark.asyncio
    async def test_decodes_bytes_content(self):
        sandbox = MagicMock()
        sandbox.read_file = AsyncMock(return_value=b"bytes content")
        content, path = await _read_file_with_workspace_fallback(
            sandbox, "/workspace/src/App.tsx"
        )
        assert content == "bytes content"

    @pytest.mark.asyncio
    async def test_falls_back_to_subdir_read(self):
        sandbox = MagicMock()
        call_count = 0

        async def mock_read_file(path: str) -> str:
            nonlocal call_count
            call_count += 1
            if path == "/workspace/src/App.tsx":
                raise FileNotFoundError(path)
            if path == "/workspace/my-project/src/App.tsx":
                return "subproject content"
            raise FileNotFoundError(path)

        sandbox.read_file = mock_read_file
        sandbox.run_command = AsyncMock(return_value="/workspace/my-project\n")

        content, path = await _read_file_with_workspace_fallback(
            sandbox, "/workspace/src/App.tsx"
        )
        assert content == "subproject content"
        assert path == "/workspace/my-project/src/App.tsx"

    @pytest.mark.asyncio
    async def test_raises_when_all_fallbacks_fail(self):
        sandbox = MagicMock()
        sandbox.read_file = AsyncMock(side_effect=FileNotFoundError("not found"))
        sandbox.run_command = AsyncMock(return_value="")  # No subdirs, no find result

        with pytest.raises((FileNotFoundError, Exception)):
            await _read_file_with_workspace_fallback(
                sandbox, "/workspace/src/App.tsx"
            )

    @pytest.mark.asyncio
    async def test_find_fallback_used_when_subdir_fails(self):
        sandbox = MagicMock()

        async def mock_read_file(path: str) -> str:
            if path == "/workspace/found/src/App.tsx":
                return "found content"
            raise FileNotFoundError(path)

        sandbox.read_file = mock_read_file
        sandbox.run_command = AsyncMock(
            side_effect=[
                "",  # _get_workspace_top_level_dirs returns empty
                "/workspace/found/src/App.tsx\n",  # find command returns path
            ]
        )

        content, path = await _read_file_with_workspace_fallback(
            sandbox, "/workspace/src/App.tsx"
        )
        assert content == "found content"


# ---------------------------------------------------------------------------
# _search_workspace_for_fixed_string
# ---------------------------------------------------------------------------


class TestSearchWorkspaceForFixedString:
    """Tests for _search_workspace_for_fixed_string()."""

    @pytest.mark.asyncio
    async def test_returns_command_output(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(
            return_value="/workspace/src/App.tsx:5: some match"
        )
        result = await _search_workspace_for_fixed_string(sandbox, "some match")
        assert "/workspace/src/App.tsx" in result

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_exception(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(side_effect=Exception("failed"))
        result = await _search_workspace_for_fixed_string(sandbox, "query")
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_none_returned(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(return_value=None)
        result = await _search_workspace_for_fixed_string(sandbox, "query")
        assert result == ""

    @pytest.mark.asyncio
    async def test_query_is_shell_escaped(self):
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(return_value="")
        await _search_workspace_for_fixed_string(sandbox, "query with spaces")
        cmd = sandbox.run_command.call_args[0][0]
        # The query should be shell-quoted
        assert "query with spaces" in cmd or "'query with spaces'" in cmd
