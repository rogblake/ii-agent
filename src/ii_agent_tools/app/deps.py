"""FastAPI dependency factories for settings, clients, and auth."""

import asyncio
from functools import wraps
from typing import TypeVar, Callable, Awaitable

import jwt
from fastapi import HTTPException, Request
from fastapi.params import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ValidationError

from ii_agent_tools.app.app_config import Settings, get_settings
from ii_agent_tools.integrations.audio_generation import AudioGenerationService
from ii_agent_tools.integrations.image_generation.service import ImageGenerationService
from ii_agent_tools.integrations.image_search import ImageSearchService
from ii_agent_tools.integrations.web_visit import WebVisitService
from ii_agent_tools.integrations.video_generation import VideoGenerationService
from ii_agent_tools.integrations.voice_generation import VoiceGenerationService
from ii_agent_tools.integrations.web_search import WebSearchService
from ii_agent_tools.logger import get_logger
from ii_agent_tools.storage import BaseStorage, create_storage_client
from ii_agent_tools.llm import LLMClient

T = TypeVar("T")


def async_lru_cache(
    func: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    """
    Async-aware LRU cache decorator for singleton pattern.

    Uses asyncio.Lock for thread-safe initialization in async context.
    Implements double-checked locking to prevent race conditions.
    """
    cache: dict[tuple, T] = {}
    lock = asyncio.Lock()

    @wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        key = (args, tuple(sorted(kwargs.items())))
        if key not in cache:
            async with lock:
                # Double-check after acquiring lock
                if key not in cache:
                    cache[key] = await func(*args, **kwargs)
        return cache[key]

    def cache_clear() -> None:
        cache.clear()

    wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
    return wrapper


logger = get_logger(__name__)

security = HTTPBearer(auto_error=False)


class JWTPayload(BaseModel):
    """Validated JWT payload structure."""

    sub: str  # Subject (user ID)
    exp: int  # Expiration timestamp
    iat: int  # Issued at timestamp
    roles: list[str] = []  # User roles/permissions


def get_settings_dep() -> Settings:
    """Expose cached settings to FastAPI."""
    return get_settings()


async def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> JWTPayload:
    """
    Verify JWT token and validate payload structure.

    Includes audit logging for authentication events.

    Args:
        request: FastAPI request object for logging context
        credentials: HTTP Bearer token credentials

    Returns:
        Validated JWT payload

    Raises:
        HTTPException: If authentication fails
    """
    settings = get_settings()

    if credentials is None or credentials.scheme.lower() != "bearer":
        logger.warning(
            "Authentication failed: missing or invalid authorization header",
            extra={
                "client_host": request.client.host if request.client else None,
                "path": request.url.path,
            },
        )
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    try:
        token = credentials.credentials
        payload_dict = jwt.decode(token, settings.auth_secret_key, algorithms=["HS256"])

        # Validate payload structure
        payload = JWTPayload(**payload_dict)

        # Audit log successful authentication
        logger.info(
            "Authentication successful",
            extra={
                "user_id": payload.sub,
                "roles": payload.roles,
                "client_host": request.client.host if request.client else None,
            },
        )

        return payload

    except jwt.ExpiredSignatureError:
        logger.warning(
            "Authentication failed: token expired",
            extra={
                "client_host": request.client.host if request.client else None,
                "path": request.url.path,
            },
        )
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        logger.warning(
            "Authentication failed: invalid token",
            extra={
                "reason": str(e),
                "client_host": request.client.host if request.client else None,
                "path": request.url.path,
            },
        )
        raise HTTPException(status_code=401, detail="Invalid token")
    except ValidationError as e:
        logger.warning(
            "Authentication failed: invalid token payload structure",
            extra={
                "errors": e.errors(),
                "client_host": request.client.host if request.client else None,
                "path": request.url.path,
            },
        )
        raise HTTPException(status_code=401, detail="Invalid token payload")
    except ValueError:
        logger.warning(
            "Authentication failed: invalid authorization header format",
            extra={
                "client_host": request.client.host if request.client else None,
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=401, detail="Invalid authorization header format"
        )


@async_lru_cache
async def get_storage() -> BaseStorage:
    return create_storage_client(get_settings().storage_config)


@async_lru_cache
async def get_llm_client() -> LLMClient | None:
    llm_config = get_settings().llm_config
    if llm_config and llm_config.openai_api_key:
        return LLMClient(llm_config)
    return None


@async_lru_cache
async def get_image_search_service() -> ImageSearchService:
    return ImageSearchService(get_settings().image_search_config, await get_storage())


@async_lru_cache
async def get_audio_generation_service() -> AudioGenerationService:
    return AudioGenerationService(get_settings().audio_generate_config)


@async_lru_cache
async def get_web_visit_service() -> WebVisitService:
    return WebVisitService(await get_llm_client(), get_settings().web_visit_config)


@async_lru_cache
async def get_video_generation_service() -> VideoGenerationService:
    return VideoGenerationService(
        get_settings().video_generate_config,
        await get_llm_client(),
        await get_storage(),
    )


@async_lru_cache
async def get_voice_generation_service() -> VoiceGenerationService:
    return VoiceGenerationService(get_settings().voice_generate_config)


@async_lru_cache
async def get_web_search_service() -> WebSearchService:
    return WebSearchService(get_settings().web_search_config)


@async_lru_cache
async def get_image_generation_service() -> ImageGenerationService:
    return ImageGenerationService(get_settings().image_generate_config)


__all__ = [
    "get_settings_dep",
    "verify_api_key",
    "get_storage",
    "get_llm_client",
    "get_image_search_service",
    "get_audio_generation_service",
    "get_web_visit_service",
    "get_video_generation_service",
    "get_voice_generation_service",
    "get_web_search_service",
    "get_image_generation_service",
]
