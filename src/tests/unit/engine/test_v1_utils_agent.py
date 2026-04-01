"""Unit tests for agent utility functions."""

import inspect
from asyncio import Future
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ii_agent.agents.utils.agent import (
    DEFAULT_ABORT_REASON,
    get_tool_abort_message,
    get_tool_error_message,
    collect_joint_images,
    collect_joint_videos,
    collect_joint_audios,
    collect_joint_files,
    store_media_util,
    validate_media_object_id,
    scrub_media_from_run_output,
    scrub_media_from_message,
    scrub_tool_results_from_run_output,
    scrub_history_messages_from_run_output,
    execute_instructions,
    aexecute_instructions,
    aexecute_system_message,
)
from ii_agent.files.media import Audio, File, Image, Video
from ii_agent.agents.models.message import Message
from ii_agent.agents.runs.agent import RunOutput, RunInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_run_output(messages=None) -> RunOutput:
    run = RunOutput(
        run_id=str(uuid4()),
        session_id="s1",
        user_id="user-001",
        model="gpt-4o",
        agent_name="test-agent",
    )
    run.messages = messages or []
    return run


def make_message(role="assistant", from_history=False) -> Message:
    msg = Message(role=role, content="content")
    msg.from_history = from_history
    msg.add_to_agent_memory = True
    return msg


def make_image(image_id=None) -> Image:
    return Image(id=image_id, url="http://example.com/image.png")


def make_video(video_id=None) -> Video:
    return Video(id=video_id, url="http://example.com/video.mp4")


def make_audio(audio_id=None) -> Audio:
    return Audio(id=audio_id, content=b"audio", transcript="")


def make_file(file_id=None) -> File:
    return File(id=file_id, name="file.txt", content=b"data")


def make_session(runs=None) -> MagicMock:
    session = MagicMock()
    session.runs = runs or []
    return session


def make_run_input(images=None, videos=None, audios=None, files=None) -> RunInput:
    ri = RunInput(
        input_content="test message",
        images=images or [],
        videos=videos or [],
        audios=audios or [],
        files=files or [],
    )
    return ri


# ---------------------------------------------------------------------------
# get_tool_abort_message tests
# ---------------------------------------------------------------------------


class TestGetToolAbortMessage:
    def test_default_abort_reason(self):
        msg = get_tool_abort_message()
        assert DEFAULT_ABORT_REASON in msg
        assert "TOOL EXECUTION ABORTED" in msg
        assert "Cancelled" in msg

    def test_custom_abort_reason(self):
        msg = get_tool_abort_message("User pressed stop")
        assert "User pressed stop" in msg

    def test_empty_reason_uses_default(self):
        msg = get_tool_abort_message("")
        assert DEFAULT_ABORT_REASON in msg

    def test_contains_note(self):
        msg = get_tool_abort_message()
        assert "Note:" in msg


# ---------------------------------------------------------------------------
# get_tool_error_message tests
# ---------------------------------------------------------------------------


class TestGetToolErrorMessage:
    def test_contains_error_text(self):
        msg = get_tool_error_message("Connection timeout")
        assert "Connection timeout" in msg
        assert "TOOL EXECUTION FAILED" in msg

    def test_contains_status_error(self):
        msg = get_tool_error_message("Bad input")
        assert "Error" in msg

    def test_contains_note(self):
        msg = get_tool_error_message("Some error")
        assert "Note:" in msg


# ---------------------------------------------------------------------------
# collect_joint_images tests
# ---------------------------------------------------------------------------


class TestCollectJointImages:
    def test_returns_none_when_no_input(self):
        result = collect_joint_images(None, None)
        assert result is None

    def test_collects_from_run_input(self):
        img = make_image()
        run_input = make_run_input(images=[img])
        result = collect_joint_images(run_input, None)
        assert result is not None
        assert img in result

    def test_collects_from_session_runs(self):
        img = make_image()
        historical_run = MagicMock()
        historical_run.images = [img]
        historical_run.input = None
        session = make_session(runs=[historical_run])

        result = collect_joint_images(None, session)
        assert result is not None
        assert img in result

    def test_collects_from_historical_run_input(self):
        img = make_image()
        historical_run = MagicMock()
        historical_run.images = None
        historical_run.input = make_run_input(images=[img])
        session = make_session(runs=[historical_run])

        result = collect_joint_images(None, session)
        assert result is not None
        assert img in result

    def test_returns_none_when_no_images_found(self):
        run_input = make_run_input(images=[])
        result = collect_joint_images(run_input, None)
        assert result is None

    def test_combines_input_and_session_images(self):
        img1 = make_image()
        img2 = make_image()
        run_input = make_run_input(images=[img1])
        historical_run = MagicMock()
        historical_run.images = [img2]
        historical_run.input = None
        session = make_session(runs=[historical_run])

        result = collect_joint_images(run_input, session)
        assert img1 in result
        assert img2 in result

    def test_handles_session_access_exception_gracefully(self):
        run_input = make_run_input(images=[make_image()])
        session = MagicMock()
        session.runs = MagicMock(side_effect=Exception("access error"))

        result = collect_joint_images(run_input, session)
        # Should still return input images despite session error
        assert result is not None


