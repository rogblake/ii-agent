"""Sandbox management domain module.

Import pattern:
    from ii_agent.agent.sandboxes import SandboxManager, E2BSandboxManager
    from ii_agent.agent.sandboxes import SandboxStatus, SandboxInfo
    from ii_agent.agent.sandboxes.service import SandboxService
"""

from ii_agent.agent.sandboxes.schemas import (
    SandboxStatus,
    SandboxInfo,
    SandboxFileInfo,
    FileUpload,
    SandboxProvider,
)
from ii_agent.agent.sandboxes.base import SandboxManager
from ii_agent.agent.sandboxes.e2b import E2BSandboxManager
from ii_agent.agent.sandboxes.exceptions import (
    SandboxException,
    SandboxAuthenticationError,
    SandboxCreationError,
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxOperationError,
    SandboxTimeoutException,
)

__all__ = [
    # Schemas
    "SandboxStatus",
    "SandboxInfo",
    "SandboxFileInfo",
    "FileUpload",
    "SandboxProvider",
    # Base classes
    "SandboxManager",
    # Provider implementations
    "E2BSandboxManager",
    # Exceptions
    "SandboxException",
    "SandboxAuthenticationError",
    "SandboxCreationError",
    "SandboxNotFoundException",
    "SandboxNotInitializedError",
    "SandboxOperationError",
    "SandboxTimeoutException",
]
