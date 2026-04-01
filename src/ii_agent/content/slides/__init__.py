"""Slides domain module."""

from .models import SlideContent, SlideVersion
from .repository import SlideContentRepository
from .schemas import (
    SlideContentCreate,
    SlideContentInfo,
    PresentationInfo,
)

__all__ = [
    # Models
    "SlideContent",
    "SlideVersion",
    # Repository
    "SlideContentRepository",
    # Schemas
    "SlideContentCreate",
    "SlideContentInfo",
    "PresentationInfo",
]
