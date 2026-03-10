"""Session validation service for pre-execution checks."""

from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.service import CreditService
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.sessions.service import SessionService

if TYPE_CHECKING:
    from ii_agent.core.config.llm_config import LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class SessionValidationResult:
    """Result of ``SessionValidationService.validate_and_prepare_session``."""

    is_valid: bool
    session_info: SessionInfo | None = None
    llm_config: "LLMConfig | None" = None
    error_message: str | None = None
    error_type: str | None = None


class SessionValidationService:
    """Service for validating and preparing sessions for agent execution."""

    def __init__(
        self,
        *,
        session_service: SessionService,
        credit_service: CreditService,
    ) -> None:
        self._session_service = session_service
        self._credit_service = credit_service

    async def validate_and_prepare_session(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        *,
        query_text: str | None = None,
        agent_type: str | None = None,
        source: str | None = None,
        model_id: str | None = None,
        min_credits: float = 1.0,
        llm_setting_service,
        current_name: str | None = None,
    ) -> SessionValidationResult:
        """Validate a session and prepare it for agent execution.

        Performs all pre-execution checks:
        1. Verifies the session exists.
        2. Updates the session name from query text if not already set.
        3. Sets agent_type if not set.
        4. Resolves LLM configuration.
        5. Checks the user has sufficient credits.

        Cross-service dependencies (``llm_setting_service``) are passed as
        keyword arguments to avoid circular imports.

        Returns a :class:`SessionValidationResult` with ``is_valid=True``
        on success, or ``is_valid=False`` with error details on failure.
        """
        session = await self._session_service.get_session_by_id(db, session_id=session_id)
        if not session:
            return SessionValidationResult(
                is_valid=False,
                error_message="Session not found!",
                error_type="unexpected_error",
            )

        # Update session name if needed
        if not current_name and query_text:
            session.name = query_text.strip()[:100]
        if session.agent_type is None and agent_type:
            session.agent_type = agent_type

        # Resolve LLM settings
        session_info = SessionService._build_session_info(session)

        llm_config = await llm_setting_service.get_llm_settings(
            db,
            session=session_info,
            source=source,
            model_id=str(model_id) if model_id else None,
        )

        if not session.llm_setting_id:
            session.llm_setting_id = llm_config.setting_id

        # Update updated_at to ensure session appears at top of list
        session.updated_at = datetime.now(timezone.utc)

        # Check credits
        if llm_config.is_user_model():
            has_credits = True
        else:
            has_credits = await self._credit_service.has_sufficient(
                db, str(session.user_id), min_credits
            )

        db.add(session)
        await db.flush()
        await db.refresh(session)

        # Rebuild session_info after flush
        updated_session_info = SessionService._build_session_info(session)

        if not has_credits:
            return SessionValidationResult(
                is_valid=False,
                session_info=updated_session_info,
                error_message="Insufficient credits. Please check your credit balance.",
                error_type="insufficient_credits",
            )

        return SessionValidationResult(
            is_valid=True,
            session_info=updated_session_info,
            llm_config=llm_config,
        )
