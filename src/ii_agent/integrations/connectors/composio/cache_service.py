"""Composio Cache Service - Redis caching for Composio data."""
import json
from typing import Optional, Dict, Any, List

from ii_agent.core.redis import entity_cache
from ii_agent.core.logger import logger

class ComposioCacheService:
    """Cache service for Composio toolkit and integration data.

    Cache Keys:
    - composio:toolkits:all - All toolkits list
    - composio:toolkit:{slug} - Individual toolkit details
    - composio:toolkit:{slug}:actions - Toolkit actions list
    - composio:toolkit:{slug}:icon - Toolkit icon/logo URL
    - composio:categories:all - All categories list
    """

    # Cache TTL values (in seconds)
    TTL_TOOLKITS_LIST = 604800  # 7 days = 7 x 24 x 60 x 60
    TTL_TOOLKIT_DETAILS = 604800
    TTL_TOOLKIT_ACTIONS = 604800
    TTL_TOOLKIT_ICON = 604800
    TTL_CATEGORIES = 604800
    TTL_ACTION_DISPLAY_NAME = 604800

    @staticmethod
    async def get_all_toolkits() -> Optional[Dict[str, Any]]:
        """Get cached list of all toolkits."""
        try:
            result = await entity_cache.get("composio:toolkits:all")
            if result:
                logger.debug("Cache HIT: composio:toolkits:all")
                return json.loads(result) if not isinstance(result, dict) else result
        except Exception as e:
            logger.error(f"Error getting cached toolkits: {e}")
            return None

    @staticmethod
    async def set_all_toolkits(toolkits_data: Dict[str, Any]) -> bool:
        """Cache the list of all toolkits."""
        try:
            success = await entity_cache.set(
                "composio:toolkits:all",
                toolkits_data,
                ttl=ComposioCacheService.TTL_TOOLKITS_LIST
            )
            if success:
                logger.debug("Cache SET: composio:toolkits:all")
                return success
        except Exception as e:
            logger.error(f"Error caching toolkits: {e}")
            return False

    @staticmethod
    async def get_toolkit_details(toolkit_slug: str) -> Optional[Dict[str, Any]]:
        """Get cached toolkit details."""
        try:
            cache_key = f"composio:toolkit:{toolkit_slug}"
            result = await entity_cache.get(cache_key)
            if result:
                logger.debug(f"Cache HIT: {cache_key}")
                return json.loads(result) if not isinstance(result, dict) else result
        except Exception as e:
            logger.error(f"Error getting cached toolkit details for {toolkit_slug}: {e}")
            return None

    @staticmethod
    async def set_toolkit_details(toolkit_slug: str, toolkit_data: Dict[str, Any]) -> bool:
        """Cache toolkit details."""
        try:
            cache_key = f"composio:toolkit:{toolkit_slug}"
            success = await entity_cache.set(
                cache_key,
                toolkit_data,
                ttl=ComposioCacheService.TTL_TOOLKIT_DETAILS
            )
            if success:
                logger.debug(f"Cache SET: {cache_key}")
                return success
        except Exception as e:
            logger.error(f"Error caching toolkit details for {toolkit_slug}: {e}")
            return False

    @staticmethod
    async def get_toolkit_actions(toolkit_slug: str) -> Optional[Dict[str, Any]]:
        """Get cached toolkit actions."""
        try:
            cache_key = f"composio:toolkit:{toolkit_slug}:actions"
            result = await entity_cache.get(cache_key)
            if result:
                logger.debug(f"Cache HIT: {cache_key}")
                return json.loads(result) if not isinstance(result, dict) else result
        except Exception as e:
            logger.error(f"Error getting cached toolkit actions for {toolkit_slug}: {e}")
            return None

    @staticmethod
    async def set_toolkit_actions(toolkit_slug: str, actions_data: List[Dict[str, Any]], categories: Optional[List[str]] = None) -> bool:
        """Cache toolkit actions with optional categories."""
        try:
            cache_key = f"composio:toolkit:{toolkit_slug}:actions"
            cache_data = {
                "actions": actions_data,
                "categories": categories or [],
                "success": True
            }
            success = await entity_cache.set(
                cache_key,
                cache_data,
                ttl=ComposioCacheService.TTL_TOOLKIT_ACTIONS
            )
            if success:
                logger.debug(f"Cache SET: {cache_key}")
                return success
        except Exception as e:
            logger.error(f"Error caching toolkit actions for {toolkit_slug}: {e}")
            return False

    @staticmethod
    async def get_toolkit_icon(toolkit_slug: str) -> Optional[str]:
        """Get cached toolkit icon URL."""
        try:
            cache_key = f"composio:toolkit:{toolkit_slug}:icon"
            result = await entity_cache.get(cache_key)
            if result:
                logger.debug(f"Cache HIT: {cache_key}")
                data = json.loads(result) if not isinstance(result, dict) else result
                return data.get("icon_url")
            return None
        except Exception as e:
            logger.error(f"Error getting cached toolkit icon for {toolkit_slug}: {e}")
            return None

    @staticmethod
    async def set_toolkit_icon(toolkit_slug: str, icon_url: Optional[str]) -> bool:
        """Cache toolkit icon URL."""
        try:
            cache_key = f"composio:toolkit:{toolkit_slug}:icon"
            cache_data = {"icon_url": icon_url}
            success = await entity_cache.set(
                cache_key,
                cache_data,
                ttl=ComposioCacheService.TTL_TOOLKIT_ICON
            )
            if success:
                logger.debug(f"Cache SET: {cache_key}")
                return success
        except Exception as e:
            logger.error(f"Error caching toolkit icon for {toolkit_slug}: {e}")
            return False

    @staticmethod
    async def get_categories() -> Optional[List[Dict[str, Any]]]:
        """Get cached categories list."""
        try:
            result = await entity_cache.get("composio:categories:all")
            if result:
                logger.debug("Cache HIT: composio:categories:all")
                return json.loads(result) if not isinstance(result, dict) else result
        except Exception as e:
            logger.error(f"Error getting cached categories: {e}")
            return None

    @staticmethod
    async def set_categories(categories_data: List[Dict[str, Any]]) -> bool:
        """Cache categories list."""
        try:
            cache_data = {"categories": categories_data}
            success = await entity_cache.set(
                "composio:categories:all",
                cache_data,
                ttl=ComposioCacheService.TTL_CATEGORIES
            )
            if success:
                logger.debug("Cache SET: composio:categories:all")
                return success
        except Exception as e:
            logger.error(f"Error caching categories: {e}")
            return False

    @staticmethod
    async def get_action_display_name(action_name: str) -> Optional[str]:
        """Get cached action display name."""
        try:
            cache_key = f"composio:action:{action_name}:display_name"
            result = await entity_cache.get(cache_key)
            if result:
                logger.debug(f"Cache HIT: {cache_key}")
                data = json.loads(result) if not isinstance(result, dict) else result
                return data.get("display_name")
            return None
        except Exception as e:
            logger.error(f"Error getting cached action display name for {action_name}: {e}")
            return None

    @staticmethod
    async def set_action_display_name(action_name: str, display_name: str) -> bool:
        """Cache action display name."""
        try:
            cache_key = f"composio:action:{action_name}:display_name"
            cache_data = {"display_name": display_name}
            success = await entity_cache.set(
                cache_key,
                cache_data,
                ttl=ComposioCacheService.TTL_ACTION_DISPLAY_NAME
            )
            if success:
                logger.debug(f"Cache SET: {cache_key}")
                return success
        except Exception as e:
            logger.error(f"Error caching action display name for {action_name}: {e}")
            return False

    @staticmethod
    async def invalidate_toolkit(toolkit_slug: str) -> bool:
        """Invalidate all cache entries for a specific toolkit."""
        try:
            await entity_cache.evict(f"composio:toolkit:{toolkit_slug}")
            await entity_cache.evict(f"composio:toolkit:{toolkit_slug}:actions")
            await entity_cache.evict(f"composio:toolkit:{toolkit_slug}:icon")
            await entity_cache.evict("composio:toolkits:all")
            logger.info(f"Invalidated cache for toolkit: {toolkit_slug}")
            return True
        except Exception as e:
            logger.error(f"Error invalidating toolkit cache for {toolkit_slug}: {e}")
            return False

    @staticmethod
    async def invalidate_all() -> bool:
        """Invalidate all Composio cache entries."""
        try:
            await entity_cache.evict("composio:toolkits:all")
            await entity_cache.evict("composio:categories:all")
            logger.info("Invalidated all Composio cache entries")
            return True
        except Exception as e:
            logger.error(f"Error invalidating all Composio cache: {e}")
            return False
