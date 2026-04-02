from typing import Literal
from pydantic import BaseModel


class LLMConfig(BaseModel):
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: Literal["gpt-5-mini", "gpt-4.1-mini"] = "gpt-5-mini"
