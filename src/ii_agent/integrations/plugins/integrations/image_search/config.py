from pydantic import BaseModel


class ImageSearchConfig(BaseModel):
    serpapi_api_key: str | None = None

    max_results: int = 5
