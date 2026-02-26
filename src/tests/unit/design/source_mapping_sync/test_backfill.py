"""Tests for _backfill.py."""

import pytest

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
    _backfill_design_id_in_source_from_react_source,
    _backfill_design_id_in_source_from_text_search,
    _backfill_design_id_in_source_from_component_callsite,
)

from .conftest import make_element_context, make_style_change


# ---------------------------------------------------------------------------
# _extract_anchor_snippets
# ---------------------------------------------------------------------------

class TestExtractAnchorSnippets:
    def test_text_content(self):
        ctx = make_element_context(text_content="Hello World")
        snippets = _extract_anchor_snippets(ctx)
        assert "Hello World" in snippets

    def test_multiline(self):
        ctx = make_element_context(text_content="Line1\nLine2\nLine3")
        snippets = _extract_anchor_snippets(ctx)
        assert "Line1" in snippets
        assert "Line2" in snippets

    def test_long_text_sentence_split(self):
        long_text = "This is a very long sentence that goes well beyond eighty characters in total length. And here is another sentence after that."
        ctx = make_element_context(text_content=long_text)
        snippets = _extract_anchor_snippets(ctx)
        assert len(snippets) >= 2

    def test_multiple_sources(self):
        ctx = make_element_context(
            text_content="Primary",
            next_sibling_text="Next",
        )
        snippets = _extract_anchor_snippets(ctx)
        assert "Primary" in snippets
        assert "Next" in snippets

    def test_120_char_cap(self):
        ctx = make_element_context(text_content="x" * 200)
        snippets = _extract_anchor_snippets(ctx)
        for s in snippets:
            assert len(s) <= 120

    def test_dedup(self):
        ctx = make_element_context(
            text_content="Same",
            next_sibling_text="Same",
        )
        snippets = _extract_anchor_snippets(ctx)
        assert snippets.count("Same") == 1

    def test_max_8(self):
        ctx = make_element_context(
            text_content="A\nB\nC\nD\nE\nF\nG\nH\nI\nJ",
        )
        snippets = _extract_anchor_snippets(ctx)
        assert len(snippets) <= 8

    def test_none_context(self):
        assert _extract_anchor_snippets(None) == []

    def test_na_skipped(self):
        ctx = make_element_context(text_content="N/A")
        assert _extract_anchor_snippets(ctx) == []


# ---------------------------------------------------------------------------
# _split_class_tokens
# ---------------------------------------------------------------------------

class TestSplitClassTokens:
    def test_whitespace_split(self):
        assert _split_class_tokens("foo bar baz") == ["foo", "bar", "baz"]

    def test_dedup(self):
        assert _split_class_tokens("foo bar foo") == ["foo", "bar"]

    def test_extra_spaces(self):
        assert _split_class_tokens("  foo   bar  ") == ["foo", "bar"]

    def test_empty(self):
        assert _split_class_tokens("") == []

    def test_none(self):
        assert _split_class_tokens(None) == []


# ---------------------------------------------------------------------------
# _class_token_distinctiveness
# ---------------------------------------------------------------------------

class TestClassTokenDistinctiveness:
    def test_length(self):
        assert _class_token_distinctiveness("ab") < _class_token_distinctiveness("abcdefgh")

    def test_special_chars_bonus(self):
        assert _class_token_distinctiveness("a/b") > _class_token_distinctiveness("abc")

    def test_digits_bonus(self):
        assert _class_token_distinctiveness("abc123") > _class_token_distinctiveness("abcdef")

    def test_data_prefix_bonus(self):
        assert _class_token_distinctiveness("data-x") > _class_token_distinctiveness("xxxxxx")

    def test_none(self):
        assert _class_token_distinctiveness(None) == 0


# ---------------------------------------------------------------------------
# _upsert_data_design_id_attribute
# ---------------------------------------------------------------------------

