"""Pydantic schemas (DTOs) for projects domain."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class SessionProjectResponse(BaseModel):
    """Response payload for a session's project metadata."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    user_id: UUID
    session_id: Optional[UUID]
    name: Optional[str]
    description: Optional[str]
    status: str
    current_build_status: str
    framework: Optional[str]
    project_path: Optional[str]
    production_url: Optional[str]
    database: Optional[Dict[str, Any]] = Field(default=None, validation_alias="database_json")
    storage: Optional[Dict[str, Any]] = Field(default=None, validation_alias="storage_json")
    secrets: Optional[Dict[str, Any]] = Field(default=None, validation_alias="secrets_json")
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    @field_validator("secrets", mode="before")
    @classmethod
    def decrypt_secrets(cls, v: Any) -> Optional[Dict[str, Any]]:
        from ii_agent.projects.secrets.utils import _decrypt_secrets_payload

        return _decrypt_secrets_payload(v)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def project_name(self) -> Optional[str]:
        return self.name
