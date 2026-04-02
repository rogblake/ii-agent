"""Sandbox management domain module.

Import pattern:
    from ii_agent.engine.sandboxes import SandboxManager, E2BSandboxManager
    from ii_agent.engine.sandboxes import SandboxStatus, SandboxInfo
    from ii_agent.engine.sandboxes.service import SandboxService
"""

from ii_agent.engine.sandboxes.schemas import (
    SandboxStatus,
    SandboxInfo,
    SandboxFileInfo,
    FileUpload,
    SandboxProvider,
)
from ii_agent.engine.sandboxes.base import SandboxManager
from ii_agent.engine.sandboxes.e2b import E2BSandboxManager
from ii_agent.engine.sandboxes.exceptions import (
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
