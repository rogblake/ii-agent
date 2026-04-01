"""Unit tests for source_mapping_sync/_backfill.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.projects.design.schemas import ElementContext, StyleChange
from ii_agent.projects.design.source_mapping_sync._backfill import (
    _build_line_start_offsets,
    _class_token_distinctiveness,
    _extract_anchor_snippets,
    _find_best_component_callsite_opening_tag,
    _find_best_opening_tag_by_class_tokens,
    _find_best_opening_tag_near_source_location,
    _infer_component_name_before_index,
    _pos_to_line_number,
    _split_class_tokens,
    _upsert_data_design_id_attribute,
    _backfill_design_id_in_source_from_class_name,
    _backfill_design_id_in_source_from_component_callsite,
    _backfill_design_id_in_source_from_react_source,
    _backfill_design_id_in_source_from_text_search,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_element_context(**kwargs) -> ElementContext:
    defaults = {
        "designId": "did-1",
        "tagName": "div",
        "className": None,
        "textContent": None,
        "outerHTML": None,
        "contextText": None,
        "prevSiblingText": None,
        "nextSiblingText": None,
        "reactSource": None,
    }
    defaults.update(kwargs)
    return ElementContext(**defaults)


def _make_style_change(element_context: ElementContext | None = None) -> StyleChange:
    return StyleChange(
        designId="did-1",
        type="style",
        property="color",
        value={"to": "red"},
        timestamp=1234567890,
        elementContext=element_context,
    )


def _make_sandbox(
    read_response: str = "",
    run_command_response: str = "",
    read_raises: Exception | None = None,
) -> MagicMock:
    sandbox = MagicMock()
    if read_raises:
        sandbox.read_file = AsyncMock(side_effect=read_raises)
    else:
        sandbox.read_file = AsyncMock(return_value=read_response)
    sandbox.run_command = AsyncMock(return_value=run_command_response)
    return sandbox


# ---------------------------------------------------------------------------
# _extract_anchor_snippets
# ---------------------------------------------------------------------------


class TestExtractAnchorSnippets:
    def test_returns_empty_for_none_context(self):
        result = _extract_anchor_snippets(None)
        assert result == []

    def test_extracts_from_text_content(self):
        ctx = _make_element_context(textContent="Hello World")
        result = _extract_anchor_snippets(ctx)
        assert "Hello World" in result

    def test_extracts_from_multiple_fields(self):
        ctx = _make_element_context(
            textContent="Main text",
            nextSiblingText="Next sibling",
        )
        result = _extract_anchor_snippets(ctx)
        assert "Main text" in result
        assert "Next sibling" in result

    def test_deduplicates_snippets(self):
        ctx = _make_element_context(
            textContent="Duplicate",
            nextSiblingText="Duplicate",
        )
        result = _extract_anchor_snippets(ctx)
        assert result.count("Duplicate") == 1

    def test_splits_multiline_text(self):
        ctx = _make_element_context(textContent="Line one\nLine two\nLine three")
        result = _extract_anchor_snippets(ctx)
        assert "Line one" in result
        assert "Line two" in result

    def test_limits_to_8_snippets(self):
        long_text = "\n".join([f"Line {i}" for i in range(20)])
        ctx = _make_element_context(textContent=long_text)
        result = _extract_anchor_snippets(ctx)
        assert len(result) <= 8

    def test_truncates_long_snippets_to_120_chars(self):
        long_text = "A" * 200
        ctx = _make_element_context(textContent=long_text)
        result = _extract_anchor_snippets(ctx)
        for snippet in result:
            assert len(snippet) <= 120

    def test_ignores_na_text(self):
        ctx = _make_element_context(textContent="n/a")
        result = _extract_anchor_snippets(ctx)
        assert result == []

    def test_ignores_empty_text(self):
        ctx = _make_element_context(textContent="")
        result = _extract_anchor_snippets(ctx)
        assert result == []

    def test_ignores_whitespace_only_text(self):
        ctx = _make_element_context(textContent="   ")
        result = _extract_anchor_snippets(ctx)
        assert result == []

    def test_splits_long_single_line_by_sentences(self):
        # A long single sentence block should be split by sentence boundaries.
        long_text = "First sentence here. Second sentence here. Third sentence here!"
        ctx = _make_element_context(textContent=long_text)
        # A 61-char string may or may not trigger sentence splitting (threshold is 80).
        result = _extract_anchor_snippets(ctx)
        assert len(result) >= 1

    def test_splits_very_long_single_line_by_sentences(self):
        long_text = (
            "This is the first sentence and it is quite long. "
            "This is the second sentence which is also long enough. "
            "And the third one too!"
        )
        ctx = _make_element_context(textContent=long_text)
        result = _extract_anchor_snippets(ctx)
        # Should have been split by sentences since total > 80 chars.
        assert len(result) > 1


# ---------------------------------------------------------------------------
# _split_class_tokens
# ---------------------------------------------------------------------------


class TestSplitClassTokens:
    def test_basic_splitting(self):
        result = _split_class_tokens("foo bar baz")
        assert result == ["foo", "bar", "baz"]

    def test_deduplicates_tokens(self):
        result = _split_class_tokens("foo foo bar")
        assert result == ["foo", "bar"]

    def test_multiple_spaces_handled(self):
        result = _split_class_tokens("foo   bar")
        assert result == ["foo", "bar"]

    def test_empty_string_returns_empty(self):
        result = _split_class_tokens("")
        assert result == []

    def test_whitespace_only_returns_empty(self):
        result = _split_class_tokens("   ")
        assert result == []

    def test_non_string_returns_empty(self):
        result = _split_class_tokens(None)  # type: ignore
        assert result == []

    def test_single_class(self):
        result = _split_class_tokens("container")
        assert result == ["container"]

    def test_preserves_order(self):
        result = _split_class_tokens("z a m")
        assert result == ["z", "a", "m"]


# ---------------------------------------------------------------------------
# _class_token_distinctiveness
# ---------------------------------------------------------------------------


class TestClassTokenDistinctiveness:
    def test_longer_token_scores_higher(self):
        short = _class_token_distinctiveness("a")
        long = _class_token_distinctiveness("backgroundColor")
        assert long > short

    def test_token_with_special_chars_scores_higher(self):
        plain = _class_token_distinctiveness("container")
        special = _class_token_distinctiveness("hover:bg-blue-500")
        assert special > plain

    def test_token_with_digit_scores_higher(self):
        no_digit = _class_token_distinctiveness("container")
        with_digit = _class_token_distinctiveness("container2")
        assert with_digit > no_digit

    def test_non_string_returns_zero(self):
        result = _class_token_distinctiveness(None)  # type: ignore
        assert result == 0

    def test_empty_string_returns_zero(self):
        result = _class_token_distinctiveness("")
        assert result == 0


# ---------------------------------------------------------------------------
# _upsert_data_design_id_attribute
# ---------------------------------------------------------------------------


class TestUpsertDataDesignIdAttribute:
    def test_adds_attribute_to_opening_tag(self):
        result = _upsert_data_design_id_attribute('<div className="foo">', "did-1")
        assert 'data-design-id="did-1"' in result

    def test_returns_tag_unchanged_when_same_id_exists(self):
        tag = '<div data-design-id="did-1" className="foo">'
        result = _upsert_data_design_id_attribute(tag, "did-1")
        assert result == tag

    def test_returns_none_when_different_id_exists(self):
        tag = '<div data-design-id="did-other" className="foo">'
        result = _upsert_data_design_id_attribute(tag, "did-1")
        assert result is None

    def test_returns_none_for_unknown_id_form(self):
        # Dynamic expression: data-design-id={someVar}
        tag = "<div data-design-id={someVar}>"
        result = _upsert_data_design_id_attribute(tag, "did-1")
        assert result is None

    def test_adds_to_self_closing_tag(self):
        result = _upsert_data_design_id_attribute('<img src="x.png" />', "did-1")
        assert 'data-design-id="did-1"' in result
        assert result.endswith("/>") or result.endswith(" />")

    def test_non_string_tag_returns_none(self):
        result = _upsert_data_design_id_attribute(None, "did-1")  # type: ignore
        assert result is None

    def test_empty_design_id_returns_none(self):
        result = _upsert_data_design_id_attribute("<div>", "")
        assert result is None


# ---------------------------------------------------------------------------
# _find_best_opening_tag_by_class_tokens
# ---------------------------------------------------------------------------


class TestFindBestOpeningTagByClassTokens:
    def test_finds_tag_with_matching_class(self):
        content = '<div className="container flex">Content</div>'
        result = _find_best_opening_tag_by_class_tokens(
            content=content,
            class_name="container flex",
            class_tokens=["container", "flex"],
            preferred_tag_name="div",
        )
        assert result is not None
        start, end = result
        assert content[start] == "<"

    def test_returns_none_when_no_class_match(self):
        content = '<div className="other">Content</div>'
        result = _find_best_opening_tag_by_class_tokens(
            content=content,
            class_name="container",
            class_tokens=["container"],
            preferred_tag_name=None,
        )
        assert result is None

    def test_returns_none_for_empty_content(self):
        result = _find_best_opening_tag_by_class_tokens(
            content="",
            class_name="container",
            class_tokens=["container"],
            preferred_tag_name=None,
        )
        assert result is None

    def test_returns_none_for_empty_class_name(self):
        result = _find_best_opening_tag_by_class_tokens(
            content='<div className="container">',
            class_name="",
            class_tokens=["container"],
            preferred_tag_name=None,
        )
        assert result is None

    def test_returns_none_for_empty_class_tokens(self):
        result = _find_best_opening_tag_by_class_tokens(
            content='<div className="container">',
            class_name="container",
            class_tokens=[],
            preferred_tag_name=None,
        )
        assert result is None

    def test_prefers_tag_without_existing_design_id(self):
        content = (
            '<div className="container" data-design-id="other">First</div>'
            '<div className="container">Second</div>'
        )
        result = _find_best_opening_tag_by_class_tokens(
            content=content,
            class_name="container",
            class_tokens=["container"],
            preferred_tag_name=None,
        )
        assert result is not None
        start, end = result
        tag = content[start : end + 1]
        assert "data-design-id" not in tag

    def test_prefers_preferred_tag_name(self):
        content = '<span className="container">Span</span><div className="container">Div</div>'
        result = _find_best_opening_tag_by_class_tokens(
            content=content,
            class_name="container",
            class_tokens=["container"],
            preferred_tag_name="div",
        )
        assert result is not None
        start, end = result
        tag = content[start : end + 1]
        assert tag.startswith("<div")


# ---------------------------------------------------------------------------
# _find_best_component_callsite_opening_tag
# ---------------------------------------------------------------------------


class TestFindBestComponentCallsiteOpeningTag:
    def test_finds_component_with_anchor_match(self):
        content = (
            "<div>\n"
            '  <CardHeader data-design-id="ch-1">\n'
            "    <h2>Hello World</h2>\n"
            "  </CardHeader>\n"
            "</div>"
        )
        result = _find_best_component_callsite_opening_tag(
            content=content,
            component_name="CardHeader",
            anchors=["Hello World"],
        )
        assert result is not None

    def test_returns_none_when_no_anchor_match(self):
        content = "<CardHeader>No matching text here</CardHeader>"
        result = _find_best_component_callsite_opening_tag(
            content=content,
            component_name="CardHeader",
            anchors=["Missing Text"],
        )
        assert result is None

    def test_returns_none_for_empty_content(self):
        result = _find_best_component_callsite_opening_tag(
            content="",
            component_name="CardHeader",
            anchors=["text"],
        )
        assert result is None

    def test_returns_none_for_empty_component_name(self):
        result = _find_best_component_callsite_opening_tag(
            content="<CardHeader>text</CardHeader>",
            component_name="",
            anchors=["text"],
        )
        assert result is None

    def test_returns_none_for_empty_anchors(self):
        result = _find_best_component_callsite_opening_tag(
            content="<CardHeader>text</CardHeader>",
            component_name="CardHeader",
            anchors=[],
        )
        assert result is None

    def test_prefers_component_without_existing_design_id(self):
        content = (
            '<CardHeader data-design-id="existing">Hello</CardHeader><CardHeader>Hello</CardHeader>'
        )
        result = _find_best_component_callsite_opening_tag(
            content=content,
            component_name="CardHeader",
            anchors=["Hello"],
        )
        assert result is not None
        start, end = result
        tag = content[start : end + 1]
        assert "data-design-id" not in tag


# ---------------------------------------------------------------------------
# _infer_component_name_before_index
# ---------------------------------------------------------------------------


class TestInferComponentNameBeforeIndex:
    def test_infers_from_function_declaration(self):
        content = "function CardHeader(props) {\n  return <div>Hello</div>;\n}\n"
        result = _infer_component_name_before_index(content, len(content))
        assert result == "CardHeader"

    def test_returns_none_for_plain_arrow_function(self):
        # The function only detects forwardRef and `function` declarations,
        # not plain const arrow functions.
        content = "const Button = () => {\n  return <div>Hello</div>;\n}\n"
        result = _infer_component_name_before_index(content, len(content))
        assert result is None

    def test_infers_from_forwardRef(self):
        content = (
            "const Input = React.forwardRef((props, ref) => {\n  return <input ref={ref} />;\n});\n"
        )
        result = _infer_component_name_before_index(content, len(content))
        assert result == "Input"

    def test_returns_none_for_empty_content(self):
        result = _infer_component_name_before_index("", 0)
        assert result is None

    def test_returns_none_for_non_string_content(self):
        result = _infer_component_name_before_index(None, 0)  # type: ignore
        assert result is None

    def test_returns_none_when_index_zero_or_negative(self):
        content = "function Header() {}"
        result = _infer_component_name_before_index(content, 0)
        assert result is None

    def test_returns_none_for_non_int_index(self):
        content = "function Header() {}"
        result = _infer_component_name_before_index(content, "bad")  # type: ignore
        assert result is None

    def test_returns_nearest_component(self):
        content = "function Outer() { return null; }\nfunction Inner() { return null; }\n"
        # Index points to end - should find Inner as nearest.
        result = _infer_component_name_before_index(content, len(content))
        assert result == "Inner"


# ---------------------------------------------------------------------------
# _build_line_start_offsets
# ---------------------------------------------------------------------------


class TestBuildLineStartOffsets:
    def test_empty_content(self):
        result = _build_line_start_offsets("")
        assert result == [0]

    def test_single_line(self):
        result = _build_line_start_offsets("hello")
        assert result == [0]

    def test_two_lines(self):
        result = _build_line_start_offsets("line1\nline2")
        assert result == [0, 6]

    def test_three_lines(self):
        result = _build_line_start_offsets("a\nb\nc")
        assert result == [0, 2, 4]

    def test_trailing_newline(self):
        result = _build_line_start_offsets("line\n")
        assert result == [0, 5]

    def test_non_string_returns_initial_offset(self):
        result = _build_line_start_offsets(None)  # type: ignore
        assert result == [0]


# ---------------------------------------------------------------------------
# _pos_to_line_number
# ---------------------------------------------------------------------------


class TestPosToLineNumber:
    def test_pos_zero_is_line_one(self):
        offsets = [0, 6, 12]
        assert _pos_to_line_number(offsets, 0) == 1

    def test_pos_in_second_line(self):
        offsets = [0, 6, 12]
        assert _pos_to_line_number(offsets, 7) == 2

    def test_pos_in_third_line(self):
        offsets = [0, 6, 12]
        assert _pos_to_line_number(offsets, 13) == 3

    def test_empty_offsets_returns_one(self):
        assert _pos_to_line_number([], 0) == 1

    def test_exact_line_boundary(self):
        offsets = [0, 5]
        # Position 5 is the start of line 2
        assert _pos_to_line_number(offsets, 5) == 2


# ---------------------------------------------------------------------------
# _find_best_opening_tag_near_source_location
# ---------------------------------------------------------------------------


class TestFindBestOpeningTagNearSourceLocation:
    def test_finds_tag_at_line(self):
        content = "const x = 1;\n<div data-design-id='d1'>Hello</div>\n"
        result = _find_best_opening_tag_near_source_location(
            content=content, line_no=2, column_no=None
        )
        assert result is not None

    def test_returns_none_for_empty_content(self):
        result = _find_best_opening_tag_near_source_location(content="", line_no=1, column_no=None)
        assert result is None

    def test_returns_none_for_invalid_line_no(self):
        result = _find_best_opening_tag_near_source_location(
            content="<div>Hello</div>", line_no=0, column_no=None
        )
        assert result is None

    def test_returns_none_when_line_out_of_range(self):
        result = _find_best_opening_tag_near_source_location(
            content="<div>Hello</div>", line_no=999, column_no=None
        )
        assert result is None

    def test_returns_tuple_of_ints(self):
        content = "<div>Hello</div>"
        result = _find_best_opening_tag_near_source_location(
            content=content, line_no=1, column_no=1
        )
        assert result is not None
        start, end = result
        assert isinstance(start, int)
        assert isinstance(end, int)

    def test_uses_column_no_as_hint(self):
        content = "<p>First</p>  <div>Second</div>"
        result = _find_best_opening_tag_near_source_location(
            content=content, line_no=1, column_no=15
        )
        assert result is not None


# ---------------------------------------------------------------------------
# _backfill_design_id_in_source_from_react_source (async)
# ---------------------------------------------------------------------------


class TestBackfillFromReactSource:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_context(self):
        change = _make_style_change(element_context=None)
        result = await _backfill_design_id_in_source_from_react_source(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_react_source_not_dict(self):
        # Use a MagicMock context with a non-dict reactSource to bypass Pydantic.
        ctx = MagicMock()
        ctx.reactSource = "not-a-dict"
        change = MagicMock()
        change.elementContext = ctx
        result = await _backfill_design_id_in_source_from_react_source(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_file_name_missing(self):
        ctx = _make_element_context(reactSource={"lineNumber": 5})
        change = _make_style_change(element_context=ctx)
        result = await _backfill_design_id_in_source_from_react_source(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_line_number_missing(self):
        ctx = _make_element_context(reactSource={"fileName": "src/App.tsx"})
        change = _make_style_change(element_context=ctx)
        result = await _backfill_design_id_in_source_from_react_source(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_file_read_fails(self):
        ctx = _make_element_context(reactSource={"fileName": "src/App.tsx", "lineNumber": 5})
        change = _make_style_change(element_context=ctx)
        sandbox = _make_sandbox(read_raises=FileNotFoundError("not found"))
        result = await _backfill_design_id_in_source_from_react_source(
            sandbox=sandbox,
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_backfills_design_id_at_line(self):
        content = '<div className="foo">Hello</div>\n'
        ctx = _make_element_context(
            reactSource={"fileName": "src/App.tsx", "lineNumber": 1, "columnNumber": 1}
        )
        change = _make_style_change(element_context=ctx)
        sandbox = _make_sandbox(read_response=content)
        result = await _backfill_design_id_in_source_from_react_source(
            sandbox=sandbox,
            change=change,
            design_id="did-1",
        )
        assert result is not None
        resolved_path, updated_content = result
        assert 'data-design-id="did-1"' in updated_content


# ---------------------------------------------------------------------------
# _backfill_design_id_in_source_from_text_search (async)
# ---------------------------------------------------------------------------


class TestBackfillFromTextSearch:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_context(self):
        change = _make_style_change(element_context=None)
        result = await _backfill_design_id_in_source_from_text_search(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_text_content_not_string(self):
        ctx = _make_element_context(textContent=None)
        change = _make_style_change(element_context=ctx)
        result = await _backfill_design_id_in_source_from_text_search(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_text_content_empty(self):
        ctx = _make_element_context(textContent="")
        change = _make_style_change(element_context=ctx)
        result = await _backfill_design_id_in_source_from_text_search(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_text_is_na(self):
        ctx = _make_element_context(textContent="N/A")
        change = _make_style_change(element_context=ctx)
        result = await _backfill_design_id_in_source_from_text_search(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_search_returns_nothing(self):
        ctx = _make_element_context(textContent="Hello World")
        change = _make_style_change(element_context=ctx)
        # Search returns empty
        sandbox = _make_sandbox(run_command_response="")
        result = await _backfill_design_id_in_source_from_text_search(
            sandbox=sandbox,
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_backfills_design_id_when_text_found(self):
        text = "Hello World"
        content = f'<p className="greeting">{text}</p>'
        ctx = _make_element_context(textContent=text)
        change = _make_style_change(element_context=ctx)

        search_output = f"/workspace/src/App.tsx:1: {text}\n"
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(return_value=search_output)
        sandbox.read_file = AsyncMock(return_value=content)

        result = await _backfill_design_id_in_source_from_text_search(
            sandbox=sandbox,
            change=change,
            design_id="did-1",
        )
        assert result is not None
        resolved_path, updated_content = result
        assert 'data-design-id="did-1"' in updated_content


# ---------------------------------------------------------------------------
# _backfill_design_id_in_source_from_class_name (async)
# ---------------------------------------------------------------------------


class TestBackfillFromClassName:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_context(self):
        change = _make_style_change(element_context=None)
        result = await _backfill_design_id_in_source_from_class_name(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_class_name_missing(self):
        ctx = _make_element_context(className=None, outerHTML=None)
        change = _make_style_change(element_context=ctx)
        result = await _backfill_design_id_in_source_from_class_name(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_search_finds_nothing(self):
        ctx = _make_element_context(className="container flex")
        change = _make_style_change(element_context=ctx)
        sandbox = _make_sandbox(run_command_response="")
        result = await _backfill_design_id_in_source_from_class_name(
            sandbox=sandbox,
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_extracts_class_from_outer_html_when_class_name_missing(self):
        outer_html = '<div class="flex container">Content</div>'
        ctx = _make_element_context(className=None, outerHTML=outer_html)
        change = _make_style_change(element_context=ctx)
        sandbox = _make_sandbox(run_command_response="")
        # Should attempt search (even if nothing found)
        result = await _backfill_design_id_in_source_from_class_name(
            sandbox=sandbox,
            change=change,
            design_id="did-1",
        )
        # With empty search result - returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_backfills_when_exact_class_match_found(self):
        class_name = "flex container"
        content = f'<div className="{class_name}">Content</div>'
        ctx = _make_element_context(className=class_name, tagName="div")
        change = _make_style_change(element_context=ctx)

        search_output = f"/workspace/src/App.tsx:1: content\n"
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(return_value=search_output)
        sandbox.read_file = AsyncMock(return_value=content)

        result = await _backfill_design_id_in_source_from_class_name(
            sandbox=sandbox,
            change=change,
            design_id="did-1",
        )
        assert result is not None
        resolved_path, updated_content = result
        assert 'data-design-id="did-1"' in updated_content


# ---------------------------------------------------------------------------
# _backfill_design_id_in_source_from_component_callsite (async)
# ---------------------------------------------------------------------------


class TestBackfillFromComponentCallsite:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_context(self):
        change = _make_style_change(element_context=None)
        result = await _backfill_design_id_in_source_from_component_callsite(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_class_name_missing(self):
        ctx = _make_element_context(className=None, outerHTML=None)
        change = _make_style_change(element_context=ctx)
        result = await _backfill_design_id_in_source_from_component_callsite(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_anchors(self):
        ctx = _make_element_context(
            className="flex container",
            textContent=None,
        )
        change = _make_style_change(element_context=ctx)
        result = await _backfill_design_id_in_source_from_component_callsite(
            sandbox=_make_sandbox(),
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_definition_not_found(self):
        ctx = _make_element_context(
            className="flex container",
            textContent="Hello World",
        )
        change = _make_style_change(element_context=ctx)
        # All searches return empty
        sandbox = _make_sandbox(run_command_response="")
        result = await _backfill_design_id_in_source_from_component_callsite(
            sandbox=sandbox,
            change=change,
            design_id="did-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_component_names_inferred(self):
        # Definition file found but doesn't contain function declarations.
        ctx = _make_element_context(
            className="my-class",
            textContent="Sample Text",
        )
        change = _make_style_change(element_context=ctx)
        definition_content = 'const x = { className: "my-class" };'  # No component decl.

        search_output = "/workspace/src/utils.ts:1: my-class\n"
        sandbox = MagicMock()
        sandbox.run_command = AsyncMock(return_value=search_output)
        sandbox.read_file = AsyncMock(return_value=definition_content)

        result = await _backfill_design_id_in_source_from_component_callsite(
            sandbox=sandbox,
            change=change,
            design_id="did-1",
        )
        assert result is None