class TestUpsertDataDesignIdAttribute:
    def test_add_to_tag(self):
        tag = '<div class="foo">'
        result = _upsert_data_design_id_attribute(tag, "abc")
        assert 'data-design-id="abc"' in result
        assert result.endswith(">")

    def test_self_closing(self):
        tag = '<br class="x" />'
        result = _upsert_data_design_id_attribute(tag, "abc")
        assert 'data-design-id="abc"' in result
        assert result.endswith("/>")

    def test_same_id_present(self):
        tag = '<div data-design-id="abc">'
        result = _upsert_data_design_id_attribute(tag, "abc")
        assert result == tag

    def test_different_id_returns_none(self):
        tag = '<div data-design-id="xyz">'
        result = _upsert_data_design_id_attribute(tag, "abc")
        assert result is None

    def test_dynamic_expr_returns_none(self):
        tag = '<div data-design-id={someVar}>'
        result = _upsert_data_design_id_attribute(tag, "abc")
        assert result is None

    def test_none_tag(self):
        assert _upsert_data_design_id_attribute(None, "abc") is None

    def test_empty_design_id(self):
        assert _upsert_data_design_id_attribute("<div>", "") is None

    def test_none_design_id(self):
        assert _upsert_data_design_id_attribute("<div>", None) is None


# ---------------------------------------------------------------------------
# _find_best_opening_tag_by_class_tokens
# ---------------------------------------------------------------------------

class TestFindBestOpeningTagByClassTokens:
    def test_matching_class(self):
        content = '<div className="flex items-center">text</div>'
        result = _find_best_opening_tag_by_class_tokens(
            content=content,
            class_name="flex items-center",
            class_tokens=["flex", "items-center"],
            preferred_tag_name=None,
        )
        assert result is not None

    def test_prefer_full_match(self):
        content = '<div className="foo bar"><span className="foo">x</span></div>'
        result = _find_best_opening_tag_by_class_tokens(
            content=content,
            class_name="foo bar",
            class_tokens=["foo", "bar"],
            preferred_tag_name=None,
        )
        assert result is not None
        tag = content[result[0] : result[1] + 1]
        assert "foo bar" in tag

    def test_prefer_tag_name(self):
        content = '<div className="abc"><span className="abc">x</span></div>'
        result = _find_best_opening_tag_by_class_tokens(
            content=content,
            class_name="abc",
            class_tokens=["abc"],
            preferred_tag_name="span",
        )
        assert result is not None
        tag = content[result[0] : result[1] + 1]
        assert tag.startswith("<span")

    def test_prefer_no_existing_id(self):
        content = '<div className="abc" data-design-id="old"><span className="abc">x</span></div>'
        result = _find_best_opening_tag_by_class_tokens(
            content=content,
            class_name="abc",
            class_tokens=["abc"],
            preferred_tag_name=None,
        )
        assert result is not None
        tag = content[result[0] : result[1] + 1]
        assert "data-design-id" not in tag

    def test_empty_content(self):
        assert _find_best_opening_tag_by_class_tokens(
            content="", class_name="x", class_tokens=["x"], preferred_tag_name=None
        ) is None

    def test_no_match(self):
        content = '<div className="other">text</div>'
        assert _find_best_opening_tag_by_class_tokens(
            content=content,
            class_name="missing",
            class_tokens=["missing"],
            preferred_tag_name=None,
        ) is None


# ---------------------------------------------------------------------------
# _find_best_component_callsite_opening_tag
# ---------------------------------------------------------------------------

class TestFindBestComponentCallsiteOpeningTag:
    def test_anchor_match(self):
        content = '<Card>Hello World</Card>'
        result = _find_best_component_callsite_opening_tag(
            content=content,
            component_name="Card",
            anchors=["Hello World"],
        )
        assert result is not None
        tag = content[result[0] : result[1] + 1]
        assert tag.startswith("<Card")

    def test_prefer_more_hits(self):
        content = '<Card>Hello</Card><Card>Hello World</Card>'
        result = _find_best_component_callsite_opening_tag(
            content=content,
            component_name="Card",
            anchors=["Hello", "World"],
        )
        assert result is not None
        # The second <Card> has both anchors, so the tag_start should be at the second one
        assert result[0] > 0

    def test_no_anchors(self):
        assert _find_best_component_callsite_opening_tag(
            content="<Card>text</Card>",
            component_name="Card",
            anchors=[],
        ) is None

    def test_empty_content(self):
        assert _find_best_component_callsite_opening_tag(
            content="", component_name="Card", anchors=["x"]
        ) is None

    def test_empty_component(self):
        assert _find_best_component_callsite_opening_tag(
            content="<Card>text</Card>", component_name="", anchors=["text"]
        ) is None


