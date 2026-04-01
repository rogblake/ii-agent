"""FastAPI dependencies for auth domain.

This module provides authentication-related dependencies that are used
across all domains that need user authentication.
"""

from typing import Annotated, TypeAlias

from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.dependencies import DBSession
from ii_agent.core.dependencies import SettingsDep
from ii_agent.users.dependencies import UserRepositoryDep
from ii_agent.users.models import User
from ii_agent.auth.jwt_handler import jwt_handler
from ii_agent.auth.schemas import TokenPayload
from ii_agent.auth.exceptions import InvalidTokenException, UserNotFoundException
from ii_agent.users.exceptions import UserDisabledException

# Re-export security scheme for use in routers
security = HTTPBearer()


async def get_current_user(
    db: DBSession,
    user_repo: UserRepositoryDep,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get the current authenticated user from JWT token.

    This dependency validates the JWT token and retrieves the user
    from the database.

    Usage:
        @router.get("/me")
        async def get_me(current_user: CurrentUser):
            return current_user
    """
    token = credentials.credentials

    # Verify the access token
    payload = jwt_handler.verify_access_token(token)
    if not payload:
        raise InvalidTokenException("Invalid or expired token")

    token_data = TokenPayload(**payload)

    # Get user from database
    user = await user_repo.get_by_id(db, token_data.user_id)

    if not user:
        raise UserNotFoundException("User not found")

    if not user.is_active:
        raise UserDisabledException("User account is disabled")

    return user


# Type alias for current user dependency
CurrentUser: TypeAlias = Annotated[User, Depends(get_current_user)]


__all__ = [
    "get_current_user",
    "CurrentUser",
    "DBSession",
    "SettingsDep",
    "security",
]
