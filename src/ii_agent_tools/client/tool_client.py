"""In-process client for ii_agent_tools services."""

from typing import Literal

from ii_agent_tools.client.input_validator import InputValidator
from ii_agent_tools.client.tool_client_config import ToolClientSettings
from ii_agent_tools.integrations.audio_generation.base import AudioGenerationResult
from ii_agent_tools.integrations.audio_generation.service import AudioGenerationService
from ii_agent_tools.integrations.database import create_database_client, DatabaseConnectionResult
from ii_agent_tools.integrations.image_generation.base import ImageGenerationResult
from ii_agent_tools.integrations.image_generation.service import ImageGenerationService
from ii_agent_tools.integrations.image_search import ImageSearchService
from ii_agent_tools.integrations.image_search.base import ImageSearchResult
from ii_agent_tools.integrations.video_generation import VideoGenerationService
from ii_agent_tools.integrations.video_generation.base import (
    VideoGenerationResult,
    VideoReferenceImage,
)
from ii_agent_tools.integrations.voice_generation.base import VoiceGenerationResult
from ii_agent_tools.integrations.voice_generation.service import VoiceGenerationService
from ii_agent_tools.integrations.web_search import WebSearchService
from ii_agent_tools.integrations.web_search.base import (
    WEB_SEARCH_SERVICE_TYPES,
    WebSearchResult,
    WebSearchServiceType,
)
from ii_agent_tools.integrations.web_visit import WebVisitService
from ii_agent_tools.integrations.web_visit.base import (
    WEB_VISIT_SERVICE_TYPES,
    WebVisitResult,
    WebVisitServiceType,
)
from ii_agent_tools.llm import LLMClient
from ii_agent_tools.storage import create_storage_client

IMAGE_ASPECT_RATIOS = (
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
    "1:4",
    "4:1",
    "1:8",
    "8:1",
)
VIDEO_ASPECT_RATIOS = ("auto", "1:1", "3:4", "4:3", "9:16", "16:9", "21:9")
IMAGE_SEARCH_ASPECTS = ("all", "square", "tall", "wide", "panoramic")
IMAGE_SEARCH_TYPES = ("all", "face", "photo", "clipart", "lineart", "animated")
IMAGE_MIME_TYPES = ("image/png", "image/jpeg", "image/webp")


