"""Unit tests for ii_agent.engine.v1.models.message module.

Tests cover:
- Message creation with defaults
- get_content_string() method for various content types
- content_is_valid() method
- to_dict() serialization
- to_function_call_dict() serialization
- from_dict() reconstruction
- MessageReferences, UrlCitation, DocumentCitation, Citations models
"""
import json
from time import time
from unittest.mock import MagicMock

import pytest

from ii_agent.engine.v1.models.message import (
    Citations,
    DocumentCitation,
    Message,
    MessageReferences,
    UrlCitation,
)
from ii_agent.engine.v1.models.metrics import Metrics


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_message():
    """Return a minimal Message with only role set."""
    return Message(role="user", content="Hello, world!")


@pytest.fixture
def assistant_message():
    """Return an assistant message with tool calls."""
    return Message(
        role="assistant",
        content="I will call a tool.",
        tool_calls=[{"id": "call_abc", "type": "function", "function": {"name": "search"}}],
    )


@pytest.fixture
def tool_result_message():
    """Return a tool result message."""
    return Message(
        role="tool",
        content="Tool result here",
        tool_call_id="call_abc",
        tool_name="search",
        tool_args={"query": "test"},
    )


@pytest.fixture
def citations_obj():
    """Return a Citations object with URL and document citations."""
    return Citations(
        raw={"source": "web"},
        urls=[UrlCitation(url="https://example.com", title="Example")],
        documents=[DocumentCitation(document_title="Doc A", cited_text="Some text", file_name="doc_a.pdf")],
    )


@pytest.fixture
def references_obj():
    """Return a MessageReferences object."""
    return MessageReferences(
        query="test query",
        references=[{"id": "ref1", "text": "reference text"}, "plain string ref"],
        time=0.5,
    )


# ---------------------------------------------------------------------------
# MessageReferences model tests
# ---------------------------------------------------------------------------


class TestMessageReferences:
    def test_creation_with_all_fields(self):
        ref = MessageReferences(
            query="test query",
            references=[{"id": "1", "content": "text"}],
            time=1.23,
        )
        assert ref.query == "test query"
        assert ref.references == [{"id": "1", "content": "text"}]
        assert ref.time == 1.23

    def test_creation_with_required_field_only(self):
        ref = MessageReferences(query="only query")
        assert ref.query == "only query"
        assert ref.references is None
        assert ref.time is None

    def test_references_can_be_string_list(self):
        ref = MessageReferences(query="q", references=["str1", "str2"])
        assert ref.references == ["str1", "str2"]

    def test_references_can_be_mixed_list(self):
        ref = MessageReferences(query="q", references=[{"key": "val"}, "string"])
        assert len(ref.references) == 2

    def test_model_dump_includes_all_fields(self):
        ref = MessageReferences(query="dump test", references=[{"x": 1}], time=0.1)
        dumped = ref.model_dump()
        assert dumped["query"] == "dump test"
        assert dumped["references"] == [{"x": 1}]
        assert dumped["time"] == 0.1


# ---------------------------------------------------------------------------
# UrlCitation model tests
# ---------------------------------------------------------------------------


class TestUrlCitation:
    def test_creation_with_all_fields(self):
        citation = UrlCitation(url="https://example.com", title="Example Page")
        assert citation.url == "https://example.com"
        assert citation.title == "Example Page"

    def test_creation_with_defaults(self):
        citation = UrlCitation()
        assert citation.url is None
        assert citation.title is None

    def test_creation_url_only(self):
        citation = UrlCitation(url="https://only-url.com")
        assert citation.url == "https://only-url.com"
        assert citation.title is None

    def test_creation_title_only(self):
        citation = UrlCitation(title="Only Title")
        assert citation.url is None
        assert citation.title == "Only Title"

    def test_model_dump(self):
        citation = UrlCitation(url="https://test.com", title="Test")
        dumped = citation.model_dump()
        assert dumped["url"] == "https://test.com"
        assert dumped["title"] == "Test"


# ---------------------------------------------------------------------------
# DocumentCitation model tests
# ---------------------------------------------------------------------------