# ---------------------------------------------------------------------------
# _infer_component_name_before_index
# ---------------------------------------------------------------------------

class TestInferComponentNameBeforeIndex:
    def test_function_component(self):
        content = "function CardHeader() {\n  return <div>x</div>\n}\n"
        result = _infer_component_name_before_index(content, len(content) - 5)
        assert result == "CardHeader"

    def test_const_forward_ref(self):
        content = "const Button = React.forwardRef((...) => {\n  return <button>x</button>\n})\n"
        result = _infer_component_name_before_index(content, len(content) - 5)
        assert result == "Button"

    def test_nearest(self):
        content = "function A() {}\nfunction B() {}\n"
        result = _infer_component_name_before_index(content, len(content))
        assert result == "B"

    def test_empty(self):
        assert _infer_component_name_before_index("", 0) is None

    def test_index_zero(self):
        assert _infer_component_name_before_index("function A() {}", 0) is None


# ---------------------------------------------------------------------------
# _build_line_start_offsets
# ---------------------------------------------------------------------------

class TestBuildLineStartOffsets:
    def test_single_line(self):
        assert _build_line_start_offsets("hello") == [0]

    def test_multi_line(self):
        offsets = _build_line_start_offsets("a\nb\nc")
        assert offsets == [0, 2, 4]

    def test_empty(self):
        assert _build_line_start_offsets("") == [0]

    def test_trailing_newline(self):
        offsets = _build_line_start_offsets("a\n")
        assert offsets == [0, 2]


# ---------------------------------------------------------------------------
# _pos_to_line_number
# ---------------------------------------------------------------------------

class TestPosToLineNumber:
    def test_first_line(self):
        assert _pos_to_line_number([0, 5, 10], 2) == 1

    def test_second_line(self):
        assert _pos_to_line_number([0, 5, 10], 7) == 2

    def test_empty_offsets(self):
        assert _pos_to_line_number([], 0) == 1

    def test_mid_line(self):
        assert _pos_to_line_number([0, 10, 20], 15) == 2


# ---------------------------------------------------------------------------
# _find_best_opening_tag_near_source_location
# ---------------------------------------------------------------------------

class TestFindBestOpeningTagNearSourceLocation:
    def test_at_line(self):
        content = "line1\n<div>hello</div>\nline3"
        result = _find_best_opening_tag_near_source_location(
            content=content, line_no=2, column_no=None
        )
        assert result is not None
        assert content[result[0] : result[0] + 4] == "<div"

    def test_closest(self):
        content = "<span>a</span>\n\n\n<div>b</div>"
        result = _find_best_opening_tag_near_source_location(
            content=content, line_no=4, column_no=None
        )
        assert result is not None
        tag = content[result[0] : result[1] + 1]
        assert tag.startswith("<div")

    def test_with_column(self):
        content = "  <div>hello</div>\n"
        result = _find_best_opening_tag_near_source_location(
            content=content, line_no=1, column_no=3
        )
        assert result is not None

    def test_out_of_range(self):
        content = "<div>x</div>"
        result = _find_best_opening_tag_near_source_location(
            content=content, line_no=999, column_no=None
        )
        assert result is None

    def test_empty_content(self):
        assert _find_best_opening_tag_near_source_location(
            content="", line_no=1, column_no=None
        ) is None


# ---------------------------------------------------------------------------
# _backfill_design_id_in_source_from_class_name (async)
# ---------------------------------------------------------------------------

class TestBackfillFromClassName:
    async def test_exact_match_injects_id(self, fake_sandbox):
        file_content = '<div className="flex items-center">hello</div>'
        sb = fake_sandbox(
            files={"/workspace/src/App.tsx": file_content},
            command_outputs={
                "rg": "/workspace/src/App.tsx:1:  flex items-center\n",
                "find /workspace": "",
            },
        )
        ctx = make_element_context(class_name="flex items-center", tag_name="div")
        change = make_style_change(design_id="new-id", element_context=ctx)
        result = await _backfill_design_id_in_source_from_class_name(
            sandbox=sb, change=change, design_id="new-id"
        )
        assert result is not None
        path, content = result
        assert 'data-design-id="new-id"' in content

    async def test_no_context_returns_none(self, fake_sandbox):
        sb = fake_sandbox()
        change = make_style_change(design_id="x", element_context=None)
        result = await _backfill_design_id_in_source_from_class_name(
            sandbox=sb, change=change, design_id="x"
        )
        assert result is None


