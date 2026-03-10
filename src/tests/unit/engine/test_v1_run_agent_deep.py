"""Deep unit tests for ii_agent/engine/runtime/run/agent.py.

Focuses on previously uncovered branches:
- RunInput: to_dict with various input types (Message, list of Messages, list of dicts with media)
- RunInput.from_dict: image/video/audio/file reconstruction
- RunOutput: to_dict / to_json / from_dict edge cases, member_responses, tool serialization
- RunOutput.add_member_run: audio/video/file aggregation
- RunOutput.get_content_as_string with Pydantic models
- run_output_event_from_dict for all event types
- Event dataclass edge cases: RunPausedEvent.active_requirements, CustomEvent
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from ii_agent.engine.runtime.run.agent import (
    RunInput,
    RunOutput,
    RunEvent,
    RunCompletedEvent,
    RunPausedEvent,
    RunCancelledEvent,
    RunErrorEvent,
    RunContentDeltaEvent,
    RunContentEvent,
    ReasoningCompletedEvent,
    ReasoningDeltaEvent,
    ToolCallStartedEvent,
    ToolCallCompletedEvent,
    SandboxInitializedEvent,
    SessionSummaryCompletedEvent,
    RunContinuedEvent,
    CustomEvent,
    run_output_event_from_dict,
    RUN_EVENT_TYPE_REGISTRY,
)
from ii_agent.engine.runtime.run.base import RunStatus
from ii_agent.engine.runtime.models.message import Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_run_output(**kwargs) -> RunOutput:
    defaults = dict(
        run_id=str(uuid4()),
        session_id="sess-deep",
        user_id="user-deep",
        model="gpt-4o",
        agent_name="DeepAgent",
    )
    defaults.update(kwargs)
    return RunOutput(**defaults)


def make_message(role="assistant", content="test", from_history=False) -> Message:
    msg = Message(role=role, content=content)
    msg.from_history = from_history
    msg.add_to_agent_memory = True
    return msg


# ---------------------------------------------------------------------------
# RunInput.to_dict deep tests
# ---------------------------------------------------------------------------

class TestRunInputToDictDeep:
    """Test to_dict with various input content types."""

    def test_to_dict_with_message_input(self):
        msg = Message(role="user", content="hello")
        ri = RunInput(input_content=msg)
        d = ri.to_dict()
        assert "input_content" in d

    def test_to_dict_with_list_of_messages(self):
        msg1 = Message(role="user", content="first")
        msg2 = Message(role="assistant", content="second")
        ri = RunInput(input_content=[msg1, msg2])
        d = ri.to_dict()
        assert "input_content" in d
        assert isinstance(d["input_content"], list)

    def test_to_dict_with_list_of_dicts_containing_images(self):
        from ii_agent.engine.runtime.media import Image
        img = Image(id="img-1", url="http://example.com/img.png")
        ri = RunInput(input_content=[{"images": [img], "text": "hello"}])
        d = ri.to_dict()
        assert "input_content" in d

    def test_to_dict_with_list_of_dicts_containing_videos(self):
        from ii_agent.engine.runtime.media import Video
        vid = Video(id="vid-1", url="http://example.com/vid.mp4")
        ri = RunInput(input_content=[{"videos": [vid], "text": "hello"}])
        d = ri.to_dict()
        assert "input_content" in d

    def test_to_dict_with_list_of_dicts_containing_audios(self):
        from ii_agent.engine.runtime.media import Audio
        aud = Audio(id="aud-1", content=b"audio", transcript="")
        ri = RunInput(input_content=[{"audios": [aud], "text": "hello"}])
        d = ri.to_dict()
        assert "input_content" in d

    def test_to_dict_with_list_of_dicts_containing_files(self):
        from ii_agent.engine.runtime.media import File
        f = File(id="file-1", name="test.txt", content=b"data")
        ri = RunInput(input_content=[{"files": [f], "text": "hello"}])
        d = ri.to_dict()
        assert "input_content" in d

    def test_to_dict_with_pydantic_model_input(self):
        from pydantic import BaseModel

        class MyInput(BaseModel):
            query: str

        model_instance = MyInput(query="test")
        ri = RunInput(input_content=model_instance)
        d = ri.to_dict()
        assert "input_content" in d

    def test_to_dict_includes_images_when_present(self):
        from ii_agent.engine.runtime.media import Image
        img = Image(id="img-1", url="http://example.com/img.png")
        ri = RunInput(input_content="test", images=[img])
        d = ri.to_dict()
        assert "images" in d
        assert len(d["images"]) == 1

    def test_to_dict_includes_videos_when_present(self):
        from ii_agent.engine.runtime.media import Video
        vid = Video(id="vid-1", url="http://example.com/vid.mp4")
        ri = RunInput(input_content="test", videos=[vid])
        d = ri.to_dict()
        assert "videos" in d

    def test_to_dict_includes_audios_when_present(self):
        from ii_agent.engine.runtime.media import Audio
        aud = Audio(id="aud-1", content=b"audio", transcript="")
        ri = RunInput(input_content="test", audios=[aud])
        d = ri.to_dict()
        assert "audios" in d

    def test_to_dict_includes_files_when_present(self):
        from ii_agent.engine.runtime.media import File
        f = File(id="file-1", name="test.txt", content=b"data")
        ri = RunInput(input_content="test", files=[f])
        d = ri.to_dict()
        assert "files" in d

    def test_to_dict_with_integer_input_falls_through_to_str(self):
        ri = RunInput(input_content=42)
        d = ri.to_dict()
        assert "input_content" in d
        assert d["input_content"] == 42

    def test_input_content_string_for_message(self):
        msg = Message(role="user", content="hello")
        ri = RunInput(input_content=msg)
        result = ri.input_content_string()
        assert isinstance(result, str)

    def test_input_content_string_for_list_of_messages(self):
        msg = Message(role="user", content="hello")
        ri = RunInput(input_content=[msg])
        result = ri.input_content_string()
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# RunInput.from_dict with media reconstruction
# ---------------------------------------------------------------------------

class TestRunInputFromDictDeep:
    def test_from_dict_reconstructs_images(self):
        data = {
            "input_content": "test",
            "images": [{"id": "img-1", "url": "http://example.com/img.png"}],
        }
        ri = RunInput.from_dict(data)
        assert ri.images is not None
        assert len(ri.images) == 1

    def test_from_dict_reconstructs_videos(self):
        data = {
            "input_content": "test",
            "videos": [{"id": "vid-1", "url": "http://example.com/vid.mp4"}],
        }
        ri = RunInput.from_dict(data)
        assert ri.videos is not None

    def test_from_dict_with_empty_images(self):
        data = {"input_content": "test", "images": []}
        ri = RunInput.from_dict(data)
        assert ri.images is None or ri.images == []


# ---------------------------------------------------------------------------
# RunOutput.to_dict deep tests
# ---------------------------------------------------------------------------

class TestRunOutputToDictDeep:
    def test_to_dict_serializes_tools(self):
        output = make_run_output()
        tool = MagicMock()
        tool.to_dict.return_value = {"name": "test_tool"}
        # Simulate ToolExecution-like object
        from ii_agent.engine.runtime.models.response import ToolExecution
        te = ToolExecution(tool_name="my_tool")
        output.tools = [te]
        d = output.to_dict()
        assert "tools" in d

    def test_to_dict_serializes_images(self):
        from ii_agent.engine.runtime.media import Image
        output = make_run_output()
        output.images = [Image(id="img-1", url="http://example.com/img.png")]
        d = output.to_dict()
        assert "images" in d

    def test_to_dict_serializes_videos(self):
        from ii_agent.engine.runtime.media import Video
        output = make_run_output()
        output.videos = [Video(id="vid-1", url="http://example.com/vid.mp4")]
        d = output.to_dict()
        assert "videos" in d

    def test_to_dict_serializes_audio_list(self):
        from ii_agent.engine.runtime.media import Audio
        output = make_run_output()
        output.audio = [Audio(id="aud-1", content=b"data", transcript="")]
        d = output.to_dict()
        assert "audio" in d

    def test_to_dict_serializes_files(self):
        from ii_agent.engine.runtime.media import File
        output = make_run_output()
        output.files = [File(id="file-1", name="test.txt", content=b"data")]
        d = output.to_dict()
        assert "files" in d

    def test_to_dict_serializes_response_audio(self):
        from ii_agent.engine.runtime.media import Audio
        output = make_run_output()
        output.response_audio = Audio(id="ra-1", content=b"audio", transcript="hello")
        d = output.to_dict()
        assert "response_audio" in d

    def test_to_dict_serializes_citations(self):
        from ii_agent.engine.runtime.models.message import Citations
        output = make_run_output()
        output.citations = MagicMock()
        output.citations.model_dump.return_value = {"items": []}
        d = output.to_dict()
        # Citations should be in dict if present
        assert "citations" in d

    def test_to_dict_content_is_pydantic_model(self):
        from pydantic import BaseModel

        class OutputSchema(BaseModel):
            result: str

        output = make_run_output()
        output.content = OutputSchema(result="hello")
        d = output.to_dict()
        assert "content" in d
        assert d["content"]["result"] == "hello"

    def test_to_dict_includes_status_as_string(self):
        output = make_run_output(status=RunStatus.COMPLETED)
        d = output.to_dict()
        assert d["status"] == RunStatus.COMPLETED.value

    def test_to_dict_includes_member_responses(self):
        parent = make_run_output()
        child = make_run_output(run_id="child-run")
        parent.member_responses = [child]
        d = parent.to_dict()
        assert "member_responses" in d
        assert len(d["member_responses"]) == 1

    def test_to_dict_includes_input(self):
        output = make_run_output()
        output.input = RunInput(input_content="user query")
        d = output.to_dict()
        assert "input" in d

    def test_to_dict_includes_references(self):
        from ii_agent.engine.runtime.run.base import MessageReferences
        output = make_run_output()
        ref = MagicMock(spec=MessageReferences)
        ref.model_dump.return_value = {"url": "http://example.com"}
        output.references = [ref]
        d = output.to_dict()
        assert "references" in d

    def test_to_dict_omits_none_messages(self):
        output = make_run_output()
        output.messages = None
        d = output.to_dict()
        assert "messages" not in d

    def test_to_dict_serializes_messages_list(self):
        output = make_run_output()
        msg = make_message()
        output.messages = [msg]
        d = output.to_dict()
        assert "messages" in d
        assert isinstance(d["messages"], list)

    def test_to_json_handles_serialization_error_by_raising(self):
        output = make_run_output()
        with patch.object(output, "to_dict", side_effect=TypeError("not serializable")):
            with pytest.raises(TypeError):
                output.to_json()


# ---------------------------------------------------------------------------
# RunOutput.from_dict deep tests
# ---------------------------------------------------------------------------

class TestRunOutputFromDictDeep:
    def test_from_dict_handles_status_string(self):
        output = make_run_output(status=RunStatus.COMPLETED)
        d = output.to_dict()
        recovered = RunOutput.from_dict(d)
        assert recovered.status == RunStatus.COMPLETED

    def test_from_dict_handles_unknown_status_string(self):
        output = make_run_output()
        d = output.to_dict()
        d["status"] = "SomeUnknownStatus"
        recovered = RunOutput.from_dict(d)
        assert recovered.status == RunStatus.COMPLETED

    def test_from_dict_handles_aborted_status(self):
        output = make_run_output(status=RunStatus.ABORTED)
        d = output.to_dict()
        recovered = RunOutput.from_dict(d)
        assert recovered.status == RunStatus.ABORTED

    def test_from_dict_handles_member_responses(self):
        parent = make_run_output()
        child = make_run_output(run_id="child-run")
        parent.member_responses = [child]
        d = parent.to_dict()
        recovered = RunOutput.from_dict(d)
        assert recovered.member_responses is not None
        assert len(recovered.member_responses) == 1

    def test_from_dict_handles_additional_input(self):
        output = make_run_output()
        msg = make_message("user", "additional context")
        output.additional_input = [msg]
        d = output.to_dict()
        # additional_input is not in to_dict standard output but is handled in from_dict
        d_manual = output.to_dict()
        # Re-add additional_input for test
        d_manual["additional_input"] = [msg.to_dict()]
        recovered = RunOutput.from_dict(d_manual)
        assert recovered.additional_input is not None

    def test_from_dict_handles_reasoning_messages(self):
        output = make_run_output()
        msg = make_message("assistant", "I reasoned...")
        output.reasoning_messages = [msg]
        d = output.to_dict()
        d["reasoning_messages"] = [msg.to_dict()]
        recovered = RunOutput.from_dict(d)
        assert recovered.reasoning_messages is not None

    def test_from_dict_handles_metrics(self):
        from ii_agent.engine.runtime.models.metrics import Metrics
        output = make_run_output()
        m = Metrics()
        m.input_tokens = 100
        output.metrics = m
        d = output.to_dict()
        recovered = RunOutput.from_dict(d)
        assert recovered.metrics is not None

    def test_from_dict_ignores_unknown_fields(self):
        output = make_run_output()
        d = output.to_dict()
        d["unknown_field_xyz"] = "should be ignored"
        recovered = RunOutput.from_dict(d)
        assert recovered.run_id == output.run_id

    def test_from_dict_handles_events_key_by_ignoring_it(self):
        output = make_run_output()
        d = output.to_dict()
        d["events"] = [{"type": "some_event"}]
        recovered = RunOutput.from_dict(d)
        assert recovered.run_id == output.run_id


# ---------------------------------------------------------------------------
# RunOutput.add_member_run deep tests
# ---------------------------------------------------------------------------

class TestRunOutputAddMemberRunDeep:
    def test_add_member_run_aggregates_videos(self):
        from ii_agent.engine.runtime.media import Video
        parent = make_run_output()
        child = make_run_output(run_id="child-run")
        child.videos = [Video(id="vid-1", url="http://example.com/vid.mp4")]
        parent.add_member_run(child)
        assert parent.videos is not None
        assert len(parent.videos) == 1

    def test_add_member_run_aggregates_audio(self):
        from ii_agent.engine.runtime.media import Audio
        parent = make_run_output()
        child = make_run_output(run_id="child-run")
        child.audio = [Audio(id="aud-1", content=b"data", transcript="")]
        parent.add_member_run(child)
        assert parent.audio is not None

    def test_add_member_run_aggregates_files(self):
        from ii_agent.engine.runtime.media import File
        parent = make_run_output()
        child = make_run_output(run_id="child-run")
        child.files = [File(id="file-1", name="test.txt", content=b"data")]
        parent.add_member_run(child)
        assert parent.files is not None

    def test_add_member_run_accumulates_multiple_children(self):
        from ii_agent.engine.runtime.media import Image
        parent = make_run_output()
        child1 = make_run_output(run_id="child-1")
        child1.images = [Image(id="img-1", url="http://example.com/1.png")]
        child2 = make_run_output(run_id="child-2")
        child2.images = [Image(id="img-2", url="http://example.com/2.png")]
        parent.add_member_run(child1)
        parent.add_member_run(child2)
        assert len(parent.member_responses) == 2
        assert len(parent.images) == 2

    def test_add_member_run_no_media_still_appends(self):
        parent = make_run_output()
        child = make_run_output(run_id="child-run")
        # No media
        parent.add_member_run(child)
        assert len(parent.member_responses) == 1
        assert parent.images is None
        assert parent.videos is None


# ---------------------------------------------------------------------------
# RunOutput.get_content_as_string deep tests
# ---------------------------------------------------------------------------

class TestGetContentAsStringDeep:
    def test_pydantic_model_content(self):
        from pydantic import BaseModel

        class OutputModel(BaseModel):
            result: str
            count: int

        output = make_run_output()
        output.content = OutputModel(result="hello", count=5)
        s = output.get_content_as_string()
        assert "hello" in s
        assert "5" in s

    def test_dict_content(self):
        output = make_run_output()
        output.content = {"key": "value", "num": 42}
        s = output.get_content_as_string()
        data = json.loads(s)
        assert data["key"] == "value"

    def test_list_content(self):
        output = make_run_output()
        output.content = [1, 2, 3]
        s = output.get_content_as_string()
        assert "[1, 2, 3]" in s or "1" in s


# ---------------------------------------------------------------------------
# RunPausedEvent edge cases
# ---------------------------------------------------------------------------

class TestRunPausedEventDeep:
    def test_active_requirements_returns_unresolved(self):
        req1 = MagicMock()
        req1.is_resolved.return_value = False
        req2 = MagicMock()
        req2.is_resolved.return_value = True

        ev = RunPausedEvent(agent_id="a1", agent_name="A", requirements=[req1, req2])
        active = ev.active_requirements
        assert req1 in active
        assert req2 not in active

    def test_active_requirements_all_resolved(self):
        req1 = MagicMock()
        req1.is_resolved.return_value = True
        ev = RunPausedEvent(agent_id="a1", agent_name="A", requirements=[req1])
        assert ev.active_requirements == []

    def test_to_dict_includes_requirements(self):
        req = MagicMock()
        req.to_dict.return_value = {"id": "req-1", "needs_confirmation": True}
        ev = RunPausedEvent(agent_id="a1", agent_name="A", requirements=[req])
        d = ev.to_dict()
        assert "requirements" in d


# ---------------------------------------------------------------------------
# CustomEvent
# ---------------------------------------------------------------------------

class TestCustomEventDeep:
    def test_custom_event_stores_kwargs(self):
        ev = CustomEvent(event="CustomEvent", agent_id="a1", agent_name="A", custom_field="custom_value")
        assert ev.custom_field == "custom_value"

    def test_custom_event_default_event_string(self):
        ev = CustomEvent(event="CustomEvent", agent_id="a1", agent_name="A")
        assert ev.event == "CustomEvent"


# ---------------------------------------------------------------------------
# run_output_event_from_dict for all registered event types
# ---------------------------------------------------------------------------

class TestRunOutputEventFromDictAllTypes:
    def _base_dict(self, event_value: str) -> dict:
        return {
            "event": event_value,
            "agent_id": "a1",
            "agent_name": "TestAgent",
            "run_id": str(uuid4()),
        }

    @pytest.mark.parametrize("event_value,expected_class", [
        ("RunStarted", "RunStartedEvent"),
        ("RunContent", "RunContentEvent"),
        ("RunContentCompleted", "RunContentCompletedEvent"),
        ("RunContentDelta", "RunContentDeltaEvent"),
        ("RunCompleted", "RunCompletedEvent"),
        ("RunError", "RunErrorEvent"),
        ("RunCancelled", "RunCancelledEvent"),
        ("RunPaused", "RunPausedEvent"),
        ("RunContinued", "RunContinuedEvent"),
        ("PreHookStarted", "PreHookStartedEvent"),
        ("PreHookCompleted", "PreHookCompletedEvent"),
        ("PostHookStarted", "PostHookStartedEvent"),
        ("PostHookCompleted", "PostHookCompletedEvent"),
        ("ReasoningStarted", "ReasoningStartedEvent"),
        ("ReasoningDelta", "ReasoningDeltaEvent"),
        ("ReasoningCompleted", "ReasoningCompletedEvent"),
        ("MemoryUpdateStarted", "MemoryUpdateStartedEvent"),
        ("MemoryUpdateCompleted", "MemoryUpdateCompletedEvent"),
        ("SessionSummaryStarted", "SessionSummaryStartedEvent"),
        ("SessionSummaryCompleted", "SessionSummaryCompletedEvent"),
        ("ToolCallStarted", "ToolCallStartedEvent"),
        ("ToolCallCompleted", "ToolCallCompletedEvent"),
        ("SandboxInitialized", "SandboxInitializedEvent"),
    ])
    def test_event_type_from_dict(self, event_value, expected_class):
        data = self._base_dict(event_value)
        ev = run_output_event_from_dict(data)
        assert type(ev).__name__ == expected_class

    def test_unknown_event_type_raises(self):
        with pytest.raises(ValueError, match="Unknown event type"):
            run_output_event_from_dict({"event": "NonExistent"})


# ---------------------------------------------------------------------------
# SandboxInitializedEvent.to_dict
# ---------------------------------------------------------------------------

class TestSandboxInitializedEventDeep:
    def test_to_dict_with_sandbox_info(self):
        from ii_agent.engine.sandboxes.schemas import SandboxInfo
        sandbox_info = MagicMock(spec=SandboxInfo)
        sandbox_info.model_dump.return_value = {"status": "running", "vscode_url": "http://vscode.example.com"}

        ev = SandboxInitializedEvent(agent_id="a1", agent_name="A", sandbox_info=sandbox_info)
        d = ev.to_dict()
        assert "sandbox_info" in d

    def test_to_dict_without_sandbox_info(self):
        ev = SandboxInitializedEvent(agent_id="a1", agent_name="A", sandbox_info=None)
        d = ev.to_dict()
        assert "sandbox_info" not in d


# ---------------------------------------------------------------------------
# RunOutput.to_json compact mode
# ---------------------------------------------------------------------------

class TestRunOutputToJsonDeep:
    def test_to_json_compact_mode(self):
        output = make_run_output(content="hello world")
        json_str = output.to_json(indent=None)
        # Should still be valid JSON
        parsed = json.loads(json_str)
        assert parsed["run_id"] == output.run_id

    def test_to_json_with_indent(self):
        output = make_run_output(content="hello world")
        json_str = output.to_json(indent=2)
        parsed = json.loads(json_str)
        assert parsed["agent_name"] == "DeepAgent"


# ---------------------------------------------------------------------------
# BaseAgentRunEvent properties with tools
# ---------------------------------------------------------------------------

class TestBaseAgentRunEventPropertiesDeep:
    def test_tools_requiring_confirmation_filters_correctly(self):
        tool1 = MagicMock()
        tool1.requires_confirmation = True
        tool2 = MagicMock()
        tool2.requires_confirmation = False

        ev = ToolCallStartedEvent(agent_id="a1", agent_name="A", tools=[tool1, tool2])
        confirming = ev.tools_requiring_confirmation
        assert tool1 in confirming
        assert tool2 not in confirming

    def test_tools_requiring_user_input_filters_correctly(self):
        tool1 = MagicMock()
        tool1.requires_user_input = True
        tool2 = MagicMock()
        tool2.requires_user_input = False

        ev = ToolCallStartedEvent(agent_id="a1", agent_name="A", tools=[tool1, tool2])
        user_input_tools = ev.tools_requiring_user_input
        assert tool1 in user_input_tools
        assert tool2 not in user_input_tools

    def test_tools_awaiting_external_execution_filters(self):
        tool1 = MagicMock()
        tool1.external_execution_required = True
        tool2 = MagicMock()
        tool2.external_execution_required = False

        ev = ToolCallStartedEvent(agent_id="a1", agent_name="A", tools=[tool1, tool2])
        external = ev.tools_awaiting_external_execution
        assert tool1 in external
        assert tool2 not in external


# ---------------------------------------------------------------------------
# RunEvent enum completeness
# ---------------------------------------------------------------------------

class TestRunEventEnumCompleteness:
    def test_all_event_enum_values_are_registered(self):
        """Every non-custom RunEvent value should map to a class in the registry."""
        # CustomEvent is registered but test other real events
        for ev in RunEvent:
            if ev == RunEvent.custom_event:
                continue
            assert ev.value in RUN_EVENT_TYPE_REGISTRY, f"{ev.value} not in registry"

    def test_run_event_pre_hook_started_value(self):
        assert RunEvent.pre_hook_started.value == "PreHookStarted"

    def test_run_event_post_hook_started_value(self):
        assert RunEvent.post_hook_started.value == "PostHookStarted"

    def test_run_event_memory_update_started_value(self):
        assert RunEvent.memory_update_started.value == "MemoryUpdateStarted"

    def test_run_event_run_paused_value(self):
        assert RunEvent.run_paused.value == "RunPaused"

    def test_run_event_run_continued_value(self):
        assert RunEvent.run_continued.value == "RunContinued"
