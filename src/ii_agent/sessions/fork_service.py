"""Session fork service for creating forked sessions."""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.sessions.exceptions import SessionNotFoundError, SessionValidationError
from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository
from ii_agent.core.config.settings import Settings
from ii_agent.core.storage.locations import get_conversation_agent_state_path

logger = logging.getLogger(__name__)


class SessionForkService:
    """Service for forking sessions to create child sessions with inherited context."""

    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        sandbox_repo,
        config: Settings,
    ) -> None:
        self._session_repo = session_repo
        self._sandbox_repo = sandbox_repo
        self._config = config

    async def fork_session(
        self,
        db: AsyncSession,
        parent_session_id: str,
        user_id: str,
        request: "ForkSessionRequest",
    ) -> "ForkSessionResponse":
        """Fork a session to create a new session with inherited context.

        Validates parent ownership, fork type against parent's agent_type,
        resolves sandbox sharing, inherits LLM settings, then creates the
        child session with fork metadata.

        Raises:
            SessionNotFoundError: If parent session not found or access denied.
            SessionValidationError: If fork type is invalid for the parent's agent_type.
        """
        from ii_agent.sessions.schemas import (
            ForkSessionRequest,
            ForkSessionResponse,
            SandboxMode,
            FORK_TYPE_VALID_SOURCES,
            get_target_agent_type,
            validate_fork_source,
        )

        # 1. Get and validate parent session
        parent = await self._session_repo.get_by_id_and_user(
            db, parent_session_id, user_id
        )
        if not parent:
            raise SessionNotFoundError(
                f"Parent session {parent_session_id} not found or access denied"
            )

        # 2. Validate fork type against parent's agent_type
        parent_agent_type = parent.agent_type
        if not validate_fork_source(request.fork_type, parent_agent_type):
            valid_sources = FORK_TYPE_VALID_SOURCES.get(request.fork_type, [])
            raise SessionValidationError(
                f"Cannot fork '{request.fork_type.value}' from agent_type "
                f"'{parent_agent_type}'. Valid sources: {valid_sources}"
            )

        # 3. Determine target agent type
        target_agent_type = get_target_agent_type(request.fork_type)

        # 4. Handle sandbox mode
        sandbox_id: Optional[str] = None
        if request.sandbox_mode == SandboxMode.SHARE:
            sandbox = await self._sandbox_repo.get_by_session_id(
                db, parent_session_id
            )
            if sandbox:
                sandbox_id = str(sandbox.id)

        # 5. Inherit LLM settings if not provided
        llm_setting_id = request.llm_setting_id
        if llm_setting_id is None and parent.llm_setting_id:
            llm_setting_id = str(parent.llm_setting_id)

        # 6. Build fork metadata and create session
        new_session_uuid = uuid.uuid4()
        parent_name = parent.name or "Untitled"
        new_name = f"Continue from: {parent_name}"
        session_metadata = {
            "fork_info": {
                "fork_type": request.fork_type.value,
                "parent_session_id": parent_session_id,
                "parent_agent_type": parent_agent_type,
                "context": {
                    "attachments": request.context.attachments,
                    "additional_instruction": request.context.additional_instruction,
                },
                "forked_at": datetime.now(timezone.utc).isoformat(),
            }
        }

        new_session = Session(
            id=str(new_session_uuid),
            user_id=user_id,
            name=new_name,
            status="active",
            agent_type=target_agent_type,
            parent_session_id=parent_session_id,
            sandbox_id=sandbox_id,
            llm_setting_id=llm_setting_id,
            session_metadata=session_metadata,
            api_version="v1",
            agent_state_path=get_conversation_agent_state_path(str(new_session_uuid)),
        )
        await self._session_repo.create(db, new_session)

        logger.info(
            f"Created forked session {new_session.id} from parent {parent_session_id} "
            f"with fork_type={request.fork_type.value}, agent_type={target_agent_type}"
        )

        return ForkSessionResponse(
            session_id=str(new_session.id),
            parent_session_id=parent_session_id,
            name=new_name,
            agent_type=target_agent_type,
            sandbox_id=sandbox_id,
            sandbox_mode=request.sandbox_mode,
            llm_setting_id=llm_setting_id,
        )
