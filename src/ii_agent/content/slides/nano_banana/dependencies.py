"""FastAPI dependencies for Nano Banana design mode."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from pydantic import SecretStr

from ii_agent.content.slides.dependencies import SlideRepositoryDep
from ii_agent.settings.llm import Provider
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.config.nano_banana import NanoBananaConfig
from ii_agent.core.config.settings import get_settings
from ii_agent.core.dependencies import SettingsDep
from ii_agent.sessions.dependencies import SessionRepositoryDep

from .repository import NanoBananaRepository
from .service import NanoBananaService


def get_nano_banana_repository(
    session_repo: SessionRepositoryDep,
    slide_repo: SlideRepositoryDep,
) -> NanoBananaRepository:
    """Provide NanoBananaRepository instance."""
    return NanoBananaRepository(session_repo=session_repo, slide_repo=slide_repo)


NanoBananaRepositoryDep = Annotated[NanoBananaRepository, Depends(get_nano_banana_repository)]


def _build_llm_config(nb_config: NanoBananaConfig) -> LLMConfig:
    """Build an LLMConfig from NanoBananaConfig settings."""
    return LLMConfig(
        model=nb_config.model,
        api_key=SecretStr(nb_config.api_key) if nb_config.api_key else None,
        provider=Provider(nb_config.provider),
        temperature=nb_config.temperature,
        base_url=nb_config.base_url,
        vertex_project_id=nb_config.vertex_project_id,
        vertex_region=nb_config.vertex_region,
        thinking_tokens=nb_config.thinking_tokens,
        config_type="system",
    )


def get_nano_banana_service(
    repo: NanoBananaRepositoryDep,
    settings: SettingsDep,
) -> NanoBananaService:
    """Provide NanoBananaService instance with LLM config from settings."""
    llm_config = _build_llm_config(settings.nano_banana)
    return NanoBananaService(
        repo=repo,
        llm_execution_service=None,
        llm_config=llm_config,
    )


NanoBananaServiceDep = Annotated[NanoBananaService, Depends(get_nano_banana_service)]


__all__ = [
    "get_nano_banana_repository",
    "get_nano_banana_service",
    "NanoBananaRepositoryDep",
    "NanoBananaServiceDep",
]
