from pydantic.main import BaseModel


class WebSearchConfig(BaseModel):
    firecrawl_api_key: str | None = None
    serpapi_api_key: str | None = None
    jina_api_key: str | None = None
    tavily_api_key: str | None = None
    max_results: int = 5
