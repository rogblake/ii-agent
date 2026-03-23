"""Enhance prompt integration package."""

__all__ = [
    "EnhancePromptClient",
    "EnhancePromptResult",
    "OpenAIEnhancePromptClient",
    "create_enhance_prompt_client",
    "router",
]


def __getattr__(name: str):
    if name in {
        "EnhancePromptClient",
        "EnhancePromptResult",
        "OpenAIEnhancePromptClient",
        "create_enhance_prompt_client",
    }:
        from .client import (
            EnhancePromptClient,
            EnhancePromptResult,
            OpenAIEnhancePromptClient,
            create_enhance_prompt_client,
        )

        exports = {
            "EnhancePromptClient": EnhancePromptClient,
            "EnhancePromptResult": EnhancePromptResult,
            "OpenAIEnhancePromptClient": OpenAIEnhancePromptClient,
            "create_enhance_prompt_client": create_enhance_prompt_client,
        }
        return exports[name]
    if name == "router":
        from .router import router

        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
