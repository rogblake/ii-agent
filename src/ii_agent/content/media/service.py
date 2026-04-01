"""Service layer for media domain - business logic only."""

from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession


from ii_agent.agents.tools.clients import _get_client
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.storage.path_resolver import path_resolver
from ii_agent.content.media.constants import IMAGE_MINI_TOOLS_TYPE
from ii_agent.content.media.models import MediaTemplate
from ii_agent.content.media.repository import MediaTemplateRepository
from ii_agent.content.media.schemas import MediaTemplateInfo, MediaTool, ReferenceImageResponse, get_image_limits
from ii_agent.core.storage.providers.base import StorageProvider
from ii_agent.core.redis.cache import EntityCache

logger = logging.getLogger(__name__)


def _get_public_url(storage: StorageProvider, preview: Optional[str]) -> Optional[str]:
    """Get public URL for a preview image."""
    if not preview:
        return None
    return storage.public_url(preview)


async def _get_public_urls_parallel(
    storage: StorageProvider, previews: List[Optional[str]]
) -> List[Optional[str]]:
    """Get public URLs for multiple previews. public_url is sync, so no I/O needed."""
    return [_get_public_url(storage, preview) for preview in previews]


def _map_template_to_media_tool(template: dict) -> MediaTool:
    """Map media_templates row into MediaTool shape."""
    preview_url = template.get("preview")
    name = template["name"]
    min_images, max_images = get_image_limits(name)
    return MediaTool(
        id=template["id"],
        name=name,
        preview=preview_url,
        min_images=min_images,
        max_images=max_images,
    )