class TestDocumentCitation:
    def test_creation_with_all_fields(self):
        citation = DocumentCitation(
            document_title="Research Paper",
            cited_text="The key finding is ...",
            file_name="paper.pdf",
        )
        assert citation.document_title == "Research Paper"
        assert citation.cited_text == "The key finding is ..."
        assert citation.file_name == "paper.pdf"

    def test_creation_with_defaults(self):
        citation = DocumentCitation()
        assert citation.document_title is None
        assert citation.cited_text is None
        assert citation.file_name is None

    def test_partial_creation(self):
        citation = DocumentCitation(document_title="Title Only")
        assert citation.document_title == "Title Only"
        assert citation.cited_text is None
        assert citation.file_name is None

    def test_model_dump_returns_dict(self):
        citation = DocumentCitation(document_title="Doc", cited_text="Text", file_name="f.pdf")
        dumped = citation.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["document_title"] == "Doc"


# ---------------------------------------------------------------------------
# Citations model tests
# ---------------------------------------------------------------------------


class TestCitations:
    def test_creation_with_all_fields(self, citations_obj):
        assert citations_obj.raw == {"source": "web"}
        assert len(citations_obj.urls) == 1
        assert len(citations_obj.documents) == 1

    def test_creation_with_defaults(self):
        citations = Citations()
        assert citations.raw is None
        assert citations.urls is None
        assert citations.documents is None

    def test_url_citations_list(self):
        citations = Citations(
            urls=[
                UrlCitation(url="https://a.com", title="A"),
                UrlCitation(url="https://b.com", title="B"),
            ]
        )
        assert len(citations.urls) == 2

    def test_model_dump_excludes_none(self):
        citations = Citations(urls=[UrlCitation(url="https://example.com")])
        dumped = citations.model_dump(exclude_none=True)
        assert "raw" not in dumped
        assert "documents" not in dumped
        assert "urls" in dumped

    def test_model_dump_with_raw(self):
        citations = Citations(raw={"data": [1, 2, 3]})
        dumped = citations.model_dump()
        assert dumped["raw"] == {"data": [1, 2, 3]}


# ---------------------------------------------------------------------------
# Message creation and defaults
# ---------------------------------------------------------------------------


class TestMessageCreation:
    def test_basic_creation_with_role_and_content(self):
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_id_is_auto_generated_as_uuid(self):
        msg1 = Message(role="user")
        msg2 = Message(role="user")
        assert msg1.id != msg2.id
        assert isinstance(msg1.id, str)
        assert len(msg1.id) == 36  # UUID4 with dashes

    def test_default_content_is_none(self):
        msg = Message(role="user")
        assert msg.content is None

    def test_default_model_is_none(self):
        msg = Message(role="assistant")
        assert msg.model is None

    def test_default_name_is_none(self):
        msg = Message(role="user")
        assert msg.name is None

    def test_default_tool_calls_is_none(self):
        msg = Message(role="user")
        assert msg.tool_calls is None

    def test_default_stop_after_tool_call_is_false(self):
        msg = Message(role="user")
        assert msg.stop_after_tool_call is False

    def test_default_add_to_agent_memory_is_true(self):
        msg = Message(role="user")
        assert msg.add_to_agent_memory is True

    def test_default_from_history_is_false(self):
        msg = Message(role="user")
        assert msg.from_history is False

    def test_default_is_summary_is_false(self):
        msg = Message(role="user")
        assert msg.is_summary is False

    def test_default_metrics_is_empty_metrics(self):
        msg = Message(role="user")
        assert isinstance(msg.metrics, Metrics)

    def test_created_at_is_unix_timestamp(self):
        before = int(time())
        msg = Message(role="user")
        after = int(time())
        assert before <= msg.created_at <= after

    def test_content_as_list(self):
        msg = Message(role="user", content=[{"type": "text", "text": "Hello"}])
        assert isinstance(msg.content, list)

    def test_custom_id_can_be_set(self):
        msg = Message(role="user", id="custom-id-123")
        assert msg.id == "custom-id-123"

    def test_all_optional_fields_none_by_default(self):
        msg = Message(role="user")
        assert msg.audio is None
        assert msg.images is None
        assert msg.videos is None
        assert msg.files is None
        assert msg.audio_output is None
        assert msg.image_output is None
        assert msg.video_output is None
        assert msg.file_output is None
        assert msg.redacted_reasoning_content is None
        assert msg.provider_data is None
        assert msg.citations is None
        assert msg.reasoning_content is None
        assert msg.tool_name is None
        assert msg.tool_args is None
        assert msg.tool_call_error is None
        assert msg.references is None

    def test_system_role(self):
        msg = Message(role="system", content="You are a helpful assistant.")
        assert msg.role == "system"


# ---------------------------------------------------------------------------
# get_content_string() tests
# ---------------------------------------------------------------------------


