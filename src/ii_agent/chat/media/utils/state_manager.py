"""Utility for managing advanced mode state persistence."""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.sessions.models import Session
from ii_agent.chat.schemas import MediaReference, AdvancedModeState
from .reference_resolver import ReferenceResolver


class AdvancedModeStateManager:
    """Handles persistence of advanced mode state to session metadata."""

    @staticmethod
    async def get_state(
        db_session: AsyncSession,
        session_id: str,
    ) -> AdvancedModeState:
        """
        Fetch persisted advanced mode state for a session.

        Args:
            db_session: Database session
            session_id: Session ID

        Returns:
            AdvancedModeState with enabled flag and references
        """
        # Fetch session metadata
        result = await db_session.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError("Session not found")

        # Get advanced_mode from session metadata
        session_metadata = session.session_metadata or {}
        advanced_mode_data = session_metadata.get("advanced_mode") or {}
        enabled = bool(advanced_mode_data.get("enabled", False))
        raw_refs = advanced_mode_data.get("references") or []

        references = await ReferenceResolver.resolve_references(
            db_session=db_session, references=raw_refs
        )

        return AdvancedModeState(
            enabled=enabled, references=references
        )

    @staticmethod
    async def update_state(
        db_session: AsyncSession,
        session_id: str,
        enabled: bool,
        references: list[MediaReference] | None,
    ) -> AdvancedModeState:
        """
        Persist advanced mode enablement and references for a session.

        Args:
            db_session: Database session
            session_id: Session ID
            enabled: Whether advanced mode is enabled
            references: List of MediaReference objects

        Returns:
            Updated AdvancedModeState
        """
        serialized_refs = (
            [ref.model_dump(exclude_none=True) for ref in references]
            if references
            else []
        )

        # Fetch session
        result = await db_session.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError("Session not found")

        # Update session metadata with advanced_mode settings
        session_metadata = session.session_metadata or {}
        session_metadata["advanced_mode"] = {
            "enabled": enabled,
            "references": serialized_refs,
        }

        # Update session
        await db_session.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(
                session_metadata=session_metadata,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db_session.commit()

        # Resolve references directly without re-fetching the session
        resolved_references = await ReferenceResolver.resolve_references(
            db_session=db_session, references=serialized_refs
        )

        return AdvancedModeState(
            enabled=enabled,
            references=resolved_references,
        )
