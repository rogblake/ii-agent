from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.repository import BaseRepository
from ii_agent.projects.deployments.models import ProjectDeployment


class DeploymentsRepository(BaseRepository[ProjectDeployment]):

    model = ProjectDeployment

    async def get_latest_deployment(
        self, db: AsyncSession, project_id: str, provider: Optional[str] = None
    ) -> Optional[ProjectDeployment]:
        query = select(ProjectDeployment).where(ProjectDeployment.project_id == project_id)
        if provider:
            query = query.where(ProjectDeployment.provider == provider)

        query = query.order_by(desc(ProjectDeployment.version)).limit(1)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_max_version(self, db: AsyncSession, project_id: str) -> int:
        result = await db.execute(
            select(func.coalesce(func.max(ProjectDeployment.version), 0)).where(
                ProjectDeployment.project_id == project_id
            )
        )
        return result.scalar_one()