class MediaTemplateService:
    """Service for managing media templates - business logic layer."""

    def __init__(
        self,
        *,
        repo: MediaTemplateRepository,
        media_storage: StorageProvider,
        config: Settings,
        cache: EntityCache,
    ) -> None:
        self._config = config
        self._repo = repo
        self._storage = media_storage
        self._cache = cache

    async def get_media_template_by_id(
        self, db: AsyncSession, template_id: str
    ) -> Optional[MediaTemplateInfo]:
        """Get a media template by ID.

        Returns:
            MediaTemplateInfo or None if not found.
        """
        cache_key = f"template:{template_id}"
        cached = await self._cache.get(cache_key)
        if cached:
            return MediaTemplateInfo(**cached)

        template = await self._repo.get_by_id(db, template_id)
        if not template:
            return None

        info = self._to_info(template)
        await self._cache.set(cache_key, info.model_dump())
        return info

    async def get_media_template_by_name(
        self, db: AsyncSession, name: str
    ) -> Optional[MediaTemplateInfo]:
        """Get a media template by name.

        Returns:
            MediaTemplateInfo or None if not found.
        """
        template = await self._repo.get_by_name(db, name)
        if not template:
            return None
        return self._to_info(template)

    async def list_media_templates(
        self,
        db: AsyncSession,
        *,
        page: int = 0,
        page_size: int = 20,
        search: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get a paginated list of media templates.

        Returns:
            Dictionary with templates list and pagination info.
        """
        cache_key = (
            f"list:page={page}:size={page_size}"
            f":search={search or ''}:type={media_type or ''}"
        )
        cached = await self._cache.get(cache_key)
        if cached:
            return cached

        result = await self._repo.list_templates(
            db,
            page=page,
            page_size=page_size,
            search=search,
            media_type=media_type,
        )

        templates: List[MediaTemplate] = result["templates"]

        # Resolve preview URLs in parallel
        previews = [t.preview for t in templates]
        public_urls = await _get_public_urls_parallel(self._storage, previews)

        result_dict: Dict[str, Any] = {
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "type": t.type,
                    "preview": url,
                    "prompt": t.prompt,
                }
                for t, url in zip(templates, public_urls)
            ],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
            "total_pages": result["total_pages"],
        }

        await self._cache.set(cache_key, result_dict)
        return result_dict

    # -- Media tools (mini tools) ------------------------------------------

    async def list_media_tools(
        self,
        db: AsyncSession,
        *,
        page: int = 0,
        page_size: int = 20,
        name: Optional[str] = None,
    ) -> List[MediaTool]:
        """List media mini tools with caching."""
        cache_key = f"tools:list:page={page}:size={page_size}:name={name or ''}"
        cached = await self._cache.get(cache_key)
        if cached:
            return [MediaTool(**tool) for tool in cached]

        result = await self.list_media_templates(
            db, page=page, page_size=page_size, search=name, media_type=IMAGE_MINI_TOOLS_TYPE,
        )
        templates = result.get("templates", [])
        media_tools = [_map_template_to_media_tool(t) for t in templates]

        await self._cache.set(cache_key, [tool.model_dump() for tool in media_tools])
        return media_tools

    async def get_media_tool(
        self,
        db: AsyncSession,
        tool_id: str,
    ) -> Optional[MediaTool]:
        """Get a media mini tool by id with caching."""
        cache_key = f"tool:{tool_id}"
        cached = await self._cache.get(cache_key)
        if cached:
            return MediaTool(**cached)

        template = await self.get_media_template_by_id(db, tool_id)
        if not template or getattr(template, "type", None) != IMAGE_MINI_TOOLS_TYPE:
            return None

        media_tool = _map_template_to_media_tool(template.model_dump())
        await self._cache.set(cache_key, media_tool.model_dump())
        return media_tool

    # -- Reference image generation ----------------------------------------

    async def generate_reference_image(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        prompt: str,
        reference_type: str,
        aspect_ratio: Optional[str] = None,
        session_id: Optional[str] = None,
        user_api_key: str,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        default_storage: StorageProvider,
        file_service: Any,
    ) -> ReferenceImageResponse:
        """Generate a reference image, store it, and create a FileAsset record."""
        from ii_agent.files.models import FileAsset

        try:
            result = await _generate_reference_image(
                prompt=prompt,
                reference_type=reference_type,
                aspect_ratio=aspect_ratio,
                session_id=session_id or str(uuid.uuid4()),
                user_api_key=user_api_key,
                model_name=model_name,
                provider=provider,
            )

            url = result.get("url")
            storage_path = result.get("storage_path")
            file_size = result.get("size", 0)
            mime_type = result.get("mime_type", "image/png")

            file_id = None
            if url and storage_path:
                ext = Path(storage_path).suffix or ".png"
                file_name = f"reference_{reference_type}_{uuid.uuid4()}{ext}"
                content_type = mimetypes.guess_type(storage_path)[0] or mime_type
                file_id = str(uuid.uuid4())

                if session_id:
                    await file_service.create_file_record(
                        db,
                        file_id=file_id,
                        file_name=file_name,
                        file_size=file_size,
                        storage_path=storage_path,
                        content_type=content_type,
                        session_id=session_id,
                    )
                else:
                    user_storage_path = path_resolver.user_generated(user_id, file_id, ext.lstrip("."))
                    try:
                        await default_storage.write_from_url(
                            url,
                            user_storage_path,
                            content_type,
                        )
                        storage_path = user_storage_path
                        signed_url = await default_storage.signed_download_url(user_storage_path)
                        if signed_url:
                            url = signed_url
                    except Exception as copy_error:
                        logger.warning(
                            "Failed to copy reference image to user storage path: %s",
                            copy_error,
                        )

                    db_file = FileAsset(
                        id=file_id,
                        user_id=user_id,
                        file_name=file_name,
                        file_size=file_size,
                        storage_path=storage_path,
                        content_type=content_type,
                    )
                    db.add(db_file)
                    await db.flush()
                    await db.refresh(db_file)

            return ReferenceImageResponse(success=True, url=url, file_id=file_id)
        except RuntimeError as e:
            logger.error(f"Reference image generation failed: {e}")
            return ReferenceImageResponse(success=False, error=str(e))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_info(self, template: MediaTemplate) -> MediaTemplateInfo:
        """Convert an ORM model to the schema DTO, resolving the preview URL."""
        return MediaTemplateInfo(
            id=template.id,
            name=template.name,
            type=template.type,
            prompt=template.prompt,
            preview=_get_public_url(self._storage, template.preview),
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

# Prompt prefixes for reference image generation by type
REFERENCE_TYPE_PROMPTS = {
    "subject": (
        "Generate a product-style reference image focusing ONLY on the subject/object itself. "
        "The subject must be isolated on a clean, plain white or neutral background. "
        "No environment, no scene, no background elements. "
        "Sharp focus on the subject with professional studio lighting. "
        "Subject: "
    ),
    "scene": (
        "Generate a scene/environment reference image showing ONLY the location, setting, or background. "
        "Focus on the atmosphere, architecture, landscape, or environment. "
        "Do NOT include any main character or prominent person as the focus. "
        "This is purely about the place, mood, and setting. "
        "Scene: "
    ),
    "style": (
        "Generate a reference image demonstrating a specific artistic style or visual aesthetic. "
        "Focus on the rendering technique, color palette, artistic medium, and visual treatment. "
        "The style should be the main feature - show how things are drawn/rendered, not what is drawn. "
        "Examples: anime style, watercolor, oil painting, 3D render, vintage photo, cyberpunk aesthetic. "
        "Style to demonstrate: "
    ),
}


async def _generate_image(
    *,
    prompt: str,
    aspect_ratio: str = "16:9",
    image_size: str = "2K",
    image_urls: Optional[list[str]] = None,
    session_id: str,
    user_api_key: str,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    background: Optional[str] = None,
    tool_server_url: Optional[str] = None,
) -> dict:
    """Generate image using tool_client library and return response dict."""
    # Build kwargs for tool_client.generate_image
    kwargs = {}

    # Add metadata
    kwargs["metadata"] = {
        "session_id": session_id,
        "user_api_key": user_api_key,
    }

    # Add optional parameters
    if background:
        kwargs["background"] = background

    # Call tool_client.generate_image
    result = await _get_client().generate_image(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        image_urls=image_urls,
        model_name=model_name,
        provider=provider,
        **kwargs,
    )

    # Transform ImageGenerationResult to the expected dict format
    return {
        "success": True,
        "url": result.url,
        "storage_path": result.storage_path,
        "size": result.size,
        "mime_type": result.mime_type,
        "file_name": result.file_name,
    }


async def _generate_reference_image(
    *,
    prompt: str,
    reference_type: str,
    aspect_ratio: str = "1:1",
    session_id: str,
    user_api_key: str,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    tool_server_url: Optional[str] = None,
) -> dict:
    """Generate reference image using tool_client library and return response dict.

    Applies reference type-specific prompt rules and calls tool_client.generate_image.
    """
    # Apply reference type-specific prompt prefix
    prefix = REFERENCE_TYPE_PROMPTS.get(reference_type, "")
    full_prompt = f"{prefix}{prompt}"

    # Call _generate_image with the enhanced prompt
    return await _generate_image(
        prompt=full_prompt,
        aspect_ratio=aspect_ratio,
        image_size="1K",  # Default size for reference images
        session_id=session_id,
        user_api_key=user_api_key,
        model_name=model_name,
        provider=provider,
        tool_server_url=tool_server_url,
    )
