"""Session fork service for creating forked sessions."""

from __future__ import annotations

from copy import deepcopy
import uuid
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.repository import SandboxRepository
from pydantic import TypeAdapter
from sqlalchemy import exc as sa_exc
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.sessions.exceptions import SessionNotFoundError, SessionValidationError
from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.schemas import (
    ForkSessionResponse,
    FORK_TYPE_VALID_SOURCES,
    SandboxMode,
    get_target_agent_type,
    validate_fork_source,
)
from ii_agent.core.config.settings import Settings

if TYPE_CHECKING:
    from ii_agent.sessions.schemas import ForkSessionRequest

logger = logging.getLogger(__name__)

_SESSION_METADATA_ADAPTER = TypeAdapter(dict[str, object])


class SessionForkService:
    """Service for forking sessions to create child sessions with inherited context."""

    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        sandbox_repo: SandboxRepository,
        config: Settings,
    ) -> None:
        self._session_repo = session_repo
        self._sandbox_repo = sandbox_repo
        self._config = config

    async def fork_session(
        self,
        db: AsyncSession,
        parent_session_id: uuid.UUID,
        user_id: uuid.UUID,
        request: "ForkSessionRequest",
    ) -> ForkSessionResponse:
        """Fork a session to create a new session with inherited context.

        Validates parent ownership, fork type against parent's agent_type,
        resolves sandbox sharing, inherits LLM settings, then creates the
        child session with fork metadata.

        Raises:
            SessionNotFoundError: If parent session not found or access denied.
            SessionValidationError: If fork type is invalid for the parent's agent_type.
        """
        # 1. Get and validate parent session
        parent = await self._session_repo.get_by_id_and_user(db, parent_session_id, user_id)
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

        # 4. Inherit LLM settings if not provided
        model_setting_id = request.model_setting_id
        if model_setting_id is None and parent.model_setting_id:
            model_setting_id = parent.model_setting_id

        # 5. Resolve sandbox sharing
        shared_sandbox = None
        if request.sandbox_mode == SandboxMode.SHARE:
            shared_sandbox = await self._sandbox_repo.get_by_session_id(db, parent_session_id)

        # 6. Build fork metadata and create session
        new_session_uuid = uuid.uuid4()
        parent_name = parent.name or "Untitled"
        new_name = f"Continue from: {parent_name}"
        session_metadata = _SESSION_METADATA_ADAPTER.dump_python(
            {
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
            },
            mode="json",
        )

        new_session = Session(
            id=new_session_uuid,
            user_id=user_id,
            name=new_name,
            status="active",
            agent_type=target_agent_type,
            parent_session_id=parent_session_id,
            model_setting_id=model_setting_id,
            session_metadata=session_metadata,
            api_version="v1",
        )

        try:
            await self._session_repo.save(db, new_session)
        except sa_exc.IntegrityError as e:
            await db.rollback()
            constraint = str(e.orig) if e.orig else str(e)
            logger.warning(
                "Fork session integrity error for parent %s: %s",
                parent_session_id,
                constraint,
            )
            if "model_setting_id" in constraint or "model_settings" in constraint:
                raise SessionValidationError(
                    f"Invalid model_setting_id: {model_setting_id}"
                ) from e
            raise SessionValidationError(
                f"Failed to create forked session: {constraint}"
            ) from e

        if shared_sandbox is not None:
            try:
                await self._sandbox_repo.save(
                    db,
                    AgentSandbox(
                        session_id=new_session.id,
                        provider=shared_sandbox.provider,
                        provider_sandbox_id=shared_sandbox.provider_sandbox_id,
                        status=shared_sandbox.status,
                        expired_at=shared_sandbox.expired_at,
                        provider_data=deepcopy(shared_sandbox.provider_data),
                    ),
                )
            except sa_exc.IntegrityError:
                logger.warning(
                    "Failed to share sandbox from parent %s to forked session %s; "
                    "continuing without shared sandbox",
                    parent_session_id,
                    new_session.id,
                )

        logger.info(
            "Created forked session %s from parent %s with fork_type=%s, agent_type=%s",
            new_session.id,
            parent_session_id,
            request.fork_type.value,
            target_agent_type,
        )

        return ForkSessionResponse(
            session_id=new_session.id,
            parent_session_id=parent_session_id,
            name=new_name,
            agent_type=target_agent_type,
            sandbox_mode=request.sandbox_mode,
            model_setting_id=model_setting_id,
        )
