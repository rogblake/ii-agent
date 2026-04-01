"""Unit tests for agent.py, message_builder.py, and delegation_manager.py - r4.

Covers:
- IIAgent initialization, properties, and public API
- IIAgent._initialize_session helpers
- MessageBuilder.get_user_message / get_system_message / get_run_messages
- MessageBuilder.get_continue_run_messages
- DelegationManager.find_sub_agent_by_id / get_sub_agents_description
- DelegationManager.initialize_sub_agent
- DelegationManager.get_delegate_task_function
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model(system_role="system", user_role="user", assistant_role="assistant"):
    model = MagicMock()
    model.id = "test-model"
    model.provider = "test-provider"
    model.system_message_role = system_role
    model.user_message_role = user_role
    model.assistant_message_role = assistant_role
    model.to_dict = MagicMock(return_value={"id": "test-model"})
    return model


def _make_agent(model=None, **kwargs):
    """Create an IIAgent with all external calls mocked."""
    from ii_agent.agents.agent import IIAgent

    if model is None:
        model = _make_model()

    with (
        patch(
            "ii_agent.agents.agent.ServiceContainer.create", return_value=MagicMock()
        ),
        patch(
            "ii_agent.agents.sandbox_provider.SandboxProvider.__init__",
            return_value=None,
        ),
    ):
        agent = IIAgent.__new__(IIAgent)
        # Set required fields manually to avoid ServiceContainer side effects
        agent.user_id = kwargs.get("user_id", "user-test")
        agent.session_id = kwargs.get("session_id", "session-test")
        agent.model = model
        agent.name = kwargs.get("name", "TestAgent")
        agent.id = kwargs.get("id", None)
        agent.session_store = kwargs.get("session_store", None)
        agent.session_state = kwargs.get("session_state", None)
        agent.session_summary_manager = kwargs.get("session_summary_manager", None)
        agent.tools = list(kwargs.get("tools", []))
        agent.tool_call_limit = None
        agent.tool_choice = None
        agent.tool_hooks = None
        agent.pre_hooks = None
        agent.post_hooks = None
        agent.system_message = kwargs.get("system_message", "You are helpful.")
        agent.description = None
        agent.instructions = None
        agent.additional_context = None
        agent.retries = 0
        agent.delay_between_retries = 1
        agent.exponential_backoff = False
        agent.stream = None
        agent.stream_events = None
        agent.store_events = False
        agent.events_to_skip = None
        agent.metadata = None
        agent.sub_agents = []
        agent.delegate_to_all_members = False
        agent.stream_member_events = True
        agent.store_member_responses = False
        agent.role = None

        # Attach mock collaborators
        agent._message_builder = MagicMock()
        agent._tool_manager = MagicMock()
        agent._response_handler = MagicMock()
        agent._hook_executor = MagicMock()
        agent._sandbox_provider = MagicMock()
        agent._hitl_handler = MagicMock()
        agent._subagent_manager = MagicMock()
        agent._internal_lock = asyncio.Lock()

    return agent


# ---------------------------------------------------------------------------
# IIAgent basic public API
# ---------------------------------------------------------------------------


class TestIIAgentPublicAPI:
    """Test IIAgent public API without running the model."""

    def test_set_id_uses_name_when_id_is_none(self):
        agent = _make_agent(name="MyAgent")
        agent.id = None
        with patch(
            "ii_agent.agents.agent.generate_id_from_name", return_value="myagent-id"
        ):
            agent.set_id()
        assert agent.id == "myagent-id"

    def test_set_id_no_op_when_id_already_set(self):
        agent = _make_agent()
        agent.id = "existing-id"
        agent.set_id()
        assert agent.id == "existing-id"

    def test_should_persist_true_when_session_store_is_set(self):
        agent = _make_agent()
        agent.session_store = MagicMock()
        assert agent.should_persist is True

    def test_should_persist_false_when_session_store_is_none(self):
        agent = _make_agent()
        agent.session_store = None
        assert agent.should_persist is False

    def test_add_tool_appends(self):
        from ii_agent.agents.tools.function import Function

        agent = _make_agent()
        agent.tools = []
        fn = Function(name="test_fn", description="Test")
        agent.add_tool(fn)
        assert fn in agent.tools

    def test_add_tool_initializes_empty_list(self):
        from ii_agent.agents.tools.function import Function

        agent = _make_agent()
        agent.tools = None
        fn = Function(name="test_fn", description="Test")
        agent.add_tool(fn)
        assert fn in agent.tools

    def test_set_tools_replaces_existing(self):
        from ii_agent.agents.tools.function import Function

        agent = _make_agent()
        f1 = Function(name="f1", description="desc1")
        f2 = Function(name="f2", description="desc2")
        agent.tools = [f1]
        agent.set_tools([f2])
        assert agent.tools == [f2]

    def test_set_tools_with_empty_sets_empty_list(self):
        agent = _make_agent()
        agent.tools = [MagicMock()]
        agent.set_tools([])
        assert agent.tools == []

    def test_add_sub_agent_appends(self):
        agent = _make_agent()
        sub = MagicMock()
        sub.id = "sub-1"
        agent.sub_agents = []
        agent.add_sub_agent(sub)
        assert sub in agent.sub_agents
        agent._subagent_manager.initialize_sub_agent.assert_called_once_with(sub)

    def test_sandbox_property_delegates(self):
        agent = _make_agent()
        agent._sandbox_provider.sandbox = "sandbox-obj"
        assert agent.sandbox == "sandbox-obj"

    def test_sandbox_setter_delegates(self):
        agent = _make_agent()
        agent.sandbox = "new-sandbox"
        assert agent._sandbox_provider.sandbox == "new-sandbox"

    def test_as_tool_returns_base_agent_tool(self):
        from ii_agent.agents.tools.base import BaseAgentTool

        agent = _make_agent()
        with patch("ii_agent.agents.agent.AgentAsTool") as mock_cls:
            mock_instance = MagicMock(spec=BaseAgentTool)
            mock_cls.return_value = mock_instance
            tool = agent.as_tool(name="my_agent")
        assert tool is mock_instance

    @pytest.mark.asyncio
    async def test_cancel_run_delegates_to_global(self):
        mock_cancel = AsyncMock(return_value=True)
        with patch("ii_agent.agents.agent.cancel_run_global", mock_cancel):
            from ii_agent.agents.agent import IIAgent

            result = await IIAgent.cancel_run("run-123")
        assert result is True
        mock_cancel.assert_called_once_with("run-123")

    @pytest.mark.asyncio
    async def test_acontinue_run_raises_when_no_run_id_and_no_run_response(self):
        agent = _make_agent()
        with pytest.raises(ValueError, match="Either run_id or run_response must be provided"):
            await agent.acontinue_run(run_id=None, run_response=None)

    @pytest.mark.asyncio
    async def test_acontinue_run_raises_when_both_run_id_and_run_response(self):
        from ii_agent.agents.runs.agent import RunOutput

        agent = _make_agent()
        rr = RunOutput(run_id=str(uuid4()), session_id="s", user_id="u", model="m", agent_name="A")
        with pytest.raises(ValueError, match="Only one"):
            await agent.acontinue_run(run_id="some-run-id", run_response=rr)


# ---------------------------------------------------------------------------
# IIAgent._initialize_session
# ---------------------------------------------------------------------------


class TestInitializeSession:
    """Test the _initialize_session helper."""

    def test_uses_agent_session_id_when_none(self):
        agent = _make_agent(session_id="default-session", user_id="default-user")
        sid, uid = agent._initialize_session(session_id=None, user_id=None)
        assert sid == "default-session"
        assert uid == "default-user"

    def test_override_with_provided_values(self):
        agent = _make_agent(session_id="default-session", user_id="default-user")
        sid, uid = agent._initialize_session(session_id="override-session", user_id="override-user")
        assert sid == "override-session"
        assert uid == "override-user"

    def test_partial_override(self):
        agent = _make_agent(session_id="default-session", user_id="default-user")
        sid, uid = agent._initialize_session(session_id="new-session", user_id=None)
        assert sid == "new-session"
        assert uid == "default-user"


# ---------------------------------------------------------------------------
# IIAgent._initialize_session_state
# ---------------------------------------------------------------------------


class TestInitializeSessionState:
    """Test the _initialize_session_state helper."""

    def test_returns_dict_with_run_context(self):
        agent = _make_agent()
        agent.session_state = {"key1": "val1"}
        result = agent._initialize_session_state(
            session_state={"key2": "val2"},
            user_id="user-1",
            session_id="sess-1",
            run_id="run-1",
        )
        assert isinstance(result, dict)
        # At minimum the provided key should be in there (or the run context keys)
        assert len(result) > 0

    def test_empty_session_state_returns_minimal_state(self):
        agent = _make_agent()
        agent.session_state = None
        result = agent._initialize_session_state(
            session_state={},
            user_id="u",
            session_id="s",
            run_id="r",
        )
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# IIAgent.__post_init__  (via actual construction)
# ---------------------------------------------------------------------------


class TestIIAgentPostInit:
    """Test that __post_init__ sets up collaborators correctly."""

    def test_tools_becomes_empty_list_when_none(self):
        from ii_agent.agents.agent import IIAgent

        mock_model = _make_model()

        with (
            patch(
                "ii_agent.agents.agent.ServiceContainer.create",
                return_value=MagicMock(),
            ),
            patch(
                "ii_agent.agents.sandbox_provider.SandboxProvider.__init__",
                return_value=None,
            ),
            patch("ii_agent.agents.agent.NoOpSessionStore"),
        ):
            agent = object.__new__(IIAgent)
            agent.user_id = "u"
            agent.session_id = "s"
            agent.model = mock_model
            agent.name = "TestAgent"
            agent.id = None
            agent.session_store = None
            agent.session_state = None
            agent.session_summary_manager = None
            agent.tools = None
            agent.tool_call_limit = None
            agent.tool_choice = None
            agent.tool_hooks = None
            agent.pre_hooks = None
            agent.post_hooks = None
            agent.system_message = "test"
            agent.description = None
            agent.instructions = None
            agent.additional_context = None
            agent.retries = 0
            agent.delay_between_retries = 1
            agent.exponential_backoff = False
            agent.stream = None
            agent.stream_events = None
            agent.store_events = False
            agent.events_to_skip = None
            agent.metadata = None
            agent.sub_agents = None
            agent.delegate_to_all_members = False
            agent.stream_member_events = True
            agent.store_member_responses = False
            agent.role = None

            with (
                patch("ii_agent.agents.agent.MessageBuilder"),
                patch("ii_agent.agents.agent.ToolManager"),
                patch("ii_agent.agents.agent.ResponseHandler"),
                patch("ii_agent.agents.agent.HookExecutor"),
                patch("ii_agent.agents.agent.SandboxProvider"),
                patch("ii_agent.agents.agent.HITLHandler"),
                patch("ii_agent.agents.agent.DelegationManager"),
            ):
                agent.__post_init__()

        assert agent.tools == []

    def test_sub_agents_becomes_empty_list_when_none(self):
        from ii_agent.agents.agent import IIAgent

        mock_model = _make_model()

        with (
            patch(
                "ii_agent.agents.agent.ServiceContainer.create",
                return_value=MagicMock(),
            ),
        ):
            agent = object.__new__(IIAgent)
            agent.user_id = "u"
            agent.session_id = "s"
            agent.model = mock_model
            agent.name = "TestAgent"
            agent.id = None
            agent.session_store = None
            agent.session_state = None
            agent.session_summary_manager = None
            agent.tools = []
            agent.tool_call_limit = None
            agent.tool_choice = None
            agent.tool_hooks = None
            agent.pre_hooks = None
            agent.post_hooks = None
            agent.system_message = "test"
            agent.description = None
            agent.instructions = None
            agent.additional_context = None
            agent.retries = 0
            agent.delay_between_retries = 1
            agent.exponential_backoff = False
            agent.stream = None
            agent.stream_events = None
            agent.store_events = False
            agent.events_to_skip = None
            agent.metadata = None
            agent.sub_agents = None
            agent.delegate_to_all_members = False
            agent.stream_member_events = True
            agent.store_member_responses = False
            agent.role = None

            with (
                patch("ii_agent.agents.agent.MessageBuilder"),
                patch("ii_agent.agents.agent.ToolManager"),
                patch("ii_agent.agents.agent.ResponseHandler"),
                patch("ii_agent.agents.agent.HookExecutor"),
                patch("ii_agent.agents.agent.SandboxProvider"),
                patch("ii_agent.agents.agent.HITLHandler"),
                patch("ii_agent.agents.agent.DelegationManager"),
            ):
                agent.__post_init__()

        assert agent.sub_agents == []


# ---------------------------------------------------------------------------
# MessageBuilder
# ---------------------------------------------------------------------------


class TestMessageBuilderGetUserMessage:
    """Test MessageBuilder.get_user_message."""

    def _make_builder(self, system_role="system"):
        from ii_agent.agents.models.builder import MessageBuilder

        model = _make_model(system_role=system_role)
        return MessageBuilder(model=model, system_message="System prompt")

    @pytest.mark.asyncio
    async def test_none_input_no_media_returns_none(self):
        builder = self._make_builder()
        result = await builder.get_user_message(input=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_none_input_with_images_returns_message_with_empty_content(self):
        from ii_agent.files.media import Image

        builder = self._make_builder()
        img = MagicMock(spec=Image)
        result = await builder.get_user_message(input=None, images=[img])
        assert result is not None
        assert result.role == "user"

    @pytest.mark.asyncio
    async def test_string_input_returns_user_message(self):
        builder = self._make_builder()
        result = await builder.get_user_message(input="Hello, agent!")
        assert result is not None
        assert result.content == "Hello, agent!"
        assert result.role == "user"

    @pytest.mark.asyncio
    async def test_list_of_strings_joins_them(self):
        builder = self._make_builder()
        result = await builder.get_user_message(input=["line1", "line2"])
        assert result is not None
        assert "line1" in result.content
        assert "line2" in result.content

    @pytest.mark.asyncio
    async def test_list_of_non_strings_stringifies(self):
        builder = self._make_builder()
        result = await builder.get_user_message(input=[1, 2, 3])
        assert result is not None
        assert result.content is not None

    @pytest.mark.asyncio
    async def test_message_input_returns_same_message(self):
        from ii_agent.agents.models.message import Message

        builder = self._make_builder()
        msg = Message(role="user", content="existing")
        result = await builder.get_user_message(input=msg)
        assert result is msg

    @pytest.mark.asyncio
    async def test_dict_input_validated_as_message(self):
        builder = self._make_builder()
        result = await builder.get_user_message(input={"role": "user", "content": "from dict"})
        assert result is not None
        assert result.content == "from dict"

    @pytest.mark.asyncio
    async def test_dict_input_invalid_raises(self):
        builder = self._make_builder()
        with pytest.raises(Exception):
            await builder.get_user_message(input={"bad": "dict"})

    @pytest.mark.asyncio
    async def test_basemodel_input_serialized_to_json(self):
        from pydantic import BaseModel

        class Payload(BaseModel):
            name: str
            value: int

        builder = self._make_builder()
        payload = Payload(name="test", value=42)
        result = await builder.get_user_message(input=payload)
        assert result is not None
        assert "name" in result.content or "test" in result.content


class TestMessageBuilderGetSystemMessage:
    """Test MessageBuilder.get_system_message."""

    @pytest.mark.asyncio
    async def test_string_system_message_returns_message(self):
        from ii_agent.agents.models.builder import MessageBuilder

        model = _make_model()
        builder = MessageBuilder(model=model, system_message="System instructions.")
        session = MagicMock()
        result = await builder.get_system_message(session=session)
        assert result is not None
        assert result.content == "System instructions."

    @pytest.mark.asyncio
    async def test_message_system_message_returned_as_is(self):
        from ii_agent.agents.models.builder import MessageBuilder
        from ii_agent.agents.models.message import Message

        model = _make_model()
        sys_msg = Message(role="system", content="Pre-built system message")
        builder = MessageBuilder(model=model, system_message=sys_msg)
        session = MagicMock()
        result = await builder.get_system_message(session=session)
        assert result is sys_msg

    @pytest.mark.asyncio
    async def test_none_system_message_returns_none_content_message(self):
        from ii_agent.agents.models.builder import MessageBuilder

        model = _make_model()
        builder = MessageBuilder(model=model, system_message=None)
        session = MagicMock()
        result = await builder.get_system_message(session=session)
        assert result is not None  # Still returns message with None content


class TestMessageBuilderGetRunMessages:
    """Test MessageBuilder.get_run_messages."""

    def _make_session(self, messages=None, summary=None):
        session = MagicMock()
        session.session_id = "test-session"
        session.summary = summary
        session.get_messages = MagicMock(return_value=messages or [])
        return session

    def _make_run_output(self, summary=None):
        from ii_agent.agents.runs.agent import RunOutput

        ro = RunOutput(
            run_id=str(uuid4()),
            session_id="test-session",
            user_id="user-1",
            model="gpt-4",
            agent_name="TestAgent",
        )
        ro.summary = summary
        return ro

    @pytest.mark.asyncio
    async def test_builds_messages_with_string_input(self):
        from ii_agent.agents.models.builder import MessageBuilder

        model = _make_model()
        builder = MessageBuilder(model=model, system_message="System message")
        session = self._make_session()
        run_output = self._make_run_output()

        result = await builder.get_run_messages(
            run_response=run_output,
            input="Hello agent",
            session=session,
        )
        assert result is not None
        assert len(result.messages) >= 1

    @pytest.mark.asyncio
    async def test_includes_history_messages_when_no_summary(self):
        from ii_agent.agents.models.builder import MessageBuilder
        from ii_agent.agents.models.message import Message

        model = _make_model()
        builder = MessageBuilder(model=model, system_message="System message")
        history_msg = Message(role="user", content="Previous message")
        session = self._make_session(messages=[history_msg])
        run_output = self._make_run_output()

        result = await builder.get_run_messages(
            run_response=run_output,
            input="New input",
            session=session,
        )
        # History message should be in messages (may have from_history=True)
        all_content = [m.content for m in result.messages]
        assert "Previous message" in all_content

    @pytest.mark.asyncio
    async def test_uses_summary_instead_of_history_when_run_has_summary(self):
        from ii_agent.agents.models.builder import MessageBuilder
        from ii_agent.agents.models.message import Message
        from ii_agent.agents.models.metrics import Metrics

        model = _make_model()
        builder = MessageBuilder(model=model, system_message=None)

        summary = MagicMock()
        summary.content = "This is the summary content"
        summary.topics = []
        summary.metrics = Metrics()
        summary.updated_at = None

        session = self._make_session()
        run_output = self._make_run_output(summary=summary)

        result = await builder.get_run_messages(
            run_response=run_output,
            input="Continue",
            session=session,
        )
        # Should have at least one message
        assert len(result.messages) > 0

    @pytest.mark.asyncio
    async def test_list_of_messages_added_as_input(self):
        from ii_agent.agents.models.builder import MessageBuilder
        from ii_agent.agents.models.message import Message

        model = _make_model()
        builder = MessageBuilder(model=model, system_message=None)
        session = self._make_session()
        run_output = self._make_run_output()

        msgs = [
            Message(role="user", content="msg1"),
            Message(role="assistant", content="msg2"),
        ]

        result = await builder.get_run_messages(
            run_response=run_output,
            input=msgs,
            session=session,
        )
        assert any(m.content == "msg1" for m in result.messages)
        assert any(m.content == "msg2" for m in result.messages)

    @pytest.mark.asyncio
    async def test_list_of_dicts_with_role_added_as_input(self):
        from ii_agent.agents.models.builder import MessageBuilder

        model = _make_model()
        builder = MessageBuilder(model=model, system_message=None)
        session = self._make_session()
        run_output = self._make_run_output()

        msgs = [
            {"role": "user", "content": "hello"},
        ]
        result = await builder.get_run_messages(
            run_response=run_output,
            input=msgs,
            session=session,
        )
        assert any(m.content == "hello" for m in result.messages)


class TestMessageBuilderGetContinueRunMessages:
    """Test MessageBuilder.get_continue_run_messages."""

    def _make_builder(self):
        from ii_agent.agents.models.builder import MessageBuilder

        return MessageBuilder(model=_make_model(), system_message="System")

    def test_extracts_last_user_message(self):
        from ii_agent.agents.models.message import Message

        builder = self._make_builder()
        msgs = [
            Message(role="system", content="sys"),
            Message(role="user", content="first user"),
            Message(role="assistant", content="response"),
            Message(role="user", content="second user"),
        ]
        result = builder.get_continue_run_messages(msgs)
        assert result.user_message is not None
        assert result.user_message.content == "second user"

    def test_extracts_system_message(self):
        from ii_agent.agents.models.message import Message

        builder = self._make_builder()
        msgs = [
            Message(role="system", content="system-msg"),
            Message(role="user", content="user-msg"),
        ]
        result = builder.get_continue_run_messages(msgs)
        assert result.system_message is not None
        assert result.system_message.content == "system-msg"

    def test_no_user_message_returns_none_user_message(self):
        from ii_agent.agents.models.message import Message

        builder = self._make_builder()
        msgs = [Message(role="system", content="sys")]
        result = builder.get_continue_run_messages(msgs)
        assert result.user_message is None

    def test_messages_list_preserved(self):
        from ii_agent.agents.models.message import Message

        builder = self._make_builder()
        msgs = [
            Message(role="user", content="u1"),
            Message(role="assistant", content="a1"),
        ]
        result = builder.get_continue_run_messages(msgs)
        assert result.messages is msgs


# ---------------------------------------------------------------------------
# DelegationManager
# ---------------------------------------------------------------------------


class TestDelegationManagerFindSubAgent:
    """Test DelegationManager.find_sub_agent_by_id."""

    def _make_dm(self):
        from ii_agent.agents.sub_agent import SubAgentManager

        return SubAgentManager(session_store=None)

    def test_find_by_id(self):
        dm = self._make_dm()
        agent1 = MagicMock()
        agent1.id = "agent-1"
        agent1.name = "Agent1"
        agent2 = MagicMock()
        agent2.id = "agent-2"
        agent2.name = "Agent2"

        result = dm.find_sub_agent_by_id([agent1, agent2], "agent-2")
        assert result is agent2

    def test_find_by_name(self):
        dm = self._make_dm()
        agent1 = MagicMock()
        agent1.id = "agent-1"
        agent1.name = "MyAgent"

        result = dm.find_sub_agent_by_id([agent1], "MyAgent")
        assert result is agent1

    def test_not_found_returns_none(self):
        dm = self._make_dm()
        agent1 = MagicMock()
        agent1.id = "agent-1"
        agent1.name = "Agent1"

        result = dm.find_sub_agent_by_id([agent1], "nonexistent")
        assert result is None

    def test_empty_list_returns_none(self):
        dm = self._make_dm()
        result = dm.find_sub_agent_by_id([], "any-id")
        assert result is None

    def test_none_list_returns_none(self):
        dm = self._make_dm()
        result = dm.find_sub_agent_by_id(None, "any-id")
        assert result is None


class TestDelegationManagerGetSubAgentsDescription:
    """Test DelegationManager.get_sub_agents_description."""

    def _make_dm(self):
        from ii_agent.agents.sub_agent import SubAgentManager

        return SubAgentManager(session_store=None)

    def test_empty_list_returns_empty_string(self):
        dm = self._make_dm()
        result = dm.get_sub_agents_description([])
        assert result == ""

    def test_none_returns_empty_string(self):
        dm = self._make_dm()
        result = dm.get_sub_agents_description(None)
        assert result == ""

    def test_includes_agent_name_and_id(self):
        dm = self._make_dm()
        agent = MagicMock()
        agent.id = "sub-1"
        agent.name = "SubAgent"
        agent.role = None
        agent.description = None

        result = dm.get_sub_agents_description([agent])
        assert "SubAgent" in result
        assert "sub-1" in result

    def test_includes_role_when_set(self):
        dm = self._make_dm()
        agent = MagicMock()
        agent.id = "sub-1"
        agent.name = "SubAgent"
        agent.role = "Researcher"
        agent.description = None

        result = dm.get_sub_agents_description([agent])
        assert "Researcher" in result

    def test_includes_description_when_set(self):
        dm = self._make_dm()
        agent = MagicMock()
        agent.id = "sub-2"
        agent.name = "Writer"
        agent.role = None
        agent.description = "Writes documentation"

        result = dm.get_sub_agents_description([agent])
        assert "Writes documentation" in result

    def test_uses_name_as_id_when_id_is_none(self):
        dm = self._make_dm()
        agent = MagicMock()
        agent.id = None
        agent.name = "OnlyName"
        agent.role = None
        agent.description = None

        result = dm.get_sub_agents_description([agent])
        assert "OnlyName" in result


class TestDelegationManagerInitializeSubAgent:
    """Test DelegationManager.initialize_sub_agent."""

    def test_assigns_session_store_when_sub_agent_has_noop_store(self):
        from ii_agent.agents.sub_agent import SubAgentManager
        from ii_agent.agents.sessions.base import NoOpSessionStore

        real_store = MagicMock()
        dm = SubAgentManager(session_store=real_store)

        sub_agent = MagicMock()
        sub_agent.session_store = NoOpSessionStore()

        dm.initialize_sub_agent(sub_agent)
        assert sub_agent.session_store is real_store

    def test_does_not_overwrite_existing_real_store(self):
        from ii_agent.agents.sub_agent import SubAgentManager

        parent_store = MagicMock()
        dm = SubAgentManager(session_store=parent_store)

        existing_store = MagicMock()
        sub_agent = MagicMock()
        sub_agent.session_store = existing_store

        dm.initialize_sub_agent(sub_agent)
        assert sub_agent.session_store is existing_store

    def test_assigns_when_sub_agent_has_none_store(self):
        from ii_agent.agents.sub_agent import SubAgentManager

        parent_store = MagicMock()
        dm = SubAgentManager(session_store=parent_store)

        sub_agent = MagicMock()
        sub_agent.session_store = None

        dm.initialize_sub_agent(sub_agent)
        assert sub_agent.session_store is parent_store


class TestDelegationManagerGetDelegateTaskFunction:
    """Test DelegationManager.get_delegate_task_function."""

    def _make_dm(self):
        from ii_agent.agents.sub_agent import SubAgentManager

        return SubAgentManager(session_store=None)

    def _make_run_output(self, run_id=None):
        from ii_agent.agents.runs.agent import RunOutput

        return RunOutput(
            run_id=run_id or str(uuid4()),
            session_id="sess-1",
            user_id="user-1",
            model="model",
            agent_name="ParentAgent",
        )

    def _make_session(self):
        session = MagicMock()
        session.session_id = "sess-1"
        return session

    def _make_run_context(self, run_id=None):
        from ii_agent.agents.runs import RunContext

        return RunContext(
            run_id=run_id or str(uuid4()),
            session_id="sess-1",
            user_id="user-1",
        )

    def test_returns_function_for_specific_member(self):
        from ii_agent.agents.tools.function import Function

        dm = self._make_dm()
        run_response = self._make_run_output()
        run_context = self._make_run_context()
        session = self._make_session()
        parent_agent = MagicMock()
        parent_agent.name = "Parent"

        sub_agent = MagicMock()
        sub_agent.id = "sub-1"
        sub_agent.name = "Sub"
        sub_agent.role = None
        sub_agent.description = None

        func = dm.get_delegate_task_function(
            sub_agents=[sub_agent],
            run_response=run_response,
            run_context=run_context,
            session=session,
            parent_agent=parent_agent,
            delegate_to_all_members=False,
        )
        assert isinstance(func, Function)
        assert "sub_agent_task" in func.name

    def test_returns_function_for_all_members(self):
        from ii_agent.agents.tools.function import Function

        dm = self._make_dm()
        run_response = self._make_run_output()
        run_context = self._make_run_context()
        session = self._make_session()
        parent_agent = MagicMock()
        parent_agent.name = "Parent"

        sub_agent = MagicMock()
        sub_agent.id = "sub-1"
        sub_agent.name = "Sub"
        sub_agent.role = None
        sub_agent.description = None

        func = dm.get_delegate_task_function(
            sub_agents=[sub_agent],
            run_response=run_response,
            run_context=run_context,
            session=session,
            parent_agent=parent_agent,
            delegate_to_all_members=True,
        )
        assert isinstance(func, Function)
        assert "sub_agent_task_all" in func.name

    def test_function_has_stop_after_false_and_show_result_true(self):
        dm = self._make_dm()
        run_response = self._make_run_output()
        run_context = self._make_run_context()
        session = self._make_session()
        parent_agent = MagicMock()
        parent_agent.name = "Parent"

        func = dm.get_delegate_task_function(
            sub_agents=[],
            run_response=run_response,
            run_context=run_context,
            session=session,
            parent_agent=parent_agent,
        )
        assert func.stop_after_tool_call is False
        assert func.show_result is True
