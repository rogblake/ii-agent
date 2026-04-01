"""
Abstract base class for session storage implementations.

This module defines the SessionStore interface that all session storage
implementations must follow. This allows for different storage backends
(PostgreSQL, Redis, DynamoDB, etc.) while maintaining a consistent interface.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from ii_agent.tasks.models import RunTask
from ii_agent.tasks.types import RunStatus
from ii_agent.agents.models.message import Message
from ii_agent.agents.runs.agent import RunOutput
from ii_agent.agents.sessions.agent import AgentSession


class SessionStore(ABC):
    """
    Abstract base class for session storage implementations.

    This interface defines the contract for session stores, which are responsible for:
    1. Managing run task lifecycle (create, update status, retrieve)
    2. Persisting run messages and outputs
    3. Retrieving conversation history for LLM context
    4. Managing session metadata and state

    Implementations must handle:
    - Atomic operations for run persistence
    - Optimistic locking for concurrent updates
    - Efficient history retrieval for large sessions
    - Proper cleanup and resource management
    """

    # -------------------------------------------------------------------------
    # Run Task Lifecycle Methods
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_by_run_id(self, *, session_id: str, run_id: str) -> Optional[RunOutput]:
        pass

    @abstractmethod
    async def get_or_create_run_task(
        self,
        *,
        session_id: str,
        run_id: str,
        status: RunStatus = RunStatus.RUNNING,
    ) -> RunTask:
        """
        Create a new run task at the start of an agent run.

        This should be called at the very beginning of arun() to track
        the run lifecycle. The returned RunTask contains the version
        for optimistic locking on subsequent updates.

        Args:
            session_id: The session ID this run belongs to.
            run_id: The run ID (required - should match RunOutput.run_id).
            status: Initial status (default: RUNNING).

        Returns:
            The created RunTask with version for optimistic locking.

        Raises:
            Exception: If an error occurs during creation.
        """
        pass

    @abstractmethod
    async def update_run_status(
        self,
        *,
        run_id: str,
        status: RunStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update the status of a run task.

        Implementations should use optimistic locking to prevent race conditions.
        State machine: Terminal states (CANCELLED, FAILED, ERROR, COMPLETED,
        SYSTEM_INTERRUPTED) can only be set if current status is RUNNING.

        Args:
            run_id: The run ID to update.
            status: The new status.
            error_message: Error message if status is FAILED or ERROR.

        Returns:
            True if the update was successful.

        Raises:
            StaleDataError: If task is not RUNNING when trying to set terminal status.
            ValueError: If task not found.
        """
        pass

    @abstractmethod
    async def get_run_task(self, run_id: str) -> Optional[RunTask]:
        """
        Get a run task by ID.

        Args:
            run_id: The run ID to fetch.

        Returns:
            RunTask if found, None otherwise.
        """
        pass

    # -------------------------------------------------------------------------
    # Message Persistence Methods
    # -------------------------------------------------------------------------

    @abstractmethod
    async def save_run(self, run: RunOutput) -> None:
        """
        Save a run's messages and update the run task status atomically.

        The run task must already exist (created via create_run_task at the
        start of arun). This method should:
        1. Update the existing RunTask status (with optimistic locking)
        2. Upsert the run message record

        All operations should be performed in a single transaction for atomicity.

        Args:
            run: The RunOutput to persist. Must have a valid run_id that
                 corresponds to an existing RunTask.

        Raises:
            ValueError: If run_id is missing or task doesn't exist.
            StaleDataError: If invalid state transition.
            Exception: If an error occurs during persistence.
        """
        pass

    # -------------------------------------------------------------------------
    # History Retrieval Methods
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_history_messages(
        self,
        session_id: str,
        *,
        last_n_runs: Optional[int] = None,
        skip_parent_runs: bool = True,
        skip_statuses: Optional[List[RunStatus]] = None,
        skip_roles: Optional[List[str]] = None,
        skip_history_messages: bool = True,
    ) -> List[Message]:
        """
        Get history messages for a session, optimized for LLM context.

        This method retrieves messages from previous runs that should be
        included in the context for the next LLM call.

        Args:
            session_id: The session ID.
            last_n_runs: Limit to the N most recent runs. If None, returns all.
            skip_parent_runs: If True, skip runs that have a parent_run_id (nested runs).
            skip_statuses: Skip runs with these statuses. Defaults to [paused, cancelled, error].
            skip_roles: Skip messages with these roles.
            skip_history_messages: Skip messages that were tagged as history in previous runs.

        Returns:
            List of Message objects ordered by creation time (oldest first).
        """
        pass

    @abstractmethod
    async def get_session_messages(
        self,
        session_id: str,
        last_n_runs: Optional[int] = None,
        skip_parent_runs: bool = True,
    ) -> List[RunOutput]:
        """
        Get run outputs for a session, optimized for model context retrieval.

        This is more efficient than loading the full session when you only need
        the messages to pass to the model.

        Args:
            session_id: The session ID.
            last_n_runs: Limit to the N most recent runs. If None, returns all.
            skip_parent_runs: If True, skip runs that have a parent_run_id (nested runs).

        Returns:
            List of RunOutput objects ordered by creation time (oldest first).
        """
        pass

    @abstractmethod
    async def get_last_run(
        self,
        session_id: str,
        *,
        status: Optional[RunStatus] = None,
    ) -> Optional[RunOutput]:
        """
        Get the most recent run for a session.

        Args:
            session_id: The session ID.
            status: Optional status filter.

        Returns:
            RunOutput if found, None otherwise.
        """
        pass

    # -------------------------------------------------------------------------
    # Session Management Methods
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_session(self, session_id: str, user_id: str) -> AgentSession:
        """
        Read an agent session from storage.

        Args:
            session_id: ID of the session to read.
            user_id: User ID to filter by (optional security check).

        Returns:
            AgentSession if found.

        Raises:
            NotFoundException: If session not found.
            Exception: If an error occurs during retrieval.
        """
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and its messages.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        pass


