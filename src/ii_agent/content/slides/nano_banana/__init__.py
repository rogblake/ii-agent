"""Nano Banana design mode sub-domain.

Vision-based slide editing that uses AI to detect components in slide images
and regenerate slides with user-specified modifications.
"""

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