# ---------------------------------------------------------------------------
# collect_joint_videos tests
# ---------------------------------------------------------------------------


class TestCollectJointVideos:
    def test_returns_none_when_no_input(self):
        result = collect_joint_videos(None, None)
        assert result is None

    def test_collects_from_run_input(self):
        vid = make_video()
        run_input = make_run_input(videos=[vid])
        result = collect_joint_videos(run_input, None)
        assert result is not None
        assert vid in result

    def test_collects_from_session_runs(self):
        vid = make_video()
        historical_run = MagicMock()
        historical_run.videos = [vid]
        historical_run.input = None
        session = make_session(runs=[historical_run])

        result = collect_joint_videos(None, session)
        assert result is not None
        assert vid in result

    def test_returns_none_when_empty(self):
        run_input = make_run_input(videos=[])
        result = collect_joint_videos(run_input, None)
        assert result is None


# ---------------------------------------------------------------------------
# collect_joint_audios tests
# ---------------------------------------------------------------------------


class TestCollectJointAudios:
    def test_returns_none_when_no_input(self):
        result = collect_joint_audios(None, None)
        assert result is None

    def test_collects_from_run_input(self):
        aud = make_audio()
        run_input = make_run_input(audios=[aud])
        result = collect_joint_audios(run_input, None)
        assert result is not None
        assert aud in result

    def test_collects_from_session_runs(self):
        aud = make_audio()
        historical_run = MagicMock()
        historical_run.audio = [aud]
        historical_run.input = None
        session = make_session(runs=[historical_run])

        result = collect_joint_audios(None, session)
        assert result is not None
        assert aud in result

    def test_returns_none_when_empty(self):
        run_input = make_run_input(audios=[])
        result = collect_joint_audios(run_input, None)
        assert result is None


# ---------------------------------------------------------------------------
# collect_joint_files tests
# ---------------------------------------------------------------------------


class TestCollectJointFiles:
    def test_returns_none_when_no_input(self):
        result = collect_joint_files(None)
        assert result is None

    def test_collects_from_run_input(self):
        f = make_file()
        run_input = make_run_input(files=[f])
        result = collect_joint_files(run_input)
        assert result is not None
        assert f in result

    def test_returns_none_when_empty_files(self):
        run_input = make_run_input(files=[])
        result = collect_joint_files(run_input)
        assert result is None


# ---------------------------------------------------------------------------
# store_media_util tests
# ---------------------------------------------------------------------------


class TestStoreMediaUtil:
    def test_stores_images_from_model_response(self):
        run_output = make_run_output()
        model_response = MagicMock()
        img = make_image()
        model_response.images = [img]
        model_response.videos = None
        model_response.audios = None
        model_response.files = None

        store_media_util(run_output, model_response)
        assert img in run_output.images

    def test_stores_videos_from_model_response(self):
        run_output = make_run_output()
        model_response = MagicMock()
        vid = make_video()
        model_response.images = None
        model_response.videos = [vid]
        model_response.audios = None
        model_response.files = None

        store_media_util(run_output, model_response)
        assert vid in run_output.videos

    def test_stores_audios_from_model_response(self):
        run_output = make_run_output()
        model_response = MagicMock()
        aud = make_audio()
        model_response.images = None
        model_response.videos = None
        model_response.audios = [aud]
        model_response.files = None

        store_media_util(run_output, model_response)
        assert aud in run_output.audio

    def test_stores_files_from_model_response(self):
        run_output = make_run_output()
        model_response = MagicMock()
        f = make_file()
        model_response.images = None
        model_response.videos = None
        model_response.audios = None
        model_response.files = [f]

        store_media_util(run_output, model_response)
        assert f in run_output.files

    def test_handles_none_media_fields(self):
        run_output = make_run_output()
        model_response = MagicMock()
        model_response.images = None
        model_response.videos = None
        model_response.audios = None
        model_response.files = None

        store_media_util(run_output, model_response)  # Should not raise


# ---------------------------------------------------------------------------
# validate_media_object_id tests
# ---------------------------------------------------------------------------


