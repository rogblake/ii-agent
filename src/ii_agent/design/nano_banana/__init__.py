"""Nano Banana design mode sub-domain.

Vision-based slide editing that uses AI to detect components in slide images
and regenerate slides with user-specified modifications.
"""

from .router import router as nano_banana_router
from .schemas import (
    DetectRequest,
    DetectResponse,
    DetectedComponent,
    RegenerateRequest,
    RegenerateResponse,
    RemoveBackgroundRequest,
    RemoveBackgroundResponse,
    GetVersionsResponse,
    RevertRequest,
    RevertResponse,
)

__all__ = [
    "nano_banana_router",
    "DetectRequest",
    "DetectResponse",
    "DetectedComponent",
    "RegenerateRequest",
    "RegenerateResponse",
    "RemoveBackgroundRequest",
    "RemoveBackgroundResponse",
    "GetVersionsResponse",
    "RevertRequest",
    "RevertResponse",
]