class NoOpSessionStore(SessionStore):
    """
    A no-operation session store that does nothing.

    This implementation is useful for:
    - Testing scenarios where persistence is not needed
    - Running agents in stateless/ephemeral mode
    - Situations where session tracking is handled externally
    """

    async def get_by_run_id(self, *, session_id: str, run_id: str) -> Optional[RunOutput]:
        return None

    async def get_or_create_run_task(
        self,
        *,
        session_id: str,
        run_id: str,
        status: RunStatus = RunStatus.RUNNING,
    ) -> RunTask:
        task = RunTask()
        task.id = run_id  # type: ignore
        task.session_id = session_id
        task.status = status.value
        return task

    async def update_run_status(
        self,
        *,
        run_id: str,
        status: RunStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        return True

    async def get_run_task(self, run_id: str) -> Optional[RunTask]:
        return None

    async def save_run(self, run: RunOutput) -> None:
        pass

    async def get_history_messages(
        self,
        session_id: str,
        *,
        last_n_runs: Optional[int] = None,
        skip_parent_runs: bool = True,
        skip_statuses: Optional[List[RunStatus]] = None,
        skip_roles: Optional[List[str]] = None,
        skip_history_messages: bool = True,
    ) -> List[Message]:
        return []

    async def get_session_messages(
        self,
        session_id: str,
        last_n_runs: Optional[int] = None,
        skip_parent_runs: bool = True,
    ) -> List[RunOutput]:
        return []

    async def get_last_run(
        self,
        session_id: str,
        *,
        status: Optional[RunStatus] = None,
    ) -> Optional[RunOutput]:
        return None

    async def get_session(self, session_id: str, user_id: str) -> AgentSession:
        return AgentSession(session_id=session_id, user_id=user_id, runs=[])

    async def delete_session(self, session_id: str) -> bool:
        return True
