from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime


class ProjectSecretsRequest(BaseModel):
    """Payload for replacing secrets on a project."""

    secrets: Dict[str, Any]


class ProjectSecretsResponse(BaseModel):
    """Response containing decrypted secrets for a project session."""

    project_id: str
    session_id: str
    secrets: Dict[str, Any]
    updated_at: Optional[datetime]
