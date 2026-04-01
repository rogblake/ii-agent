"""Session lifecycle management domain module."""

from ii_agent.sessions.exceptions import SessionNotFoundError, SessionValidationError
from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.schemas import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    ForkContext,
    ForkSessionRequest,
    ForkSessionResponse,
    ForkType,
    SandboxMode,
    SessionCreate,
    SessionFile,
    SessionInfo,
    SessionMilestoneUpdate,
    SessionPlan,
    SessionPlanUpdate,
    SessionResponse,
    SessionStats,
    SessionUpdate,
    ValidatedSessionResult,
)
from ii_agent.sessions.service import SessionService
from ii_agent.sessions.fork_service import SessionForkService
from ii_agent.sessions.title_service import SessionTitleService
from ii_agent.sessions.types import AppKind, SessionState

__all__ = [
    # Exceptions
    "SessionNotFoundError",
    "SessionValidationError",
    # Models
    "Session",
    # Repository
    "SessionRepository",
    # Services
    "SessionService",
    "SessionForkService",
    "SessionTitleService",
    # Schemas
    "BulkDeleteRequest",
    "BulkDeleteResponse",
    "ForkContext",
    "ForkSessionRequest",
    "ForkSessionResponse",
    "ForkType",
    "SandboxMode",
    "SessionCreate",
    "SessionFile",
    "SessionInfo",
    "SessionMilestoneUpdate",
    "SessionPlan",
    "SessionPlanUpdate",
    "SessionResponse",
    "SessionStats",
    "SessionUpdate",
    "ValidatedSessionResult",
    # Types
    "AppKind",
    "SessionState",
]
