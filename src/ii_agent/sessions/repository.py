"""Repository layer for sessions domain - data access only."""

import uuid
from typing import Any, Optional, List

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ii_agent.core.db.repository import BaseRepository
from ii_agent.sessions.models import Session


class SessionRepository(BaseRepository[Session]):
    """Data access layer for Session model."""

    model = Session

    # ==================== Basic CRUD ====================

    async def get_by_id(self, db: AsyncSession, entity_id: Any) -> Optional[Session]:
        """Get a session by its ID (accepts str or uuid.UUID)."""
        result = await db.execute(
            select(Session).where(Session.id == str(entity_id))
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_project(self, db: AsyncSession, session_id: str | uuid.UUID) -> Optional[Session]:
        """Get a session by ID with project eagerly loaded."""
        result = await db.execute(
            select(Session)
            .options(selectinload(Session.project))
            .where(Session.id == str(session_id))
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_user(
        self, db: AsyncSession, session_id: str, user_id: str
    ) -> Optional[Session]:
        """Get a non-deleted session for a specific user with project loaded."""
        result = await db.execute(
            select(Session)
            .options(selectinload(Session.project))
            .where(
                Session.id == session_id,
                Session.user_id == user_id,
                Session.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_workspace(self, db: AsyncSession, workspace_dir: str) -> Optional[Session]:
        """Get a session by its workspace directory."""
        result = await db.execute(
            select(Session).where(Session.workspace_dir == workspace_dir)
        )
        return result.scalar_one_or_none()

    async def get_public_by_id(self, db: AsyncSession, session_id: str) -> Optional[Session]:
        """Get a public, non-deleted session by ID."""
        result = await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.is_public,
                Session.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_user_id(self, db: AsyncSession, session_id: str | uuid.UUID) -> Optional[str]:
        """Get the user ID for a session."""
        session = await self.get_by_id(db, session_id)
        if not session:
            return None
        return str(session.user_id)

    # ==================== Query Operations ====================

    async def get_llm_setting_id(self, db: AsyncSession, session_id: str | uuid.UUID) -> Optional[str]:
        """Get the LLM setting ID for a session."""
        result = await db.execute(
            select(Session.llm_setting_id).where(Session.id == str(session_id))
        )
        return result.scalar_one_or_none()

    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: str,
        search_term: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        public_only: Optional[bool] = False,
        session_type: Optional[str] = None,
    ) -> tuple[List[Session], int]:
        """Get paginated sessions for a user with optional filters."""
        conditions = [Session.user_id == user_id, Session.deleted_at.is_(None)]

        if public_only:
            conditions.append(Session.is_public)
        if search_term:
            conditions.append(Session.name.ilike(f"%{search_term}%"))
        if session_type == "chat":
            conditions.append(Session.agent_type == "chat")
        elif session_type == "agent":
            conditions.append(Session.agent_type != "chat")

        count_query = select(func.count()).select_from(Session).where(*conditions)
        count_result = await db.execute(count_query)
        total = count_result.scalar()

        offset = (page - 1) * per_page
        data_query = (
            select(Session)
            .options(selectinload(Session.project))
            .where(*conditions)
            .order_by(desc(Session.created_at))
            .limit(per_page)
            .offset(offset)
        )

        result = await db.execute(data_query)
        sessions = list(result.scalars().all())

        return sessions, total

    async def get_non_deleted_by_ids_and_user(
        self, db: AsyncSession, session_ids: list[str], user_id: str
    ) -> list[Session]:
        """Get non-deleted sessions matching the given IDs for a specific user."""
        result = await db.execute(
            select(Session).where(
                Session.id.in_(session_ids),
                Session.user_id == user_id,
                Session.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get_non_deleted_by_ids(
        self, db: AsyncSession, session_ids: list[str]
    ) -> list[Session]:
        """Get non-deleted sessions matching the given IDs."""
        if not session_ids:
            return []
        result = await db.execute(
            select(Session).where(
                Session.id.in_(session_ids),
                Session.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get_sandbox_id(
        self, db: AsyncSession, session_id: str | uuid.UUID
    ) -> Optional[str]:
        """Get the sandbox ID for a session (scalar projection)."""
        result = await db.execute(
            select(Session.sandbox_id).where(Session.id == str(session_id))
        )
        return result.scalar_one_or_none()