class IIToolClient:
    """Client wrapper that mirrors service behaviors without HTTP or auth."""

    def __init__(self, settings: ToolClientSettings) -> None:
        self.settings = settings

        self.input_validator = InputValidator()
        self.storage = create_storage_client(settings.storage_config)

        llm_config = settings.llm_config
        self.llm_client = (
            LLMClient(llm_config) if llm_config and llm_config.openai_api_key else None
        )
        self.init_services(settings)

    def init_services(self, settings: ToolClientSettings):
        self.web_search_service = WebSearchService(settings.web_search_config)
        self.web_visit_service = WebVisitService(self.llm_client, settings.web_visit_config)
        self.image_generation_service = ImageGenerationService(settings.image_generate_config)
        self.audio_generation_service = AudioGenerationService(settings.audio_generate_config)
        self.image_search_service = ImageSearchService(settings.image_search_config, self.storage)
        self.video_generation_service = VideoGenerationService(
            settings.video_generate_config, self.llm_client, self.storage
        )
        self.voice_generation_service = VoiceGenerationService(settings.voice_generate_config)

    async def web_search(
        self,
        query: str,
        max_results: int = 5,
        service_type: WebSearchServiceType | None = None,
    ) -> WebSearchResult:
        self.input_validator.validate_str("query", query, min_len=1, max_len=500)
        self.input_validator.validate_int("max_results", max_results, min_val=1, max_val=50)
        if service_type is not None:
            self.input_validator.validate_choice(
                "service_type", service_type, WEB_SEARCH_SERVICE_TYPES
            )

        return await self.web_search_service.search(query, max_results, service_type)

    async def web_batch_search(
        self,
        queries: list[str],
        max_results: int = 6,
        service_type: WebSearchServiceType | None = None,
    ) -> list[WebSearchResult]:
        self.input_validator.validate_list("queries", queries, min_len=1, max_len=10)
        for query in queries:
            self.input_validator.validate_str("query", query)
        self.input_validator.validate_int("max_results", max_results, min_val=1, max_val=50)
        if service_type is not None:
            self.input_validator.validate_choice(
                "service_type", service_type, WEB_SEARCH_SERVICE_TYPES
            )

        return await self.web_search_service.batch_search(queries, max_results, service_type)

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: Literal[
            "1:1",
            "2:3",
            "3:2",
            "3:4",
            "4:3",
            "4:5",
            "5:4",
            "9:16",
            "16:9",
            "21:9",
            "1:4",
            "4:1",
            "1:8",
            "8:1",
        ] = "1:1",
        image_urls: list[str] | None = None,
        image_size: str = "1K",
        model_name: str | None = None,
        provider: str | None = None,
        provider_payload: dict | None = None,
        request_mode: str | None = None,
        **kwargs,
    ) -> ImageGenerationResult:
        self.input_validator.validate_str("prompt", prompt)
        self.input_validator.validate_choice("aspect_ratio", aspect_ratio, IMAGE_ASPECT_RATIOS)
        self.input_validator.validate_str("image_size", image_size)
        if image_urls is not None:
            self.input_validator.validate_list("image_urls", image_urls, min_len=0)
            for url in image_urls:
                self.input_validator.validate_str("image_url", url)
        if model_name is not None:
            self.input_validator.validate_str("model_name", model_name)
        if provider is not None:
            self.input_validator.validate_str("provider", provider)
        if request_mode is not None:
            self.input_validator.validate_str("request_mode", request_mode)

        return await self.image_generation_service.generate_image(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            image_urls=image_urls,
            image_size=image_size,
            model_name=model_name,
            provider=provider,
            provider_payload=provider_payload,
            request_mode=request_mode,
            **kwargs,
        )

    async def image_search(
        self,
        query: str,
        aspect_ratio: Literal[
            "all",
            "square",
            "tall",
            "wide",
            "panoramic",
        ] = "all",
        image_type: Literal[
            "all",
            "face",
            "photo",
            "clipart",
            "lineart",
            "animated",
        ] = "all",
        min_width: int = 0,
        min_height: int = 0,
        is_product: bool = False,
        max_results: int = 5,
    ) -> ImageSearchResult:
        self.input_validator.validate_str("query", query)
        self.input_validator.validate_choice("aspect_ratio", aspect_ratio, IMAGE_SEARCH_ASPECTS)
        self.input_validator.validate_choice("image_type", image_type, IMAGE_SEARCH_TYPES)
        self.input_validator.validate_int("min_width", min_width)
        self.input_validator.validate_int("min_height", min_height)
        self.input_validator.validate_int("max_results", max_results)

        return await self.image_search_service.search(
            query=query,
            aspect_ratio=aspect_ratio,
            image_type=image_type,
            min_width=min_width,
            min_height=min_height,
            is_product=is_product,
            max_results=max_results,
        )

    async def web_visit(
        self,
        url: str,
        prompt: str | None = None,
        service_type: WebVisitServiceType | None = None,
    ) -> WebVisitResult:
        self.input_validator.validate_url(url)
        if prompt is not None:
            self.input_validator.validate_str("prompt", prompt, max_len=1000)
        if service_type is not None:
            self.input_validator.validate_choice(
                "service_type", service_type, WEB_VISIT_SERVICE_TYPES
            )

        return await self.web_visit_service.visit(url, prompt, service_type)

    async def researcher_web_visit(
        self,
        urls: list[str],
        query: str,
    ) -> WebVisitResult:
        self.input_validator.validate_list("urls", urls, min_len=1, max_len=10)
        for url in urls:
            self.input_validator.validate_url(url)
        self.input_validator.validate_str("query", query, min_len=1, max_len=500)
        return await self.web_visit_service.batch_visit(urls, query)

    async def video_generation(
        self,
        prompt: str,
        model_name: str | None = None,
        provider: str = "vertex",
        duration_seconds: int = 5,
        aspect_ratio: Literal["auto", "1:1", "3:4", "4:3", "9:16", "16:9", "21:9"] = "16:9",
        resolution: str = "720p",
        audio_included: bool = False,
        multishot_mode: bool = True,
        # Frame URLs (passed directly to Veo API)
        start_frame: str | None = None,
        end_frame: str | None = None,
        start_frame_base64: str | None = None,
        start_frame_mime_type: Literal["image/png", "image/jpeg", "image/webp"] | None = None,
        end_frame_base64: str | None = None,
        end_frame_mime_type: Literal["image/png", "image/jpeg", "image/webp"] | None = None,
        # Veo 3.1 additional parameters
        negative_prompt: str | None = None,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        seed: int | None = None,
        reference_images: list[VideoReferenceImage] | None = None,
        # Extension API for long videos with audio coherence
        use_extension_api: bool = True,
        provider_payload: dict | None = None,
        request_mode: str | None = None,
    ) -> VideoGenerationResult:
        """
        Generate video using Veo models.

        Args:
            prompt: Text description of the video to generate
            model_name: Model identifier (e.g., "veo-3.1-generate-preview")
            provider: Provider name (e.g., "vertex")
            duration_seconds: Duration in seconds (4-30, internally split if >8)
            aspect_ratio: Video aspect ratio
            resolution: Video resolution ("720p", "1080p", "4k")
            audio_included: Whether to generate audio with the video
            multishot_mode: Whether to enable multishot mode when supported
            start_frame: URL of start frame image (https:// or gs://)
            end_frame: URL of end frame image (https:// or gs://)
            start_frame_base64: Base64-encoded start frame image content
            start_frame_mime_type: MIME type for inline start frame content
            end_frame_base64: Base64-encoded end frame image content
            end_frame_mime_type: MIME type for inline end frame content
            negative_prompt: Description of unwanted content in the video
            person_generation: Person generation mode ("allow_all" or "allow_adult")
            seed: Random seed for reproducibility (Veo 3.x)
            reference_images: List of reference images for style/content (Veo 3.1+)
            use_extension_api: Use video extension API for long videos (maintains audio coherence)
        """
        self.input_validator.validate_str("prompt", prompt)
        self.input_validator.validate_choice("aspect_ratio", aspect_ratio, VIDEO_ASPECT_RATIOS)
        self.input_validator.validate_int(
            "duration_seconds", duration_seconds, min_val=3, max_val=30
        )
        if start_frame is not None:
            self.input_validator.validate_str("start_frame", start_frame, min_len=1)
        if end_frame is not None:
            self.input_validator.validate_str("end_frame", end_frame, min_len=1)
        if start_frame and start_frame_base64:
            raise ValueError("start_frame accepts either a URL or base64 content, not both")
        if end_frame and end_frame_base64:
            raise ValueError("end_frame accepts either a URL or base64 content, not both")
        if start_frame_base64 is not None:
            self.input_validator.validate_str("start_frame_base64", start_frame_base64, min_len=1)
        if start_frame_mime_type is not None:
            self.input_validator.validate_choice(
                "start_frame_mime_type", start_frame_mime_type, IMAGE_MIME_TYPES
            )
        if end_frame_base64 is not None:
            self.input_validator.validate_str("end_frame_base64", end_frame_base64, min_len=1)
        if end_frame_mime_type is not None:
            self.input_validator.validate_choice(
                "end_frame_mime_type", end_frame_mime_type, IMAGE_MIME_TYPES
            )
        if negative_prompt is not None:
            self.input_validator.validate_str("negative_prompt", negative_prompt)
        if person_generation is not None:
            self.input_validator.validate_choice(
                "person_generation", person_generation, ("allow_all", "allow_adult")
            )
        if seed is not None:
            self.input_validator.validate_int("seed", seed, min_val=0)
        if reference_images is not None:
            self.input_validator.validate_list(
                "reference_images", reference_images, min_len=0, max_len=3
            )
        if model_name is not None:
            self.input_validator.validate_str("model_name", model_name)
        self.input_validator.validate_str("provider", provider)
        if request_mode is not None:
            self.input_validator.validate_str("request_mode", request_mode)

        return await self.video_generation_service.generate_video(
            prompt=prompt,
            model_name=model_name,
            provider=provider,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            resolution=resolution,
            audio_included=audio_included,
            multishot_mode=multishot_mode,
            start_frame=start_frame,
            end_frame=end_frame,
            start_frame_base64=start_frame_base64,
            start_frame_mime_type=start_frame_mime_type,
            end_frame_base64=end_frame_base64,
            end_frame_mime_type=end_frame_mime_type,
            negative_prompt=negative_prompt,
            person_generation=person_generation,
            seed=seed,
            reference_images=reference_images,
            use_extension_api=use_extension_api,
            provider_payload=provider_payload,
            request_mode=request_mode,
        )

    async def video_extension(
        self,
        source_video_url: str,
        prompt: str,
        extension_seconds: int = 7,
        generate_audio: bool = True,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        end_frame: str | None = None,
    ) -> VideoGenerationResult:
        """
        Extend an existing video using Veo's video extension API.

        Returns a merged video (original + extension) with audio/visual coherence.
        Max 7 seconds per call, can be repeated up to 20 times (~148s total).

        Args:
            source_video_url: URL of the video to extend (from previous generation).
            prompt: Text prompt describing how the video should continue.
            extension_seconds: Duration to extend by (max 7s per call).
            generate_audio: Whether to continue generating synchronized audio.
            person_generation: Person generation mode ("allow_all" or "allow_adult").
            end_frame: URL of end frame image (https:// or gs://).

        Returns:
            VideoGenerationResult with the merged video URL.
        """
        self.input_validator.validate_url(source_video_url)
        self.input_validator.validate_str("prompt", prompt)
        self.input_validator.validate_int(
            "extension_seconds", extension_seconds, min_val=1, max_val=7
        )
        if person_generation is not None:
            self.input_validator.validate_choice(
                "person_generation", person_generation, ("allow_all", "allow_adult")
            )

        return await self.video_generation_service.extend_video(
            source_video_url=source_video_url,
            prompt=prompt,
            extension_seconds=extension_seconds,
            generate_audio=generate_audio,
            person_generation=person_generation,
            end_frame=end_frame,
        )

    async def generate_voice(
        self,
        text: str,
        voice_id: str | None = None,
        provider: str | None = None,
        model_name: str | None = None,
        output_format: str | None = None,
        voice_settings: dict | None = None,
        language_code: str | None = None,
        seed: int | None = None,
        provider_payload: dict | None = None,
        request_mode: str | None = None,
        pronunciation_dictionary_locators: list[dict] | None = None,
        previous_text: str | None = None,
        next_text: str | None = None,
        previous_request_ids: list[str] | None = None,
        next_request_ids: list[str] | None = None,
        enable_logging: bool | None = None,
        optimize_streaming_latency: int | None = None,
        apply_text_normalization: str | None = None,
        apply_language_text_normalization: str | None = None,
        **kwargs,
    ) -> VoiceGenerationResult:
        """Generate speech audio from text."""
        self.input_validator.validate_str("text", text, min_len=1)
        if voice_id is not None:
            self.input_validator.validate_str("voice_id", voice_id)
        if provider is not None:
            self.input_validator.validate_str("provider", provider)
        if model_name is not None:
            self.input_validator.validate_str("model_name", model_name)
        if output_format is not None:
            self.input_validator.validate_str("output_format", output_format)
        if language_code is not None:
            self.input_validator.validate_str("language_code", language_code)
        if seed is not None:
            self.input_validator.validate_int("seed", seed, min_val=0)
        if previous_text is not None:
            self.input_validator.validate_str("previous_text", previous_text)
        if next_text is not None:
            self.input_validator.validate_str("next_text", next_text)
        if pronunciation_dictionary_locators is not None:
            self.input_validator.validate_list(
                "pronunciation_dictionary_locators",
                pronunciation_dictionary_locators,
                min_len=0,
            )
        if previous_request_ids is not None:
            self.input_validator.validate_list(
                "previous_request_ids", previous_request_ids, min_len=0
            )
        if next_request_ids is not None:
            self.input_validator.validate_list("next_request_ids", next_request_ids, min_len=0)
        if optimize_streaming_latency is not None:
            self.input_validator.validate_int(
                "optimize_streaming_latency", optimize_streaming_latency, min_val=0
            )
        if request_mode is not None:
            self.input_validator.validate_str("request_mode", request_mode)

        return await self.voice_generation_service.generate_voice(
            text=text,
            voice_id=voice_id,
            provider=provider,
            model_name=model_name,
            output_format=output_format,
            voice_settings=voice_settings,
            language_code=language_code,
            seed=seed,
            provider_payload=provider_payload,
            request_mode=request_mode,
            pronunciation_dictionary_locators=pronunciation_dictionary_locators,
            previous_text=previous_text,
            next_text=next_text,
            previous_request_ids=previous_request_ids,
            next_request_ids=next_request_ids,
            enable_logging=enable_logging,
            optimize_streaming_latency=optimize_streaming_latency,
            apply_text_normalization=apply_text_normalization,
            apply_language_text_normalization=apply_language_text_normalization,
            **kwargs,
        )

    async def generate_audio(
        self,
        prompt: str,
        provider: str | None = None,
        model_name: str | None = None,
        music_length_ms: int | None = None,
        force_instrumental: bool | None = None,
        output_format: str | None = None,
        seed: int | None = None,
        provider_payload: dict | None = None,
        request_mode: str | None = None,
        **kwargs,
    ) -> AudioGenerationResult:
        self.input_validator.validate_str("prompt", prompt, min_len=1)
        if provider is not None:
            self.input_validator.validate_str("provider", provider)
        if model_name is not None:
            self.input_validator.validate_str("model_name", model_name)
        if music_length_ms is not None:
            self.input_validator.validate_int("music_length_ms", music_length_ms, min_val=1000)
        if output_format is not None:
            self.input_validator.validate_str("output_format", output_format)
        if seed is not None:
            self.input_validator.validate_int("seed", seed, min_val=0)
        if request_mode is not None:
            self.input_validator.validate_str("request_mode", request_mode)

        return await self.audio_generation_service.generate_audio(
            prompt=prompt,
            provider=provider,
            model_name=model_name,
            music_length_ms=music_length_ms,
            force_instrumental=force_instrumental,
            output_format=output_format,
            seed=seed,
            provider_payload=provider_payload,
            request_mode=request_mode,
            **kwargs,
        )

    async def database_connection(
        self,
        database_type: str,
        database_name: str,
    ) -> DatabaseConnectionResult:
        """
        Get a database connection with metadata.

        Args:
            database_type: Type of database ("postgres", "redis", "mysql")
            database_name: Unique identifier for the database (e.g., session ID)

        Returns:
            DatabaseConnectionResult with connection string and audit metadata
        """
        self.input_validator.validate_str("database_type", database_type)
        self.input_validator.validate_str("database_name", database_name, min_len=1, max_len=63)

        client = create_database_client(database_type, self.settings.database_config)
        try:
            return await client.get_database_connection(database_name)
        finally:
            if hasattr(client, "close"):
                await client.close()
