"""Session validation service for pre-execution checks."""

from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.balance_models import BillingStatus
from ii_agent.billing.credits.balance_repository import CreditBalanceRepository
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.sessions.service import SessionService
from ii_agent.sessions.title_service import SessionTitleService

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
        balance_repo: CreditBalanceRepository | None = None,
        title_service: SessionTitleService,
    ) -> None:
        self._session_service = session_service
        self._balance_repo = balance_repo
        self._title_service = title_service

    async def validate_and_prepare_session(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        *,
        query_text: str | None = None,
        agent_type: str | None = None,
        source: str | None = None,
        model_id: str | None = None,
        llm_setting_service,
        current_name: str | None = None,
    ) -> SessionValidationResult:
        """Validate a session and prepare it for agent execution.

        Performs all pre-execution checks:
        1. Verifies the session exists.
        2. Updates the session name from query text if not already set.
        3. Sets agent_type if not set.
        4. Resolves LLM configuration.
        5. Checks billing status (runtime reservation is the real credit gate).

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

        title_pending = False

        # Update session name if needed
        if not current_name and query_text:
            session.name, title_pending = self._title_service.build_initial_title(
                query_text,
                80,
            )
            session.session_metadata = SessionTitleService.set_title_pending(
                getattr(session, "session_metadata", None),
                title_pending,
            )
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

        # Validation only checks account health; runtime reservation is the
        # single money gate for actual credit sufficiency.
        billing_blocked = False
        if not llm_config.is_user_model() and self._balance_repo is not None:
            billing_status = await self._balance_repo.get_billing_status(db, str(session.user_id))
            if billing_status is not None and billing_status != BillingStatus.OK:
                billing_blocked = True

        db.add(session)
        await db.flush()
        await db.refresh(session)
        await db.commit()

        if title_pending and not billing_blocked and query_text:
            self._title_service.schedule_title_update(
                str(session.id),
                query_text,
                user_id=str(session.user_id),
                app_kind=str(getattr(session, "app_kind", "agent") or "agent"),
            )

        await db.refresh(session)
        # Rebuild session_info after flush
        updated_session_info = SessionService._build_session_info(session)

        if billing_blocked:
            return SessionValidationResult(
                is_valid=False,
                session_info=updated_session_info,
                error_message="Billing reconciliation required. Please contact support.",
                error_type="billing_reconciliation_required",
            )

        return SessionValidationResult(
            is_valid=True,
            session_info=updated_session_info,
            llm_config=llm_config,
        )
