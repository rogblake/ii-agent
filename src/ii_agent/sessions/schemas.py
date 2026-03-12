"""Pydantic schemas (DTOs) for sessions domain."""

from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal


class SessionCreate(BaseModel):
    """Model for creating a new session."""

    name: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    sandbox_template: Optional[str] = "base"


class SessionUpdate(BaseModel):
    """Model for updating a session."""

    name: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(pending|active|pause)$")
    settings: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None


class SessionInfo(BaseModel):
    """Model for session information."""

    id: UUID
    user_id: str
    api_version: Optional[str] = None
    name: Optional[str] = None
    status: str
    sandbox_id: Optional[str] = None
    workspace_dir: str
    is_public: bool
    public_url: Optional[str] = None
    token_usage: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None
    project_id: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    last_message_at: Optional[str] = None
    agent_type: Optional[str] = None
    app_kind: str = "agent"
    title_pending: bool = False


class SessionList(BaseModel):
    """Model for session list response."""

    sessions: List[SessionInfo]
    total: int
    page: int
    per_page: int


class SessionStats(BaseModel):
    """Model for session statistics."""

    total_sessions: int
    active_sessions: int
    paused_sessions: int
    sessions_today: int
    sessions_this_week: int
    sessions_this_month: int
    total_messages: int
    average_session_duration: Optional[float] = None


class TokenUsage(BaseModel):
    """Model for token usage tracking."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: Optional[str] = None


class SessionPlan(BaseModel):
    """Model for session execution plan."""

    id: str
    title: str
    description: str
    steps: List[Dict[str, Any]]
    status: str = "pending"  # pending, running, completed, failed
    created_at: str
    updated_at: Optional[str] = None


class SessionFile(BaseModel):
    """Model for session file."""

    id: str
    name: str
    size: int
    content_type: str
    url: str


class SessionMilestoneUpdate(BaseModel):
    """Model for updating milestones in a session plan."""

    id: str
    content: str
    status: Literal["pending", "in_progress", "completed"] = "pending"
    details: Optional[str] = None
    dependencies: Optional[List[str]] = None


class SessionPlanUpdate(BaseModel):
    """Model for updating a session plan."""

    summary: str = ""
    milestones: List[SessionMilestoneUpdate] = []


# ==================== Bulk Delete ====================


class BulkDeleteRequest(BaseModel):
    """Request for bulk deleting sessions."""

    session_ids: List[str] = Field(..., min_length=1, max_length=50)


class BulkDeleteResponse(BaseModel):
    """Response for bulk delete."""

    deleted_ids: List[str]
    failed_ids: List[str]


# ==================== Fork ====================


class ForkType(str, Enum):
    """Fork type - defines source → target transformation."""

    RESEARCH_TO_WEBSITE = "research_to_website"


class SandboxMode(str, Enum):
    """How to handle sandbox for forked session."""

    SHARE = "share"
    NEW = "new"


class ForkContext(BaseModel):
    """Context from parent session (from send_user_files tool output)."""

    attachments: List[str] = Field(..., min_length=1)
    additional_instruction: Optional[str] = None


class ForkSessionRequest(BaseModel):
    """Request for POST /sessions/{session_id}/fork."""

    fork_type: ForkType
    sandbox_mode: SandboxMode = SandboxMode.SHARE
    context: ForkContext
    llm_setting_id: Optional[str] = None


class ForkSessionResponse(BaseModel):
    """Response for fork endpoint."""

    session_id: str
    parent_session_id: str
    name: str
    agent_type: str
    sandbox_id: Optional[str] = None
    sandbox_mode: SandboxMode
    llm_setting_id: Optional[str] = None


# ==================== Fork Validation ====================

FORK_TYPE_TARGET_AGENT: Dict[ForkType, str] = {
    ForkType.RESEARCH_TO_WEBSITE: "research_to_website",
}

FORK_TYPE_VALID_SOURCES: Dict[ForkType, List[str]] = {
    ForkType.RESEARCH_TO_WEBSITE: ["deep_research", "fast_research"],
}


def get_target_agent_type(fork_type: ForkType) -> str:
    """Get the target agent type for a fork type."""
    return FORK_TYPE_TARGET_AGENT[fork_type]


def validate_fork_source(fork_type: ForkType, source_agent_type: Optional[str]) -> bool:
    """Validate that fork_type is valid for the source session's agent_type."""
    if source_agent_type is None:
        return False
    return source_agent_type in FORK_TYPE_VALID_SOURCES.get(fork_type, [])
