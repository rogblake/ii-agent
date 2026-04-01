"""Authentication and authorization domain module."""

from ii_agent.auth.dependencies import CurrentUser, DBSession, SettingsDep, get_current_user
from ii_agent.auth.exceptions import (
    AuthException,
    InvalidCredentialsException,
    InvalidTokenException,
    OIDCConfigError,
    TokenExpiredException,
    UserAlreadyExistsException,
    UserNotFoundException,
)
from ii_agent.auth.jwt_handler import JWTHandler, jwt_handler
from ii_agent.auth.oidc_verify import verify_at_hash_if_present, verify_id_token_pyjwt
from ii_agent.auth.schemas import TokenPayload, TokenResponse
from ii_agent.auth.utils import generate_api_key, generate_prefixed_api_key

__all__ = [
    # JWT
    "jwt_handler",
    "JWTHandler",
    # API Key utilities
    "generate_api_key",
    "generate_prefixed_api_key",
    # OIDC
    "verify_id_token_pyjwt",
    "verify_at_hash_if_present",
    "OIDCConfigError",
    # Schemas
    "TokenResponse",
    "TokenPayload",
    # Exceptions
    "AuthException",
    "InvalidCredentialsException",
    "InvalidTokenException",
    "TokenExpiredException",
    "UserNotFoundException",
    "UserAlreadyExistsException",
    # Dependencies
    "CurrentUser",
    "DBSession",
    "SettingsDep",
    "get_current_user",
]


def __getattr__(name: str):
    """Lazy imports for router."""
    if name == "router":
        from ii_agent.auth.router import router

        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
