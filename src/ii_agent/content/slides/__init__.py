"""Slides domain module."""

from .models import SlideContent, SlideVersion
from .schemas import (
    SlideContentCreate,
    SlideContentInfo,
    PresentationInfo,
)
from .router import router
from .templates.router import router as template_router

__all__ = [
    # Models
    "SlideContent",
    "SlideVersion",
    # Schemas
    "SlideContentCreate",
    "SlideContentInfo",
    "PresentationInfo",
    # Routers
    "router",
    "template_router",
]
