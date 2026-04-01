"""User management and profiles domain module."""

from ii_agent.users.models import User, APIKey  # noqa: F401
from ii_agent.users.repository import UserRepository, APIKeyRepository  # noqa: F401

# Note: UserService and router are NOT imported here to avoid circular imports
# with ii_agent.auth. Import them directly:
#   from ii_agent.users.service import UserService
#   from ii_agent.users.dependencies import UserServiceDep
#   from ii_agent.users.router import router

__all__ = [
    "User",
    "APIKey",
    "UserRepository",
    "APIKeyRepository",
]
