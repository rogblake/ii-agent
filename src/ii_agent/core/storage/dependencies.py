"""FastAPI dependencies for storage providers."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.storage.base import BaseStorage
from ii_agent.core.storage.client import storage, media_storage, slide_storage


async def get_storage() -> BaseStorage:
    """Dependency to get the file upload storage singleton (no custom domain)."""
    return storage


async def get_media_template_storage() -> BaseStorage:
    """Dependency to get the media storage singleton for media templates."""
    return media_storage


async def get_slide_storage() -> BaseStorage:
    """Dependency to get the slide storage singleton (with custom domain)."""
    return slide_storage


StorageDep = Annotated[BaseStorage, Depends(get_storage)]
MediaTemplateStorageDep = Annotated[BaseStorage, Depends(get_media_template_storage)]
SlideStorageDep = Annotated[BaseStorage, Depends(get_slide_storage)]
