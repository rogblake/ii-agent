"""Composio Cache Service - Redis caching for Composio data."""

import json
import logging
from typing import Any, Dict, List, Optional

from ii_agent.core.redis.cache import EntityCache

logger = logging.getLogger(__name__)


class ComposioCacheService:
    """Cache service for Composio toolkit and integration data.

    Cache Keys (relative to the ``composio`` namespace):
    - toolkits:all - All toolkits list
    - toolkit:{slug} - Individual toolkit details
    - toolkit:{slug}:actions - Toolkit actions list
    - toolkit:{slug}:icon - Toolkit icon/logo URL
    - categories:all - All categories list
    - action:{name}:display_name - Action display name
    """

    # Cache TTL values (in seconds)
    TTL_TOOLKITS_LIST = 604800  # 7 days
    TTL_TOOLKIT_DETAILS = 604800
    TTL_TOOLKIT_ACTIONS = 604800
    TTL_TOOLKIT_ICON = 604800
    TTL_CATEGORIES = 604800
    TTL_ACTION_DISPLAY_NAME = 604800

    def __init__(self, *, cache: EntityCache) -> None:
        self._cache = cache

    # ── Toolkits ──────────────────────────────────────────────────────────

    async def get_all_toolkits(self) -> Optional[Dict[str, Any]]:
        try:
            result = await self._cache.get("toolkits:all")
            if result:
                return json.loads(result) if not isinstance(result, dict) else result
        except Exception as e:
            logger.error("Error getting cached toolkits: %s", e)
        return None

    async def set_all_toolkits(self, toolkits_data: Dict[str, Any]) -> bool:
        try:
            return await self._cache.set("toolkits:all", toolkits_data, ttl=self.TTL_TOOLKITS_LIST)
        except Exception as e:
            logger.error("Error caching toolkits: %s", e)
            return False

    # ── Toolkit details ───────────────────────────────────────────────────

    async def get_toolkit_details(self, toolkit_slug: str) -> Optional[Dict[str, Any]]:
        try:
            result = await self._cache.get(f"toolkit:{toolkit_slug}")
            if result:
                return json.loads(result) if not isinstance(result, dict) else result
        except Exception as e:
            logger.error("Error getting cached toolkit details for %s: %s", toolkit_slug, e)
        return None

    async def set_toolkit_details(self, toolkit_slug: str, toolkit_data: Dict[str, Any]) -> bool:
        try:
            return await self._cache.set(
                f"toolkit:{toolkit_slug}", toolkit_data, ttl=self.TTL_TOOLKIT_DETAILS
            )
        except Exception as e:
            logger.error("Error caching toolkit details for %s: %s", toolkit_slug, e)
            return False

    # ── Toolkit actions ───────────────────────────────────────────────────

    async def get_toolkit_actions(self, toolkit_slug: str) -> Optional[Dict[str, Any]]:
        try:
            result = await self._cache.get(f"toolkit:{toolkit_slug}:actions")
            if result:
                return json.loads(result) if not isinstance(result, dict) else result
        except Exception as e:
            logger.error("Error getting cached toolkit actions for %s: %s", toolkit_slug, e)
        return None

    async def set_toolkit_actions(
        self,
        toolkit_slug: str,
        actions_data: List[Dict[str, Any]],
        categories: Optional[List[str]] = None,
    ) -> bool:
        try:
            cache_data = {"actions": actions_data, "categories": categories or [], "success": True}
            return await self._cache.set(
                f"toolkit:{toolkit_slug}:actions", cache_data, ttl=self.TTL_TOOLKIT_ACTIONS
            )
        except Exception as e:
            logger.error("Error caching toolkit actions for %s: %s", toolkit_slug, e)
            return False

    # ── Toolkit icon ──────────────────────────────────────────────────────

    async def get_toolkit_icon(self, toolkit_slug: str) -> Optional[str]:
        try:
            result = await self._cache.get(f"toolkit:{toolkit_slug}:icon")
            if result:
                data = json.loads(result) if not isinstance(result, dict) else result
                return data.get("icon_url")
        except Exception as e:
            logger.error("Error getting cached toolkit icon for %s: %s", toolkit_slug, e)
        return None

    async def set_toolkit_icon(self, toolkit_slug: str, icon_url: Optional[str]) -> bool:
        try:
            return await self._cache.set(
                f"toolkit:{toolkit_slug}:icon", {"icon_url": icon_url}, ttl=self.TTL_TOOLKIT_ICON
            )
        except Exception as e:
            logger.error("Error caching toolkit icon for %s: %s", toolkit_slug, e)
            return False

    # ── Categories ────────────────────────────────────────────────────────

    async def get_categories(self) -> Optional[List[Dict[str, Any]]]:
        try:
            result = await self._cache.get("categories:all")
            if result:
                return json.loads(result) if not isinstance(result, dict) else result
        except Exception as e:
            logger.error("Error getting cached categories: %s", e)
        return None

    async def set_categories(self, categories_data: List[Dict[str, Any]]) -> bool:
        try:
            return await self._cache.set(
                "categories:all", {"categories": categories_data}, ttl=self.TTL_CATEGORIES
            )
        except Exception as e:
            logger.error("Error caching categories: %s", e)
            return False

    # ── Action display names ──────────────────────────────────────────────

    async def get_action_display_name(self, action_name: str) -> Optional[str]:
        try:
            result = await self._cache.get(f"action:{action_name}:display_name")
            if result:
                data = json.loads(result) if not isinstance(result, dict) else result
                return data.get("display_name")
        except Exception as e:
            logger.error("Error getting cached action display name for %s: %s", action_name, e)
        return None

    async def set_action_display_name(self, action_name: str, display_name: str) -> bool:
        try:
            return await self._cache.set(
                f"action:{action_name}:display_name",
                {"display_name": display_name},
                ttl=self.TTL_ACTION_DISPLAY_NAME,
            )
        except Exception as e:
            logger.error("Error caching action display name for %s: %s", action_name, e)
            return False

    # ── Invalidation ──────────────────────────────────────────────────────

    async def invalidate_toolkit(self, toolkit_slug: str) -> bool:
        try:
            await self._cache.evict(f"toolkit:{toolkit_slug}")
            await self._cache.evict(f"toolkit:{toolkit_slug}:actions")
            await self._cache.evict(f"toolkit:{toolkit_slug}:icon")
            await self._cache.evict("toolkits:all")
            logger.info("Invalidated cache for toolkit: %s", toolkit_slug)
            return True
        except Exception as e:
            logger.error("Error invalidating toolkit cache for %s: %s", toolkit_slug, e)
            return False

    async def invalidate_all(self) -> bool:
        try:
            await self._cache.evict("toolkits:all")
            await self._cache.evict("categories:all")
            logger.info("Invalidated all Composio cache entries")
            return True
        except Exception as e:
            logger.error("Error invalidating all Composio cache: %s", e)
            return False
