from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel


class ProjectSecretsRequest(BaseModel):
    """Payload for adding or updating secrets on a project."""

    secrets: Dict[str, Any]


class ProjectSecretsResponse(BaseModel):
    """Response containing decrypted secrets for a project session."""

    project_id: UUID
    session_id: UUID
    secrets: Dict[str, Any]
    updated_at: Optional[datetime]
