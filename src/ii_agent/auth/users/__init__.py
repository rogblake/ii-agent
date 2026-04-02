"""User management and profiles domain module."""

from ii_agent.auth.users.models import User, APIKey  # noqa: F401
from ii_agent.auth.users.repository import UserRepository, APIKeyRepository  # noqa: F401

# Note: UserService and router are NOT imported here to avoid circular imports
# with ii_agent.auth. Import them directly:
#   from ii_agent.auth.users.service import UserService
#   from ii_agent.auth.users.dependencies import UserServiceDep
#   from ii_agent.auth.users.router import router

__all__ = [
    "User",
    "APIKey",
    "UserRepository",
    "APIKeyRepository",
]