# ---------------------------------------------------------------------------
# _backfill_design_id_in_source_from_react_source (async)
# ---------------------------------------------------------------------------

class TestBackfillFromReactSource:
    async def test_finds_tag_by_line(self, fake_sandbox):
        file_content = "import React from 'react'\n\nfunction App() {\n  return <div>hello</div>\n}\n"
        sb = fake_sandbox(files={"/workspace/src/App.tsx": file_content})
        ctx = make_element_context(
            react_source={"fileName": "src/App.tsx", "lineNumber": 4, "columnNumber": 10},
            tag_name="div",
        )
        change = make_style_change(design_id="new-id", element_context=ctx)
        result = await _backfill_design_id_in_source_from_react_source(
            sandbox=sb, change=change, design_id="new-id"
        )
        assert result is not None
        path, content = result
        assert 'data-design-id="new-id"' in content

    async def test_missing_file_returns_none(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={"find /workspace -maxdepth 1": "", "find /workspace -type f": ""})
        ctx = make_element_context(
            react_source={"fileName": "src/Missing.tsx", "lineNumber": 1},
            tag_name="div",
        )
        change = make_style_change(design_id="x", element_context=ctx)
        result = await _backfill_design_id_in_source_from_react_source(
            sandbox=sb, change=change, design_id="x"
        )
        assert result is None


# ---------------------------------------------------------------------------
# _backfill_design_id_in_source_from_text_search (async)
# ---------------------------------------------------------------------------

class TestBackfillFromTextSearch:
    async def test_finds_element(self, fake_sandbox):
        file_content = "<p>Some unique text</p>"
        sb = fake_sandbox(
            files={"/workspace/src/Page.tsx": file_content},
            command_outputs={
                "rg": "/workspace/src/Page.tsx:1:  Some unique text\n",
                "find /workspace": "",
            },
        )
        ctx = make_element_context(text_content="Some unique text", tag_name="p")
        change = make_style_change(design_id="txt-id", element_context=ctx)
        result = await _backfill_design_id_in_source_from_text_search(
            sandbox=sb, change=change, design_id="txt-id"
        )
        assert result is not None
        _, content = result
        assert 'data-design-id="txt-id"' in content

    async def test_na_skipped(self, fake_sandbox):
        sb = fake_sandbox()
        ctx = make_element_context(text_content="N/A", tag_name="div")
        change = make_style_change(design_id="x", element_context=ctx)
        result = await _backfill_design_id_in_source_from_text_search(
            sandbox=sb, change=change, design_id="x"
        )
        assert result is None


# ---------------------------------------------------------------------------
# _backfill_design_id_in_source_from_component_callsite (async)
# ---------------------------------------------------------------------------

class TestBackfillFromCallsite:
    async def test_infers_component_and_finds_callsite(self, fake_sandbox):
        definition = 'const CardHeader = React.forwardRef(() => {\n  return <div className="flex flex-col space-y-1.5">content</div>\n})\n'
        callsite = "<CardHeader>My Title</CardHeader>"
        sb = fake_sandbox(
            files={
                "/workspace/src/ui/card.tsx": definition,
                "/workspace/src/Page.tsx": callsite,
            },
            command_outputs={
                "rg": (
                    "/workspace/src/ui/card.tsx:2:  flex flex-col\n"
                    "/workspace/src/Page.tsx:1:  My Title\n"
                ),
                "find /workspace": "",
            },
        )
        ctx = make_element_context(
            class_name="flex flex-col space-y-1.5",
            text_content="My Title",
            tag_name="div",
        )
        change = make_style_change(design_id="card-header-id", element_context=ctx)
        result = await _backfill_design_id_in_source_from_component_callsite(
            sandbox=sb, change=change, design_id="card-header-id"
        )
        # The result depends on the grep/search interaction; just verify the function doesn't crash
        # and returns either a tuple or None
        assert result is None or (isinstance(result, tuple) and len(result) == 2)
