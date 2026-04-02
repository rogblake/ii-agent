"""
Agent Session Store - Manages session persistence for agent operations.

Uses a session factory pattern to acquire short-lived database connections
rather than holding connections for long-running tasks.

Key features:
- Atomic run task creation and message persistence
- Proper status tracking throughout run lifecycle
- Efficient history retrieval for LLM context
- Optimistic locking for concurrent updates
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncContextManager, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from ii_agent.core.exceptions import NotFoundException
from ii_agent.tasks.models import RunTask
from ii_agent.tasks.types import RunStatus
from ii_agent.sessions.models import Session
from ii_agent.agents.runs.models import AgentRunMessage, SessionSummary
from ii_agent.agents.models.message import Message
from ii_agent.agents.runs.agent import RunOutput
from ii_agent.agents.sessions.agent import AgentSession
from ii_agent.agents.sessions.base import SessionStore
from ii_agent.core.logger import logger


class AgentSessionStore(SessionStore):
    """
    Manages database session lifecycle for agent operations.

    Uses a session factory pattern to acquire short-lived sessions
    rather than holding connections for long-running tasks.

    This store handles:
    1. Run task lifecycle (create, update status)
    2. Message persistence with atomic operations
    3. History retrieval for LLM context
    4. Session management
    """

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self._session_maker = session_maker

    def _get_db_session(self) -> AsyncContextManager[AsyncSession]:
        """
        Get a new async session context manager.

        Usage:
            async with store._get_db_session() as db:
                await db.execute(...)
                await db.commit()
        """
        return self._session_maker()

    # -------------------------------------------------------------------------
    # Run Task Lifecycle Methods
    # -------------------------------------------------------------------------

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
        the run lifecycle in the database. The returned RunTask contains
        the version for optimistic locking on subsequent updates.

        Args:
            session_id: The session ID this run belongs to.
            run_id: The run ID (required - should match RunOutput.run_id).
            status: Initial status (default: RUNNING).

        Returns:
            The created RunTask with version for optimistic locking.

        Raises:
            Exception: If an error occurs during creation.
        """

        from ii_agent.tasks.types import TaskType

        async with self._get_db_session() as db:
            try:
                task_id = uuid.UUID(run_id)
                result = await db.execute(select(RunTask).where(RunTask.id == task_id))
                run_task = result.scalar_one_or_none()
                if run_task:
                    return run_task

                run_task = RunTask(
                    id=task_id,
                    session_id=session_id,
                    task_type=TaskType.AGENT_RUN,
                    status=status,
                )
                db.add(run_task)
                await db.commit()
                await db.refresh(run_task)

                logger.info(
                    f"Created run task {task_id} for session {session_id} (version={run_task.version})"
                )
                return run_task
            except Exception as e:
                logger.error(f"Error creating run task for session {session_id}: {e}")
                await db.rollback()
                raise

    async def update_run_status(
        self,
        *,
        run_id: str,
        status: RunStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update the status of a run task using ORM for optimistic locking.

        State machine:
        - Terminal → terminal is blocked (e.g. COMPLETED → FAILED).
        - Terminal → active is allowed (e.g. COMPLETED → RUNNING for continue_run).
        - Active  → any is allowed.

        Args:
            run_id: The run ID to update.
            status: The new status.
            error_message: Error message if status is FAILED or ERROR.

        Returns:
            True if the update was successful.

        Raises:
            StaleDataError: If trying to set a terminal status on an already-terminal task.
            ValueError: If task not found.
        """
        try:
            async with self._get_db_session() as db:
                task_uuid = uuid.UUID(run_id)

                # Fetch the task via ORM (enables optimistic locking)
                result = await db.execute(select(RunTask).where(RunTask.id == task_uuid))
                task = result.scalar_one_or_none()

                if task is None:
                    raise ValueError(f"Run task {run_id} not found")

                # Block terminal → terminal (e.g. COMPLETED → FAILED).
                # Allow terminal → active for resume/continue_run (e.g. COMPLETED → RUNNING).
                if (
                    task.status in RunStatus.terminal_states()
                    and status in RunStatus.terminal_states()
                ):
                    raise StaleDataError(
                        f"Cannot transition run {run_id} from {task.status} to {status}. "
                        f"Task is already in a terminal state."
                    )

                # Update via attribute assignment (SQLAlchemy handles optimistic locking)
                task.status = status
                if error_message is not None:
                    task.error_message = error_message

                await db.commit()
                await db.refresh(task)
                logger.debug(f"Updated run task {run_id} status to {status}")
                return task

        except (StaleDataError, ValueError):
            raise
        except Exception as e:
            logger.error(f"Error updating run task {run_id} status: {e}")
            raise

    async def get_run_task(self, run_id: str) -> Optional[RunTask]:
        """
        Get a run task by ID.

        Args:
            run_id: The run ID to fetch.

        Returns:
            RunTask if found, None otherwise.
        """
        try:
            async with self._get_db_session() as db:
                task_uuid = uuid.UUID(run_id)
                result = await db.execute(select(RunTask).where(RunTask.id == task_uuid))
                return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Error getting run task {run_id}: {e}")
            raise

    # -------------------------------------------------------------------------
    # Message Persistence Methods
    # -------------------------------------------------------------------------

    async def save_run(self, run: RunOutput) -> None:
        """
        Save a run's messages and update the run task status atomically.

        The run task must already exist (created via create_run_task at the start of arun).
        This method:
        1. Updates the existing RunTask status via ORM (for optimistic locking)
        2. Upserts the AgentRunMessage record

        State machine: Terminal states can only be set from RUNNING status.

        All operations are performed in a single transaction for atomicity.

        Args:
            run: The RunOutput to persist. Must have a valid run_id that corresponds
                 to an existing RunTask.

        Raises:
            ValueError: If run_id is missing or task doesn't exist.
            StaleDataError: If invalid state transition.
            Exception: If an error occurs during persistence.
        """
        if not run.run_id:
            raise ValueError("run_id is required - create_run_task must be called first")

        try:
            async with self._get_db_session() as db:
                run_uuid = uuid.UUID(run.run_id)

                # Fetch the existing run task (must exist)
                existing_task = await db.execute(select(RunTask).where(RunTask.id == run_uuid))
                task = existing_task.scalar_one_or_none()

                if task is None:
                    raise NotFoundException(
                        f"Run task {run_uuid} not found for session: {run.session_id}."
                    )

                task.status = run.status

                # Serialize data
                messages_data = {
                    "messages": [m.to_dict() for m in (run.messages or [])],
                }
                run_input_data = run.input.to_dict() if run.input else None
                metrics_data = run.metrics.to_dict() if run.metrics else None

                additional_info: Dict[str, Any] = {
                    "agent_id": run.agent_id,
                    "agent_name": run.agent_name,
                    "user_id": run.user_id,
                    "parent_run_id": run.parent_run_id,
                    "model": run.model,
                    "model_provider": run.model_provider,
                    "metadata": run.metadata,
                    "session_state": run.session_state,
                }
                # Remove None values to keep storage compact
                additional_info = {k: v for k, v in additional_info.items() if v is not None}

                # Check if message record exists
                existing_msg = await db.execute(
                    select(AgentRunMessage).where(AgentRunMessage.run_id == run_uuid)
                )
                message_record = existing_msg.scalar_one_or_none()
                tools = []
                if run.tools:
                    tools = [_t.to_dict() for _t in run.tools]
                if message_record:
                    # Update existing message record via ORM (for optimistic locking)
                    message_record.run_input = run_input_data
                    message_record.messages = messages_data
                    message_record.metrics = metrics_data
                    message_record.model_id = run.model
                    message_record.status = run.status
                    message_record.additional_info = additional_info
                    message_record.tools = tools
                    if run.parent_run_id:
                        message_record.parent_run_id = uuid.UUID(run.parent_run_id)
                else:
                    # Create new message record
                    parent_run_uuid = uuid.UUID(run.parent_run_id) if run.parent_run_id else None
                    message_record = AgentRunMessage(
                        session_id=run.session_id,
                        run_id=run_uuid,
                        parent_run_id=parent_run_uuid,
                        model_id=run.model,
                        status=run.status,
                        run_input=run_input_data,
                        messages=messages_data,
                        metrics=metrics_data,
                        additional_info=additional_info,
                        tools=tools,
                    )
                    db.add(message_record)
                await db.flush()

                # Save session summary if present
                if run.summary is not None:
                    await db.refresh(message_record)
                    existing_summary = await db.execute(
                        select(SessionSummary).where(SessionSummary.session_id == run.session_id)
                    )
                    summary_record = existing_summary.scalar_one_or_none()

                    summary_metrics = run.summary.metrics.to_dict() if run.summary.metrics else None

                    if summary_record:
                        summary_record.content = run.summary.content
                        summary_record.topics = run.summary.topics
                        summary_record.metrics = summary_metrics
                        summary_record.agent_run_id = message_record.id
                    else:
                        new_summary = SessionSummary(
                            session_id=run.session_id,
                            content=run.summary.content,
                            topics=run.summary.topics,
                            metrics=summary_metrics,
                            agent_run_id=message_record.id,
                        )
                        db.add(new_summary)

                await db.commit()
        except (StaleDataError, ValueError) as e:
            logger.error(f"Error saving run to session {run.session_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error saving run to session {run.session_id}: {e}")
            raise

    # -------------------------------------------------------------------------
    # History Retrieval Methods
    # -------------------------------------------------------------------------

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
        if skip_statuses is None:
            # ABORTED runs are valid history; only skip PAUSED and ERROR
            skip_statuses = [RunStatus.PAUSED]

        try:
            runs = await self.get_session_messages(
                session_id=session_id,
                last_n_runs=last_n_runs,
                skip_parent_runs=skip_parent_runs,
            )

            messages: List[Message] = []
            system_message: Optional[Message] = None

            for run in runs:
                # Skip runs with excluded statuses
                if run.status in skip_statuses:
                    continue

                for msg in run.messages or []:
                    # Tag message with the run's model for model-specific filtering
                    if msg.model is None:
                        msg.model = run.model

                    # Skip history-tagged messages if requested
                    if skip_history_messages and getattr(msg, "from_history", False):
                        continue

                    # Skip messages with excluded roles
                    if skip_roles and msg.role in skip_roles:
                        continue

                    # Handle system message separately (only include once)
                    if msg.role == "system":
                        if system_message is None:
                            system_message = msg
                    else:
                        messages.append(msg)

            # Prepend system message if we have one
            if system_message:
                messages = [system_message] + messages

            logger.debug(f"Retrieved {len(messages)} history messages for session {session_id}")
            return messages

        except Exception as e:
            logger.error(f"Error getting history messages for {session_id}: {e}")
            raise

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
        try:
            async with self._get_db_session() as db:
                stmt = (
                    select(AgentRunMessage)
                    .where(AgentRunMessage.session_id == session_id)
                    .order_by(AgentRunMessage.created_at.asc())
                )

                result = await db.execute(stmt)
                message_rows = result.scalars().all()

                runs: List[RunOutput] = []
                for msg_row in message_rows:
                    # Get additional_info first to extract required fields
                    additional = msg_row.additional_info or {}

                    # Skip nested runs if requested
                    if skip_parent_runs and additional.get("parent_run_id") is not None:
                        continue

                    run_data: Dict[str, Any] = {
                        # Required fields
                        "run_id": str(msg_row.run_id),
                        "session_id": msg_row.session_id,
                        "user_id": additional.get("user_id", ""),
                        "model": msg_row.model_id,
                        "agent_name": additional.get("agent_name", ""),
                        # Optional fields
                        "status": msg_row.status,
                        "messages": msg_row.messages.get("messages", [])
                        if msg_row.messages
                        else [],
                        "metrics": msg_row.metrics,
                        "run_input": msg_row.run_input,
                        "created_at": int(msg_row.created_at.timestamp())
                        if msg_row.created_at
                        else None,
                        **additional,
                    }

                    run = RunOutput.from_dict(run_data)
                    runs.append(run)

                # Apply last_n_runs limit
                if last_n_runs is not None and len(runs) > last_n_runs:
                    runs = runs[-last_n_runs:]

                return runs

        except Exception as e:
            logger.error(f"Error getting session messages for {session_id}: {e}")
            raise

    async def get_by_run_id(self, *, run_id: str, session_id: str) -> Optional[RunOutput]:
        """
        Get the most recent run for a session.

        Args:
            session_id: The session ID.
            status: Optional status filter.

        Returns:
            RunOutput if found, None otherwise.
        """
        try:
            async with self._get_db_session() as db:
                stmt = select(AgentRunMessage).where(
                    AgentRunMessage.session_id == session_id,
                    AgentRunMessage.run_id == run_id,
                )
                result = await db.execute(stmt)
                msg_row = result.scalar_one_or_none()

                if msg_row is None:
                    return None

                additional = msg_row.additional_info or {}
                run_data: Dict[str, Any] = {
                    "run_id": str(msg_row.run_id),
                    "session_id": msg_row.session_id,
                    "user_id": additional.get("user_id", ""),
                    "model": msg_row.model_id,
                    "agent_name": additional.get("agent_name", ""),
                    "status": msg_row.status,
                    "tools": msg_row.tools,
                    "messages": msg_row.messages.get("messages", []) if msg_row.messages else [],
                    "metrics": msg_row.metrics,
                    "run_input": msg_row.run_input,
                    "created_at": int(msg_row.created_at.timestamp())
                    if msg_row.created_at
                    else None,
                    **additional,
                }

                return RunOutput.from_dict(run_data)

        except Exception as e:
            logger.error(f"Error getting last run for session {session_id}: {e}")
            raise

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
        try:
            async with self._get_db_session() as db:
                stmt = (
                    select(AgentRunMessage)
                    .where(AgentRunMessage.session_id == session_id)
                    .order_by(AgentRunMessage.created_at.desc())
                    .limit(1)
                )

                if status:
                    stmt = stmt.where(AgentRunMessage.status == status.value)

                result = await db.execute(stmt)
                msg_row = result.scalar_one_or_none()

                if msg_row is None:
                    return None

                additional = msg_row.additional_info or {}
                run_data: Dict[str, Any] = {
                    "run_id": str(msg_row.run_id),
                    "session_id": msg_row.session_id,
                    "user_id": additional.get("user_id", ""),
                    "model": msg_row.model_id,
                    "agent_name": additional.get("agent_name", ""),
                    "status": msg_row.status,
                    "messages": msg_row.messages.get("messages", []) if msg_row.messages else [],
                    "metrics": msg_row.metrics,
                    "run_input": msg_row.run_input,
                    "created_at": int(msg_row.created_at.timestamp())
                    if msg_row.created_at
                    else None,
                    **additional,
                }

                return RunOutput.from_dict(run_data)

        except Exception as e:
            logger.error(f"Error getting last run for session {session_id}: {e}")
            raise

    # -------------------------------------------------------------------------
    # Session Management Methods
    # -------------------------------------------------------------------------

    async def get_session(self, session_id: str, user_id: str) -> AgentSession:
        """
        Read an agent session from the database.

        Args:
            session_id: ID of the session to read.
            user_id: User ID to filter by (optional security check).

        Returns:
            AgentSession if found.

        Raises:
            NotFoundException: If session not found.
            Exception: If an error occurs during retrieval.
        """
        try:
            async with self._get_db_session() as db:
                # 1. Query the Session table
                session_stmt = select(Session).where(
                    Session.id == session_id, Session.user_id == user_id
                )

                session_result = await db.execute(session_stmt)
                session_row = session_result.scalar_one_or_none()

                if session_row is None:
                    raise NotFoundException(
                        f"Session '{session_id}' not found for user '{user_id}'"
                    )

                # 2. Check if a summary exists for this session
                summary_stmt = select(SessionSummary).where(SessionSummary.session_id == session_id)
                summary_result = await db.execute(summary_stmt)
                summary_row = summary_result.scalar_one_or_none()

                # 3. Query the AgentRunMessage table for messages
                # If summary exists, only fetch messages after the summarised point
                messages_stmt = select(AgentRunMessage).where(
                    AgentRunMessage.session_id == session_id
                )
                if summary_row is not None:
                    messages_stmt = messages_stmt.where(
                        AgentRunMessage.id >= summary_row.agent_run_id
                    )
                messages_stmt = messages_stmt.order_by(AgentRunMessage.id.asc())

                messages_result = await db.execute(messages_stmt)
                message_rows = messages_result.scalars().all()

            # 4. Map to AgentSession
            return self._map_to_agent_session(session_row, message_rows, summary_row)

        except NotFoundException:
            raise
        except Exception as e:
            logger.error(f"Error reading session {session_id}: {e}")
            raise

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and its messages.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        try:
            async with self._get_db_session() as db:
                # Delete messages first (foreign key constraint)
                from sqlalchemy import delete

                # Delete run messages
                await db.execute(
                    delete(AgentRunMessage).where(AgentRunMessage.session_id == session_id)
                )

                # Delete run tasks
                await db.execute(delete(RunTask).where(RunTask.session_id == session_id))

                # Delete session
                session_stmt = select(Session).where(Session.id == session_id)
                result = await db.execute(session_stmt)
                session_row = result.scalar_one_or_none()

                if session_row is None:
                    return False

                await db.delete(session_row)
                await db.commit()
                return True

        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            raise

    # -------------------------------------------------------------------------
    # Private Helper Methods
    # -------------------------------------------------------------------------

    def _map_to_agent_session(
        self,
        session_row: Session,
        message_rows: List[AgentRunMessage],
        summary_row: Optional[SessionSummary] = None,
    ) -> AgentSession:
        """
        Map database rows to AgentSession dataclass.

        Args:
            session_row: The Session ORM object.
            message_rows: List of AgentRunMessage ORM objects.
            summary_row: Optional SessionSummary ORM object.

        Returns:
            AgentSession dataclass instance.
        """
        # Convert message rows to RunOutput objects
        run_outputs: List[RunOutput] = []
        for msg_row in message_rows:
            # Build run data from AgentRunMessage fields
            run_data: Dict[str, Any] = {
                "run_id": str(msg_row.run_id),
                "session_id": msg_row.session_id,
                "parent_run_id": str(msg_row.parent_run_id) if msg_row.parent_run_id else None,
                "model": msg_row.model_id,  # DB column is model_id, RunOutput uses model
                "status": msg_row.status,
                "messages": msg_row.messages.get("messages", []) if msg_row.messages else [],
                "tools": msg_row.tools,
                "metrics": msg_row.metrics,
                "run_input": msg_row.run_input,  # Maps to RunOutput.input via from_dict
                "created_at": int(msg_row.created_at.timestamp()) if msg_row.created_at else None,
            }

            # Merge additional_info fields (agent_id, model, content, etc.)
            if msg_row.additional_info:
                run_data.update(msg_row.additional_info)

            run = RunOutput.from_dict(run_data)
            if run:
                run_outputs.append(run)

        # Build AgentSession data dict
        # TODO: rework this field mapping to be cleaner
        session_data: Dict[str, Any] = {
            "session_id": session_row.id,
            "user_id": session_row.user_id,
            "agent_id": session_row.agent_type,
            "session_data": {
                "name": session_row.name,
                "status": session_row.status,
            },
            "metadata": {
                "model_setting_id": session_row.model_setting_id,
                "is_public": session_row.is_public,
                "public_url": session_row.public_url,
            },
            "run_messages": run_outputs,
            "created_at": (
                int(session_row.created_at.timestamp()) if session_row.created_at else None
            ),
            "updated_at": (
                int(session_row.updated_at.timestamp()) if session_row.updated_at else None
            ),
        }

        if summary_row:
            session_data["summary"] = {
                "content": summary_row.content,
                "topics": summary_row.topics,
                "metrics": summary_row.metrics,
                "updated_at": summary_row.updated_at,
            }

        return AgentSession.from_dict(session_data)
