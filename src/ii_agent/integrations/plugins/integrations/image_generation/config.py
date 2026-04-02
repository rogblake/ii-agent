import os

from pydantic import BaseModel


class ImageGenerateConfig(BaseModel):
    gcp_project_id: str | None = None
    gcp_location: str | None = None
    gcs_output_bucket: str | None = None
    gemini_api_key: str | None = None
    gemini_model_name: str = "gemini-3.1-flash-image-preview"
    google_ai_studio_api_key: str | None = None
    openai_api_key: str | None = None
    fal_api_key: str | None = None
    fal_model_name: str | None = None
    fal_request_mode: str = "async"

    def get_gemini_api_key(self) -> str | None:
        candidates = (
            self.gemini_api_key,
            self.google_ai_studio_api_key,
            os.environ.get("TOOL__IMAGE_GENERATE_CONFIG__GEMINI_API_KEY"),
            os.environ.get("TOOL__IMAGE_GENERATE_CONFIG__GOOGLE_AI_STUDIO_API_KEY"),
            os.environ.get("GEMINI_API_KEY"),
            os.environ.get("GOOGLE_AI_STUDIO_API_KEY"),
        )
        for candidate in candidates:
            if candidate and candidate.strip():
                return candidate.strip()
        return None

    def has_gemini_api_key(self) -> bool:
        return self.get_gemini_api_key() is not None
