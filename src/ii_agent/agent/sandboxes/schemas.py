"""Pydantic schemas (DTOs) for sandboxes domain."""

from datetime import datetime
from enum import Enum
from typing import IO, Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict


class SandboxStatus(str, Enum):
    """Sandbox lifecycle status values."""

    NOT_INITIALIZED = "not_initialized"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    DELETED = "deleted"
    ERROR = "error"


class FileUpload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: str
    content: str | bytes | IO


class SandboxInfo(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat() if v else None})

    id: str
    provider: str
    session_id: str
    status: SandboxStatus
    vscode_url: Optional[str] = None
    expired_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True, mode="json")


class SandboxFileInfo(BaseModel):
    """Information about a written file in the sandbox."""

    name: str
    type: Literal["file", "dir"]
    path: str


SandboxProvider = Literal["e2b", "docker"]