class TestGetContentString:
    def test_string_content_returns_as_is(self):
        msg = Message(role="user", content="Hello, world!")
        assert msg.get_content_string() == "Hello, world!"

    def test_empty_string_content_returns_empty_string(self):
        msg = Message(role="user", content="")
        assert msg.get_content_string() == ""

    def test_none_content_returns_empty_string(self):
        msg = Message(role="user", content=None)
        assert msg.get_content_string() == ""

    def test_list_content_with_text_dict_returns_text(self):
        msg = Message(role="user", content=[{"type": "text", "text": "Hello from list"}])
        assert msg.get_content_string() == "Hello from list"

    def test_list_content_with_text_dict_returns_first_text_only(self):
        msg = Message(
            role="user",
            content=[
                {"type": "text", "text": "First"},
                {"type": "text", "text": "Second"},
            ],
        )
        assert msg.get_content_string() == "First"

    def test_list_content_without_text_key_returns_json_dumps(self):
        content = [{"type": "image", "url": "https://example.com/img.png"}]
        msg = Message(role="user", content=content)
        result = msg.get_content_string()
        assert result == json.dumps(content)

    def test_empty_list_content_returns_json_empty_list(self):
        msg = Message(role="user", content=[])
        # Empty list: isinstance check passes, len > 0 check fails, falls to json.dumps
        result = msg.get_content_string()
        assert result == json.dumps([])

    def test_list_content_with_dict_missing_text_key(self):
        content = [{"type": "image_url", "image_url": {"url": "https://img.com"}}]
        msg = Message(role="user", content=content)
        result = msg.get_content_string()
        # No "text" key in first dict, falls to json.dumps
        assert result == json.dumps(content)

    def test_string_content_with_special_characters(self):
        content = "Hello\nWorld\t!"
        msg = Message(role="user", content=content)
        assert msg.get_content_string() == content

    def test_list_content_text_dict_with_empty_text(self):
        msg = Message(role="user", content=[{"type": "text", "text": ""}])
        assert msg.get_content_string() == ""


# ---------------------------------------------------------------------------
# content_is_valid() tests
# ---------------------------------------------------------------------------


class TestContentIsValid:
    def test_non_empty_string_is_valid(self):
        msg = Message(role="user", content="Hello")
        assert msg.content_is_valid() is True

    def test_single_space_string_is_valid(self):
        msg = Message(role="user", content=" ")
        assert msg.content_is_valid() is True

    def test_none_content_is_not_valid(self):
        msg = Message(role="user", content=None)
        assert msg.content_is_valid() is False

    def test_empty_list_is_not_valid(self):
        msg = Message(role="user", content=[])
        assert msg.content_is_valid() is False

    def test_non_empty_list_is_valid(self):
        msg = Message(role="user", content=[{"text": "Hello"}])
        assert msg.content_is_valid() is True

    def test_empty_string_is_not_valid(self):
        msg = Message(role="user", content="")
        assert msg.content_is_valid() is False

    def test_list_with_multiple_items_is_valid(self):
        msg = Message(role="user", content=[{"text": "a"}, {"text": "b"}])
        assert msg.content_is_valid() is True


# ---------------------------------------------------------------------------
# to_dict() tests
# ---------------------------------------------------------------------------


