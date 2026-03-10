"""Service layer for sessions domain - business logic only."""

from __future__ import annotations

import uuid
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agent.runs.service import AgentRunService

from ii_agent.agent.events.models import EventType, Event
from ii_agent.agent.events.repository import EventRepository
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.core.config.settings import Settings
from ii_agent.core.storage.locations import get_conversation_agent_state_path

logger = logging.getLogger(__name__)


class SessionService:
    """Service for managing chat sessions - business logic layer."""

    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        event_repo: EventRepository,
        agent_run_service: AgentRunService,
        file_store,
        sandbox_repo,
        config: Settings,
    ) -> None:
        self._config = config
        self._session_repo = session_repo
        self._event_repo = event_repo
        self._agent_run_service = agent_run_service
        self._file_store = file_store
        self._sandbox_repo = sandbox_repo

    # ==================== Session CRUD ====================

    async def create_session(
        self,
        db: AsyncSession,
        session_uuid: uuid.UUID,
        user_id: str,
        agent_state_path: str,
        api_version: str = "v0",
        name: Optional[str] = None,
    ) -> Session:
        """Create a new session with a UUID-based workspace directory."""
        session = Session(
            id=str(session_uuid),
            user_id=user_id,
            name=name,
            status="active",
            api_version=api_version,
            agent_state_path=agent_state_path,
        )
        return await self._session_repo.create(db, session)

    async def get_session_by_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[Session]:
        """Get a session by its UUID with project loaded."""
        return await self._session_repo.get_by_id_with_project(db, session_id)

    async def get_session_details(
        self, db: AsyncSession, session_id: str, user_id: str
    ) -> Optional[dict]:
        """Get detailed information for a specific session."""
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)
        if not session:
            return None
        return self._session_to_dict(session)

    async def get_public_session_details(
        self, db: AsyncSession, session_id: str
    ) -> Optional[dict]:
        """Get detailed information for a public session."""
        session = await self._session_repo.get_public_by_id(db, session_id)
        if not session:
            return None
        return self._session_to_dict(session, include_project=False)

    # ==================== Session Updates ====================

    async def _update_session_field(self, db: AsyncSession, session_id, **fields) -> None:
        """Update one or more fields on a session."""
        session = await self._session_repo.get_by_id(db, session_id)
        if session:
            for key, value in fields.items():
                setattr(session, key, value)
            await self._session_repo.update(db, session)

    async def update_sandbox_id(
        self, db: AsyncSession, session_uuid: uuid.UUID, sandbox_id: str
    ) -> None:
        await self._update_session_field(db, session_uuid, sandbox_id=sandbox_id)

    async def update_session_name(
        self, db: AsyncSession, session_id: uuid.UUID, name: str
    ) -> None:
        await self._update_session_field(db, session_id, name=name)

    async def update_session_agent_type(
        self, db: AsyncSession, session_id: uuid.UUID, agent_type: str
    ) -> None:
        await self._update_session_field(db, session_id, agent_type=agent_type)

    async def update_session_llm_setting_id(
        self, db: AsyncSession, session_id: uuid.UUID, llm_setting_id: Optional[str]
    ) -> None:
        await self._update_session_field(db, session_id, llm_setting_id=llm_setting_id)

    async def update_session_public_url(
        self, db: AsyncSession, session_id: uuid.UUID, public_url: str
    ) -> None:
        await self._update_session_field(db, session_id, public_url=public_url)

    # ==================== Query Operations ====================

    async def get_session_by_workspace(
        self, db: AsyncSession, workspace_dir: str
    ) -> Optional[Session]:
        """Get a session by its workspace directory."""
        return await self._session_repo.get_by_workspace(db, workspace_dir)

    async def session_has_sandbox(self, db: AsyncSession, session_id: uuid.UUID) -> bool:
        """Check if a session has a sandbox."""
        sandbox_id = await self._session_repo.get_sandbox_id(db, session_id)
        return sandbox_id is not None

    async def get_session_user_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[str]:
        """Get the user ID for a session."""
        return await self._session_repo.get_user_id(db, session_id)

    async def get_session_llm_setting_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[str]:
        """Get the LLM setting ID for a session."""
        return await self._session_repo.get_llm_setting_id(db, session_id)

    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: str,
        search_term: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        public_only: Optional[bool] = False,
        session_type: Optional[str] = None,
    ) -> tuple[List[dict], int]:
        """Get sessions for a user with optional search and pagination."""
        sessions, total = await self._session_repo.get_user_sessions(
            db,
            user_id=user_id,
            search_term=search_term,
            page=page,
            per_page=per_page,
            public_only=public_only,
            session_type=session_type,
        )
        return [self._session_to_dict(s) for s in sessions], total

    # ==================== Session State ====================

    async def soft_delete_session(
        self, db: AsyncSession, session_id: str, user_id: str
    ) -> None:
        """Soft delete a session by setting its deleted_at timestamp."""
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)
        if not session:
            raise SessionNotFoundError(
                f"Session {session_id} not found or already deleted"
            )
        session.deleted_at = datetime.now(timezone.utc)
        await self._session_repo.update(db, session)

    async def bulk_soft_delete_sessions(
        self, db: AsyncSession, session_ids: list[str], user_id: str
    ) -> tuple[list[str], list[str]]:
        """Bulk soft delete sessions.

        Returns:
            Tuple of (deleted_ids, failed_ids).
        """
        sessions = await self._session_repo.get_non_deleted_by_ids_and_user(
            db, session_ids, user_id
        )
        now = datetime.now(timezone.utc)
        deleted_ids: list[str] = []
        for session in sessions:
            session.deleted_at = now
            deleted_ids.append(str(session.id))
        await db.flush()

        found_ids = set(deleted_ids)
        failed_ids = [sid for sid in session_ids if sid not in found_ids]
        return deleted_ids, failed_ids

    async def set_session_public(
        self, db: AsyncSession, session_id: str, user_id: str, is_public: bool
    ) -> bool:
        """Set the public status of a session."""
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)
        if not session:
            return False
        session.is_public = is_public
        await self._session_repo.update(db, session)
        return True

    async def get_sessions_with_running_status(self, db: AsyncSession) -> List[Session]:
        """Get all sessions that have active running status."""
        running_session_ids = await self._agent_run_service.get_all_running_session_ids(db)
        if not running_session_ids:
            return []
        return await self._session_repo.get_non_deleted_by_ids(db, running_session_ids)

    async def get_session_running_status(self, db: AsyncSession, session_id: str):
        """Get the running status for a specific session."""
        return await self._agent_run_service.get_running_by_session(db, session_id)

    # ==================== Events ====================

    async def get_session_events_with_details(
        self, db: AsyncSession, session_id: str
    ) -> List[dict]:
        """Get all events for a session with signed URLs for file results."""
        ignored_events = [
            EventType.STATUS_UPDATE.value,
            EventType.SYSTEM.value,
            EventType.ERROR.value,
            EventType.PONG.value,
            EventType.CONNECTION_ESTABLISHED.value,
            EventType.WORKSPACE_INFO.value,
            EventType.AGENT_INITIALIZED.value,
            EventType.SANDBOX_STATUS.value,
        ]
        events = await self._event_repo.get_by_session_filtered(
            db, session_id, excluded_types=ignored_events
        )

        event_list = []
        for e in events:
            event_data = {
                "id": e.id,
                "session_id": e.session_id,
                "created_at": e.created_at.isoformat(),
                "type": e.type,
                "content": e.content,
                "workspace_dir": f"/workspace/{e.session_id}",
                "run_id": e.run_id,
            }

            # Generate signed URL for file_url type tool results
            if event_data["type"] == EventType.TOOL_RESULT:
                tool_result = event_data["content"].get("result", {})
                if (
                    isinstance(tool_result, dict)
                    and tool_result.get("type") == "file_url"
                ):
                    updated_content = deepcopy(event_data["content"])
                    tool_result = updated_content["result"]
                    tool_result["url"] = self._file_store.get_download_signed_url(
                        path=tool_result["file_storage_path"]
                    )
                    updated_content["result"] = tool_result
                    event_data["content"] = updated_content

            event_list.append(event_data)

        return event_list

    # ==================== Plan ====================

    async def update_session_plan(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
        summary: str,
        milestones: List[dict],
    ) -> None:
        """Update the session's stored plan (summary + milestones).

        Raises:
            SessionNotFoundError: If session not found or access denied.
        """
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)
        if not session:
            raise SessionNotFoundError(
                f"Session {session_id} not found or access denied"
            )

        plan_data = {"summary": summary, "milestones": milestones}
        for milestone in plan_data["milestones"]:
            if milestone.get("details") is None:
                milestone["details"] = ""
            if milestone.get("dependencies") is None:
                milestone["dependencies"] = []

        session.session_metadata = {
            **(session.session_metadata or {}),
            "plan": plan_data,
        }
        await self._session_repo.update(db, session)

        # Update or create the plan event
        plan_event_content = {
            "summary": plan_data["summary"],
            "milestones": plan_data["milestones"],
            "is_update": True,
        }
        existing_plan_event = await self._event_repo.get_latest_by_type(
            db, session_id, EventType.PLAN_GENERATED.value
        )
        if existing_plan_event:
            existing_plan_event.content = plan_event_content
            await db.flush()
        else:
            event = Event(
                session_id=session_id,
                type=EventType.PLAN_GENERATED.value,
                content=plan_event_content,
            )
            await self._event_repo.create(db, event)

    # ==================== High-level Business Logic ====================

    async def find_session_by_id_info(
        self, db: AsyncSession, session_uuid: uuid.UUID
    ) -> Optional[SessionInfo]:
        """Find session by ID and return SessionInfo."""
        session = await self.get_session_by_id(db, session_uuid)
        if session is None:
            return None
        return self._build_session_info(session)

    async def create_new_session(
        self,
        db: AsyncSession,
        session_uuid: uuid.UUID,
        user_id: str,
        api_version: str = "v0",
    ) -> SessionInfo:
        """Create a new session and return SessionInfo."""
        session = await self.create_session(
            db,
            session_uuid=session_uuid,
            user_id=user_id,
            api_version=api_version,
            agent_state_path=get_conversation_agent_state_path(str(session_uuid)),
        )
        return self._build_session_info(session, api_version=api_version)

    async def get_or_create_session(
        self,
        db: AsyncSession,
        session_uuid: Optional[str],
        user_id: str,
        api_version: str = "v0",
    ) -> SessionInfo:
        """Get existing session or create a new one."""
        if session_uuid:
            session = await self.find_session_by_id_info(db, uuid.UUID(session_uuid))
            if not session:
                raise SessionNotFoundError(f"Session {session_uuid} not found")
        else:
            session = await self.create_new_session(db, uuid.uuid4(), user_id, api_version)
        return session

    async def ensure_session_exists(
        self,
        db: AsyncSession,
        session_uuid: uuid.UUID,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """Ensure a database session exists for the given session ID."""
        existing_session = await self.get_session_by_id(db, session_uuid)
        if existing_session:
            logger.info(
                f"Found existing session {session_uuid} for user {existing_session.user_id}"
            )
            return existing_session.user_id
        else:
            if not user_id:
                from ii_agent.core.exceptions import ValidationError
                raise ValidationError("Cannot create session without authenticated user_id")

            await self.create_session(
                db,
                session_uuid=session_uuid,
                user_id=user_id,
                agent_state_path=get_conversation_agent_state_path(str(session_uuid)),
                name=None,
            )

            logger.info(f"Created new session {session_uuid} for user {user_id}")
            return user_id

    # ==================== Helpers ====================

    @staticmethod
    def _build_session_info(
        session: Session,
        *,
        project_id: Optional[str] = None,
        api_version: Optional[str] = None,
    ) -> SessionInfo:
        """Build a SessionInfo DTO from a Session model."""
        resolved_project_id = project_id
        if resolved_project_id is None:
            # Only access relationship if already loaded to avoid lazy load in async
            if "project" not in sa_inspect(session).unloaded:
                resolved_project_id = (
                    session.project.id if session.project else None
                )
        return SessionInfo(
            id=str(session.id),
            user_id=session.user_id,
            name=session.name,
            status=session.status,
            sandbox_id=session.sandbox_id,
            agent_type=session.agent_type,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            workspace_dir=session.get_workspace_dir(),
            is_public=session.is_public,
            token_usage=None,
            project_id=resolved_project_id,
            api_version=api_version or session.api_version,
        )

    @staticmethod
    def _session_to_dict(session: Session, include_project: bool = True) -> dict:
        """Convert a Session model to a dict representation."""
        data = {
            "id": str(session.id),
            "user_id": session.user_id,
            "name": session.name,
            "status": session.status,
            "sandbox_id": session.sandbox_id,
            "workspace_dir": f"/workspace/{session.id}",
            "is_public": session.is_public,
            "public_url": session.public_url,
            "token_usage": None,
            "settings": None,
            "agent_type": session.agent_type,
            "created_at": (
                session.created_at.isoformat() if session.created_at else None
            ),
            "updated_at": (
                session.updated_at.isoformat() if session.updated_at else None
            ),
            "last_message_at": (
                session.last_message_at.isoformat()
                if session.last_message_at
                else None
            ),
        }
        if include_project:
            # Only access relationship if already loaded to avoid lazy load in async
            if "project" not in sa_inspect(session).unloaded:
                data["project_id"] = session.project.id if session.project else None
            else:
                data["project_id"] = None
        return data
