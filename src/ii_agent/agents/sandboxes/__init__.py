"""Sandbox module for agent system.

Provides sandbox management for isolated code execution environments.

Key components:
- Sandbox: Abstract interface for sandbox providers
- SandboxService: Orchestrates DB persistence + provider lifecycle
- E2BSandbox: E2B cloud sandbox provider implementation
"""

from ii_agent.agents.sandboxes.base import Sandbox
from ii_agent.agents.sandboxes.dependencies import SandboxRepositoryDep, SandboxServiceDep
from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox
from ii_agent.agents.sandboxes.e2b import E2BSandbox
from ii_agent.agents.sandboxes.exceptions import (
    SandboxAuthenticationError,
    SandboxCreationError,
    SandboxException,
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxOperationError,
    SandboxTimeoutException,
)
from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.repository import SandboxRepository
from ii_agent.agents.sandboxes.router import router as sandbox_router
from ii_agent.agents.sandboxes.schemas import FileUpload, SandboxFileInfo, SandboxInfo
from ii_agent.agents.sandboxes.service import SandboxService
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus

# Backward-compat aliases — exposed here so callers can migrate gradually
SandboxManager = Sandbox
E2BSandboxManager = E2BSandbox

__all__ = [
    # Interface
    "Sandbox",
    # Dependencies
    "SandboxRepositoryDep",
    "SandboxServiceDep",
    # Router
    "sandbox_router",
    # Service
    "SandboxService",
    # Provider implementations
    "E2BSandbox",
    # ORM
    "AgentSandbox",
    # Repository
    "SandboxRepository",
    # Schemas
    "SandboxInfo",
    "SandboxFileInfo",
    "FileUpload",
    # Types
    "SandboxStatus",
    "SandboxProviderType",
    # Exceptions
    "SandboxException",
    "SandboxAuthenticationError",
    "SandboxCreationError",
    "SandboxNotFoundException",
    "SandboxNotInitializedError",
    "SandboxOperationError",
    "SandboxTimeoutException",
    # Utilities
    "upload_media_to_sandbox",
    # Backward-compat aliases
    "SandboxManager",
    "E2BSandboxManager",
]
