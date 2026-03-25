from ii_agent_tools.integrations.image_search import utils
from ii_agent_tools.integrations.image_search.base import ImageSearchResult
from ii_agent_tools.integrations.image_search.config import ImageSearchConfig
from ii_agent_tools.integrations.image_search.factory import create_image_search_client
from ii_agent_tools.logger import get_logger
from ii_agent_tools.storage import BaseStorage

logger = get_logger(__name__)


class ImageSearchService:
    def __init__(
        self, image_search_config: ImageSearchConfig, storage: BaseStorage
    ) -> None:
        self.client = create_image_search_client(image_search_config)
        self.storage = storage

    async def search(
        self,
        query: str,
        aspect_ratio: str,
        image_type: str,
        min_width: int,
        min_height: int,
        is_product: bool,
        max_results: int,
    ) -> ImageSearchResult:
        try:
            client_results = await self.client.search(
                query=query,
                aspect_ratio=aspect_ratio,
                image_type=image_type,
                min_width=min_width,
                min_height=min_height,
                is_product=is_product,
                max_results=max_results,
            )
        except Exception:
            logger.exception(
                "Image search provider failed",
                extra={
                    "query": query,
                    "aspect_ratio": aspect_ratio,
                    "image_type": image_type,
                },
            )
            raise

        results = []

        for result in client_results.result:
            if len(results) >= max_results:
                break

            url = result["image_url"]
            is_available, content_type = await utils.is_image_url_available(url)
            if not is_available or content_type is None:
                logger.debug(
                    "Skipping unavailable image URL",
                    extra={"image_url": url, "content_type": content_type},
                )
                continue

            extension = utils.convert_mimetype_to_extension(content_type)
            name = utils.generate_unique_image_name()
            blob_path = utils.construct_blob_path(f"{name}.{extension}")
            try:
                await self.storage.write_from_url(url, blob_path, content_type)
            except Exception as e:
                logger.warning(
                    "Error writing image to storage",
                    extra={"image_url": url, "error": str(e)},
                )
                continue

            public_url = self.storage.get_public_url(blob_path)
            new_result = result.copy()
            new_result["image_url"] = public_url
            results.append(new_result)

        return ImageSearchResult(
            result=results,
            cost=client_results.cost,
        )
