from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional

from ii_agent.agents.runs.agent import RunOutput
from ii_agent.agents.runs.base import RunStatus
from ii_agent.agents.sessions.summary import SessionSummary
from ii_agent.agents.models.message import Message
from ii_agent.core.logger import logger

@dataclass
class AgentSession:
    """Agent Session that is stored in the database"""

    # Session UUID
    session_id: str
    # ID of the user interacting with this agent (required)
    user_id: str

    # ID of the agent that this session is associated with
    agent_id: Optional[str] = None

    # Session Data: session_name, session_state, images, videos, audio
    session_data: Optional[Dict[str, Any]] = None
    # Metadata stored with this agent
    metadata: Optional[Dict[str, Any]] = None
    # Agent Data: agent_id, name and model
    agent_data: Optional[Dict[str, Any]] = None
    # List of all runs in the session
    runs: Optional[List[RunOutput]] = None
    # Summary of the session
    summary: Optional["SessionSummary"] = None

    # The unix timestamp when this session was created
    created_at: Optional[int] = None
    # The unix timestamp when this session was last updated
    updated_at: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        session_dict = asdict(self)

        session_dict["runs"] = [run.to_dict() for run in self.runs] if self.runs else None
        session_dict["summary"] = self.summary.to_dict() if self.summary else None

        return session_dict

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Optional[AgentSession]:
        if data is None or data.get("session_id") is None:
            logger.warning("AgentSession is missing session_id")
            return None

        if data.get("user_id") is None:
            logger.warning("AgentSession is missing user_id")
            return None

        runs = data.get("run_messages")
        serialized_runs: List[RunOutput] = []
        if runs:
            for run in runs:
                if isinstance(run, dict):
                    _run_model = RunOutput.from_dict(run)
                    serialized_runs.append(_run_model)
                elif isinstance(run, RunOutput):
                    serialized_runs.append(run)

        summary = data.get("summary")
        if summary is not None and isinstance(summary, dict):
            summary = SessionSummary.from_dict(summary)

        metadata = data.get("metadata")

        return cls(
            session_id=data.get("session_id"),  # type: ignore
            agent_id=data.get("agent_id"),
            user_id=data.get("user_id"),
            agent_data=data.get("agent_data"),
            session_data=data.get("session_data"),
            metadata=metadata,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            runs=serialized_runs,
            summary=summary,
        )

    def add_run(self, run: RunOutput):
        """Adds a RunOutput, together with some calculated data, to the runs list."""
        messages = run.messages
        for m in messages or []:
            if m.metrics is not None:
                m.metrics.duration = None

        if not self.runs:
            self.runs = []

        for i, existing_run in enumerate(self.runs or []):
            if existing_run.run_id == run.run_id:
                self.runs[i] = run
                break
        else:
            self.runs.append(run)

        logger.debug("Added RunOutput to Agent Session")

    def get_run(self, run_id: str) -> Optional[RunOutput]:
        for run in self.runs or []:
            if run.run_id == run_id:
                return run
        return None

    def get_messages(
        self,
        agent_id: Optional[str] = None,
        last_n_runs: Optional[int] = None,
        limit: Optional[int] = None,
        skip_roles: Optional[List[str]] = None,
        skip_statuses: Optional[List[RunStatus]] = None,
        skip_history_messages: bool = True,
    ) -> List[Message]:
        """Returns the messages belonging to the session that fit the given criteria.

        Args:
            agent_id: The id of the agent to get the messages from.
            last_n_runs: The number of runs to return messages from, counting from the latest. Defaults to all runs.
            last_n_messages: The number of messages to return, counting from the latest. Defaults to all messages.
            skip_roles: Skip messages with these roles.
            skip_statuses: Skip messages with these statuses.
            skip_history_messages: Skip messages that were tagged as history in previous runs.

        Returns:
            A list of Messages belonging to the session.
        """

        def _should_skip_message(
            message: Message,
            skip_roles: Optional[List[str]] = None,
            skip_history_messages: bool = True,
        ) -> bool:
            """Logic to determine if a message should be skipped"""
            # Skip messages that were tagged as history in previous runs
            if hasattr(message, "from_history") and message.from_history and skip_history_messages:
                return True

            # Skip messages with specified role
            if skip_roles and message.role in skip_roles:
                return True

            return False

        if not self.runs:
            return []

        if skip_statuses is None:
            # ABORTED runs are valid history; only skip PAUSED and ERROR
            skip_statuses = [RunStatus.PAUSED]

        # Filter by status
        runs = [run for run in self.runs if run.status not in skip_statuses]  # type: ignore

        messages_from_history = []
        system_message = None

        # Limit the number of messages returned if limit is set
        if limit is not None:
            for run_response in runs:
                if not run_response or not run_response.messages:
                    continue

                for message in run_response.messages or []:
                    if _should_skip_message(message, skip_roles, skip_history_messages):
                        continue

                    if message.role == "system":
                        # Only add the system message once
                        if system_message is None:
                            system_message = message
                    else:
                        messages_from_history.append(message)

            if system_message:
                messages_from_history = [system_message] + messages_from_history[
                    -(limit - 1) :
                ]  # Grab one less message then add the system message
            else:
                messages_from_history = messages_from_history[-limit:]

            # Remove tool result messages that don't have an associated assistant message with tool calls
            while len(messages_from_history) > 0 and messages_from_history[0].role == "tool":
                messages_from_history.pop(0)

        # If limit is not set, return all messages
        else:
            runs_to_process = runs[-last_n_runs:] if last_n_runs is not None else runs
            for run_response in runs_to_process:
                if not run_response or not run_response.messages:
                    continue

                for message in run_response.messages or []:
                    if _should_skip_message(message, skip_roles, skip_history_messages):
                        continue

                    if message.role == "system":
                        # Only add the system message once
                        if system_message is None:
                            system_message = message
                            messages_from_history.append(system_message)
                    else:
                        messages_from_history.append(message)

        logger.debug(f"Getting messages from previous runs: {len(messages_from_history)}")
        return messages_from_history

    def get_chat_history(self, last_n_runs: Optional[int] = None) -> List[Message]:
        """Return the chat history (user and assistant messages) for the session.
        Use get_messages() for more filtering options.

        Args:
            last_n_runs: Number of recent runs to include. If None, all runs will be considered.

        Returns:
            A list of user and assistant Messages belonging to the session.
        """
        return self.get_messages(skip_roles=["system", "tool"], last_n_runs=last_n_runs)

    def get_tool_calls(self, num_calls: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns a list of tool calls from the messages"""

        tool_calls = []
        if self.runs:
            session_runs = self.runs
            for run_response in session_runs[::-1]:
                if run_response and run_response.messages:
                    for message in run_response.messages or []:
                        if message.tool_calls:
                            for tool_call in message.tool_calls:
                                tool_calls.append(tool_call)
                                if num_calls and len(tool_calls) >= num_calls:
                                    return tool_calls
        return tool_calls

    def get_session_summary(self) -> Optional[SessionSummary]:
        """Get the session summary for the session"""

        if self.summary is None:
            return None
        return self.summary
