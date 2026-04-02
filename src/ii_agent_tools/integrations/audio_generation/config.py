from pydantic import BaseModel


class AudioGenerateConfig(BaseModel):
    fal_api_key: str | None = None
    fal_model_name: str | None = None
    fal_request_mode: str = "async"