class TestToDict:
    def test_basic_serialization(self, basic_message):
        d = basic_message.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hello, world!"
        assert "id" in d
        assert "created_at" in d

    def test_none_values_are_excluded(self):
        msg = Message(role="user", content="Test")
        d = msg.to_dict()
        # name, tool_call_id, model, etc. should not be in dict if None
        assert "name" not in d
        assert "tool_call_id" not in d
        assert "tool_name" not in d
        assert "tool_args" not in d
        assert "reasoning_content" not in d

    def test_tool_calls_included_when_set(self, assistant_message):
        d = assistant_message.to_dict()
        assert "tool_calls" in d
        assert len(d["tool_calls"]) == 1
        assert d["tool_calls"][0]["id"] == "call_abc"

    def test_citations_included_when_set(self, citations_obj):
        msg = Message(role="assistant", content="See sources.", citations=citations_obj)
        d = msg.to_dict()
        assert "citations" in d
        assert "urls" in d["citations"]

    def test_citations_model_dumped_exclude_none(self, citations_obj):
        msg = Message(role="assistant", citations=citations_obj)
        d = msg.to_dict()
        # raw field is set so it should be included
        assert "raw" in d["citations"]

    def test_references_included_when_set(self, references_obj):
        msg = Message(role="user", content="Test", references=references_obj)
        d = msg.to_dict()
        assert "references" in d
        assert d["references"]["query"] == "test query"

    def test_metrics_included_when_non_empty(self):
        metrics = Metrics(input_tokens=100, output_tokens=50)
        msg = Message(role="assistant", content="Response", metrics=metrics)
        d = msg.to_dict()
        assert "metrics" in d
        assert d["metrics"]["input_tokens"] == 100

    def test_metrics_excluded_when_empty(self):
        msg = Message(role="user", content="Hello")
        # Default Metrics has all zeros, to_dict returns empty dict
        d = msg.to_dict()
        assert "metrics" not in d

    def test_add_to_agent_memory_excluded_when_true(self):
        msg = Message(role="user", add_to_agent_memory=True)
        d = msg.to_dict()
        assert "add_to_agent_memory" not in d

    def test_add_to_agent_memory_included_when_false(self):
        msg = Message(role="user", add_to_agent_memory=False)
        d = msg.to_dict()
        assert "add_to_agent_memory" in d
        assert d["add_to_agent_memory"] is False

    def test_is_summary_excluded_when_false(self):
        msg = Message(role="user")
        d = msg.to_dict()
        assert "is_summary" not in d

    def test_is_summary_included_when_true(self):
        msg = Message(role="user", is_summary=True)
        d = msg.to_dict()
        assert "is_summary" in d
        assert d["is_summary"] is True

    def test_from_history_included_when_true(self):
        msg = Message(role="user", from_history=True)
        d = msg.to_dict()
        assert "from_history" in d
        assert d["from_history"] is True

    def test_stop_after_tool_call_included(self):
        msg = Message(role="user", stop_after_tool_call=True)
        d = msg.to_dict()
        assert d["stop_after_tool_call"] is True

    def test_created_at_always_included(self):
        msg = Message(role="user")
        d = msg.to_dict()
        assert "created_at" in d
        assert isinstance(d["created_at"], int)

    def test_reasoning_content_included_when_set(self):
        msg = Message(role="assistant", content="Resp", reasoning_content="My reasoning")
        d = msg.to_dict()
        assert "reasoning_content" in d
        assert d["reasoning_content"] == "My reasoning"

    def test_redacted_reasoning_content_included_when_set(self):
        msg = Message(role="assistant", redacted_reasoning_content="encrypted_data")
        d = msg.to_dict()
        assert "redacted_reasoning_content" in d

    def test_provider_data_included_when_set(self):
        msg = Message(role="assistant", provider_data={"signature": "abc123"})
        d = msg.to_dict()
        assert "provider_data" in d
        assert d["provider_data"]["signature"] == "abc123"

    def test_empty_tool_calls_list_excluded(self):
        # Empty list should be excluded by the filter
        msg = Message(role="user", tool_calls=[])
        d = msg.to_dict()
        assert "tool_calls" not in d

    def test_tool_call_error_included_when_set(self):
        msg = Message(role="tool", tool_call_error=True)
        d = msg.to_dict()
        assert "tool_call_error" in d
        assert d["tool_call_error"] is True


# ---------------------------------------------------------------------------
# to_function_call_dict() tests
# ---------------------------------------------------------------------------


class TestToFunctionCallDict:
    def test_basic_serialization(self, tool_result_message):
        d = tool_result_message.to_function_call_dict()
        assert d["content"] == "Tool result here"
        assert d["tool_call_id"] == "call_abc"
        assert d["tool_name"] == "search"
        assert d["tool_args"] == {"query": "test"}

    def test_includes_metrics(self):
        msg = Message(role="tool", content="result")
        d = msg.to_function_call_dict()
        assert "metrics" in d
        assert isinstance(d["metrics"], Metrics)

    def test_includes_created_at(self):
        msg = Message(role="tool", content="result")
        d = msg.to_function_call_dict()
        assert "created_at" in d

    def test_includes_tool_call_error(self):
        msg = Message(role="tool", content="error", tool_call_error=True)
        d = msg.to_function_call_dict()
        assert d["tool_call_error"] is True

    def test_none_fields_included_as_none(self):
        msg = Message(role="tool", content="result")
        d = msg.to_function_call_dict()
        assert d["tool_call_id"] is None
        assert d["tool_name"] is None
        assert d["tool_args"] is None
        assert d["tool_call_error"] is None

    def test_does_not_include_role(self):
        msg = Message(role="tool", content="result")
        d = msg.to_function_call_dict()
        assert "role" not in d

    def test_does_not_include_tool_calls(self):
        msg = Message(role="assistant", tool_calls=[{"id": "abc"}])
        d = msg.to_function_call_dict()
        assert "tool_calls" not in d


