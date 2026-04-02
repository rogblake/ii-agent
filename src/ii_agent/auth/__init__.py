"""Authentication and authorization domain module.

Import pattern:
    from ii_agent.auth import (
        jwt_handler,
        JWTHandler,
        TokenResponse,
        TokenPayload,
        CurrentUser,
        DBSession,
        router,
    )
"""

from ii_agent.auth.jwt_handler import jwt_handler, JWTHandler
from ii_agent.auth.api_key_utils import generate_api_key, generate_prefixed_api_key
from ii_agent.auth.oidc_verify import (
    verify_id_token_pyjwt,
    verify_at_hash_if_present,
)
from ii_agent.auth.exceptions import OIDCConfigError
from ii_agent.auth.schemas import TokenResponse, TokenPayload
from ii_agent.auth.models import WaitlistEntry
from ii_agent.auth.dependencies import CurrentUser, DBSession, get_current_user
from ii_agent.auth.router import router

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
    # Models
    "WaitlistEntry",
    # Dependencies
    "CurrentUser",
    "DBSession",
    "get_current_user",
    # Router
    "router",
]
