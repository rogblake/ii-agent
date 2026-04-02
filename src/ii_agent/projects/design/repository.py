"""Repository layer for project design domain - data access only."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository


class ProjectDesignRepository:
    """Data access facade for project design workflows.

    This repository composes existing session repository so project design
    service logic does not perform direct ORM queries.
    """

    def __init__(
        self,
        *,
        session_repo: SessionRepository,
    ) -> None:
        self._session_repo = session_repo

    async def get_session_for_user(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        user_id: str,
    ) -> Optional[Session]:
        return await self._session_repo.get_by_id_and_user(db, session_id, user_id)

    async def get_session(
        self,
        db: AsyncSession,
        *,
        session_id: str,
    ) -> Optional[Session]:
        return await self._session_repo.get_by_id(db, session_id)

    @staticmethod
    def get_design_state(session: Session) -> tuple[list[Any], list[Any], Optional[int]]:
        metadata = session.session_metadata or {}
        design_mode = metadata.get("design_mode") if isinstance(metadata, dict) else None
        if not isinstance(design_mode, dict):
            return [], [], None
        raw_changes = (
            design_mode.get("changes") if isinstance(design_mode.get("changes"), list) else []
        )
        raw_redo = (
            design_mode.get("redo_changes")
            if isinstance(design_mode.get("redo_changes"), list)
            else []
        )
        updated_at = design_mode.get("updated_at")
        return raw_changes, raw_redo, updated_at

    async def update_design_state(
        self,
        db: AsyncSession,
        *,
        session: Session,
        changes: Iterable[dict[str, Any]],
        redo_changes: Iterable[dict[str, Any]],
        updated_at: int,
    ) -> None:
        metadata = dict(session.session_metadata or {})
        metadata["design_mode"] = {
            "changes": list(changes),
            "redo_changes": list(redo_changes),
            "updated_at": updated_at,
        }
        session.session_metadata = metadata
        await db.flush()