# ---------------------------------------------------------------------------
# from_dict() tests
# ---------------------------------------------------------------------------


class TestFromDict:
    def test_basic_reconstruction(self):
        data = {
            "id": "test-id-123",
            "role": "user",
            "content": "Hello",
            "created_at": 1700000000,
        }
        msg = Message.from_dict(data)
        assert msg.id == "test-id-123"
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.created_at == 1700000000

    def test_reconstruction_with_citations(self):
        data = {
            "role": "assistant",
            "content": "Answer with citation",
            "citations": {
                "raw": None,
                "urls": [{"url": "https://example.com", "title": "Example"}],
                "documents": None,
            },
        }
        msg = Message.from_dict(data)
        assert msg.citations is not None
        assert isinstance(msg.citations, Citations)
        assert len(msg.citations.urls) == 1
        assert msg.citations.urls[0].url == "https://example.com"

    def test_reconstruction_with_metrics(self):
        data = {
            "role": "assistant",
            "content": "Response",
            "metrics": {
                "input_tokens": 50,
                "output_tokens": 100,
                "total_tokens": 150,
            },
        }
        msg = Message.from_dict(data)
        assert msg.metrics is not None
        assert isinstance(msg.metrics, Metrics)
        assert msg.metrics.input_tokens == 50
        assert msg.metrics.output_tokens == 100

    def test_reconstruction_with_references(self):
        data = {
            "role": "user",
            "content": "Question",
            "references": {
                "query": "my query",
                "references": [{"id": "1", "text": "ref text"}],
                "time": 0.5,
            },
        }
        msg = Message.from_dict(data)
        assert msg.references is not None
        assert isinstance(msg.references, MessageReferences)
        assert msg.references.query == "my query"
        assert msg.references.time == 0.5

    def test_reconstruction_preserves_tool_fields(self):
        data = {
            "role": "tool",
            "content": "tool result",
            "tool_call_id": "call_xyz",
            "tool_name": "calculator",
            "tool_args": {"x": 1, "y": 2},
            "tool_call_error": False,
        }
        msg = Message.from_dict(data)
        assert msg.tool_call_id == "call_xyz"
        assert msg.tool_name == "calculator"
        assert msg.tool_args == {"x": 1, "y": 2}
        assert msg.tool_call_error is False

    def test_reconstruction_without_citations(self):
        data = {"role": "user", "content": "Hello"}
        msg = Message.from_dict(data)
        assert msg.citations is None

    def test_reconstruction_without_references(self):
        data = {"role": "user", "content": "Hello"}
        msg = Message.from_dict(data)
        assert msg.references is None

    def test_reconstruction_citations_already_citations_object(self):
        citations_dict = Citations(
            urls=[UrlCitation(url="https://test.com")]
        )
        data = {
            "role": "assistant",
            "content": "resp",
            "citations": citations_dict.model_dump(),
        }
        msg = Message.from_dict(data)
        assert isinstance(msg.citations, Citations)

    def test_roundtrip_serialization(self, basic_message):
        d = basic_message.to_dict()
        reconstructed = Message.from_dict(d)
        assert reconstructed.role == basic_message.role
        assert reconstructed.content == basic_message.content
        assert reconstructed.id == basic_message.id

    def test_roundtrip_with_tool_calls(self, assistant_message):
        d = assistant_message.to_dict()
        reconstructed = Message.from_dict(d)
        assert reconstructed.role == "assistant"
        assert reconstructed.tool_calls is not None
        assert len(reconstructed.tool_calls) == 1

    def test_roundtrip_with_citations(self, citations_obj):
        msg = Message(role="assistant", content="Citation test", citations=citations_obj)
        d = msg.to_dict()
        reconstructed = Message.from_dict(d)
        assert reconstructed.citations is not None
        assert len(reconstructed.citations.urls) == 1
        assert reconstructed.citations.urls[0].url == "https://example.com"

    def test_roundtrip_with_metrics(self):
        metrics = Metrics(input_tokens=200, output_tokens=100, total_tokens=300)
        msg = Message(role="assistant", content="metricked", metrics=metrics)
        d = msg.to_dict()
        reconstructed = Message.from_dict(d)
        assert reconstructed.metrics.input_tokens == 200
        assert reconstructed.metrics.output_tokens == 100