class TestValidateMediaObjectId:
    def test_assigns_id_to_images_without_id(self):
        img = make_image(image_id=None)
        result_images, _, _, _ = validate_media_object_id(images=[img])
        assert result_images[0].id is not None

    def test_preserves_existing_image_id(self):
        img = make_image(image_id="existing-id")
        result_images, _, _, _ = validate_media_object_id(images=[img])
        assert result_images[0].id == "existing-id"

    def test_assigns_id_to_videos_without_id(self):
        vid = make_video(video_id=None)
        _, result_videos, _, _ = validate_media_object_id(videos=[vid])
        assert result_videos[0].id is not None

    def test_assigns_id_to_audios_without_id(self):
        aud = make_audio(audio_id=None)
        _, _, result_audios, _ = validate_media_object_id(audios=[aud])
        assert result_audios[0].id is not None

    def test_assigns_id_to_files_without_id(self):
        f = make_file(file_id=None)
        _, _, _, result_files = validate_media_object_id(files=[f])
        assert result_files[0].id is not None

    def test_returns_none_for_empty_inputs(self):
        images, videos, audios, files = validate_media_object_id()
        assert images is None
        assert videos is None
        assert audios is None
        assert files is None


# ---------------------------------------------------------------------------
# scrub_media_from_run_output tests
# ---------------------------------------------------------------------------


class TestScrubMediaFromRunOutput:
    def test_scrubs_run_input_media(self):
        run_output = make_run_output()
        run_input = make_run_input(images=[make_image()], videos=[make_video()])
        run_output.input = run_input

        scrub_media_from_run_output(run_output)
        assert run_output.input.images == []
        assert run_output.input.videos == []

    def test_scrubs_media_from_messages(self):
        msg = make_message()
        msg.images = [make_image()]
        msg.videos = [make_video()]
        run_output = make_run_output(messages=[msg])

        scrub_media_from_run_output(run_output)
        assert msg.images is None
        assert msg.videos is None

    def test_handles_no_input_gracefully(self):
        run_output = make_run_output()
        run_output.input = None
        scrub_media_from_run_output(run_output)  # Should not raise


# ---------------------------------------------------------------------------
# scrub_media_from_message tests
# ---------------------------------------------------------------------------


class TestScrubMediaFromMessage:
    def test_clears_all_media_fields(self):
        msg = make_message()
        msg.images = [make_image()]
        msg.videos = [make_video()]
        msg.audio = make_audio()
        msg.files = [make_file()]
        msg.audio_output = MagicMock()
        msg.image_output = MagicMock()
        msg.video_output = MagicMock()

        scrub_media_from_message(msg)

        assert msg.images is None
        assert msg.videos is None
        assert msg.audio is None
        assert msg.files is None
        assert msg.audio_output is None
        assert msg.image_output is None
        assert msg.video_output is None


# ---------------------------------------------------------------------------
# scrub_tool_results_from_run_output tests
# ---------------------------------------------------------------------------


class TestScrubToolResultsFromRunOutput:
    def test_removes_tool_messages(self):
        tool_call_id = str(uuid4())
        assistant_msg = make_message("assistant")
        assistant_msg.tool_calls = [{"id": tool_call_id}]
        tool_msg = make_message("tool")
        tool_msg.tool_call_id = tool_call_id

        run_output = make_run_output(messages=[assistant_msg, tool_msg])
        scrub_tool_results_from_run_output(run_output)

        assert not any(m.role == "tool" for m in run_output.messages)

    def test_removes_assistant_messages_that_made_tool_calls(self):
        tool_call_id = str(uuid4())
        assistant_msg = make_message("assistant")
        assistant_msg.tool_calls = [{"id": tool_call_id}]
        tool_msg = make_message("tool")
        tool_msg.tool_call_id = tool_call_id

        run_output = make_run_output(messages=[assistant_msg, tool_msg])
        scrub_tool_results_from_run_output(run_output)

        assert not any(m.role == "assistant" for m in run_output.messages)

    def test_keeps_assistant_messages_without_tool_calls(self):
        regular_assistant_msg = make_message("assistant")
        regular_assistant_msg.tool_calls = None

        tool_call_id = str(uuid4())
        tool_calling_assistant_msg = make_message("assistant")
        tool_calling_assistant_msg.tool_calls = [{"id": tool_call_id}]
        tool_msg = make_message("tool")
        tool_msg.tool_call_id = tool_call_id

        run_output = make_run_output(
            messages=[regular_assistant_msg, tool_calling_assistant_msg, tool_msg]
        )
        scrub_tool_results_from_run_output(run_output)

        assert regular_assistant_msg in run_output.messages

    def test_handles_empty_messages(self):
        run_output = make_run_output(messages=[])
        scrub_tool_results_from_run_output(run_output)  # Should not raise


# ---------------------------------------------------------------------------
# scrub_history_messages_from_run_output tests
# ---------------------------------------------------------------------------


class TestScrubHistoryMessagesFromRunOutput:
    def test_removes_history_messages(self):
        history_msg = make_message(from_history=True)
        non_history_msg = make_message(from_history=False)
        run_output = make_run_output(messages=[history_msg, non_history_msg])

        scrub_history_messages_from_run_output(run_output)
        assert history_msg not in run_output.messages
        assert non_history_msg in run_output.messages

    def test_handles_none_messages(self):
        run_output = make_run_output()
        run_output.messages = None
        scrub_history_messages_from_run_output(run_output)  # Should not raise


# ---------------------------------------------------------------------------
# execute_instructions tests
# ---------------------------------------------------------------------------


class TestExecuteInstructions:
    def test_calls_simple_function(self):
        def simple_instructions():
            return "instructions text"

        result = execute_instructions(simple_instructions)
        assert result == "instructions text"

    def test_passes_agent_param_when_expected(self):
        mock_agent = MagicMock()

        def instructions_with_agent(agent):
            return f"agent name: {agent.name}"

        mock_agent.name = "TestAgent"
        result = execute_instructions(instructions_with_agent, agent=mock_agent)
        assert "TestAgent" in result

    def test_passes_session_state_when_expected(self):
        def instructions_with_state(session_state):
            return f"state: {session_state.get('key')}"

        result = execute_instructions(instructions_with_state, session_state={"key": "value"})
        assert "value" in result

    def test_passes_run_context_when_expected(self):
        mock_context = MagicMock()
        mock_context.some_field = "context_value"

        def instructions_with_context(run_context):
            return f"context: {run_context.some_field}"

        result = execute_instructions(instructions_with_context, run_context=mock_context)
        assert "context_value" in result

    def test_raises_for_async_function(self):
        async def async_instructions():
            return "async result"

        with pytest.raises(Exception, match="async"):
            execute_instructions(async_instructions)

    def test_session_state_defaults_to_empty_dict_when_none(self):
        def instructions_with_state(session_state):
            return str(session_state)

        result = execute_instructions(instructions_with_state, session_state=None)
        assert result == "{}"


# ---------------------------------------------------------------------------
# aexecute_instructions tests
# ---------------------------------------------------------------------------


class TestAExecuteInstructions:
    @pytest.mark.asyncio
    async def test_calls_sync_function(self):
        def sync_instructions():
            return "sync result"

        result = await aexecute_instructions(sync_instructions)
        assert result == "sync result"

    @pytest.mark.asyncio
    async def test_calls_async_function(self):
        async def async_instructions():
            return "async result"

        result = await aexecute_instructions(async_instructions)
        assert result == "async result"

    @pytest.mark.asyncio
    async def test_passes_agent_param(self):
        mock_agent = MagicMock()
        mock_agent.name = "MyAgent"

        async def async_instructions_with_agent(agent):
            return f"hello {agent.name}"

        result = await aexecute_instructions(async_instructions_with_agent, agent=mock_agent)
        assert "MyAgent" in result

    @pytest.mark.asyncio
    async def test_passes_session_state_param(self):
        async def instructions_with_state(session_state):
            return str(session_state.get("data"))

        result = await aexecute_instructions(
            instructions_with_state, session_state={"data": "test_value"}
        )
        assert "test_value" in result

    @pytest.mark.asyncio
    async def test_session_state_defaults_to_empty_dict_when_none(self):
        async def instructions_with_state(session_state):
            return str(session_state)

        result = await aexecute_instructions(instructions_with_state, session_state=None)
        assert result == "{}"


# ---------------------------------------------------------------------------
# aexecute_system_message tests
# ---------------------------------------------------------------------------


class TestAExecuteSystemMessage:
    @pytest.mark.asyncio
    async def test_calls_sync_system_message_function(self):
        def sync_system_message():
            return "System prompt"

        result = await aexecute_system_message(sync_system_message)
        assert result == "System prompt"

    @pytest.mark.asyncio
    async def test_calls_async_system_message_function(self):
        async def async_system_message():
            return "Async system prompt"

        result = await aexecute_system_message(async_system_message)
        assert result == "Async system prompt"

    @pytest.mark.asyncio
    async def test_passes_agent_param(self):
        mock_agent = MagicMock()
        mock_agent.name = "TestAgent"

        async def system_message_with_agent(agent):
            return f"You are {agent.name}"

        result = await aexecute_system_message(system_message_with_agent, agent=mock_agent)
        assert "TestAgent" in result

    @pytest.mark.asyncio
    async def test_function_without_agent_param_not_passed_agent(self):
        async def system_message_without_agent():
            return "No agent needed"

        mock_agent = MagicMock()
        result = await aexecute_system_message(system_message_without_agent, agent=mock_agent)
        assert result == "No agent needed"
