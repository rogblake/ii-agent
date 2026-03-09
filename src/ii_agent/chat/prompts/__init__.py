"""Chat prompts package.

Centralizes all prompt templates used across the chat module.
"""

from .anthropic_system_prompt import (
    SYSTEM_PROMPT_TEMPLATE as ANTHROPIC_SYSTEM_PROMPT_TEMPLATE,
    system_prompt_template as anthropic_system_prompt_template,
)
from .gemini_system_prompt import (
    SYSTEM_PROMPT_TEMPLATE as GEMINI_SYSTEM_PROMPT_TEMPLATE,
    template as gemini_system_prompt_template,
)
from .openai_system_prompt import (
    SYSTEM_PROMPT_TEMPLATE as OPENAI_SYSTEM_PROMPT_TEMPLATE,
    template as openai_system_prompt_template,
)
from .custom_system_prompt import (
    SYSTEM_PROMPT_TEMPLATE as CUSTOM_SYSTEM_PROMPT_TEMPLATE,
    template as custom_system_prompt_template,
)
from .context_prompts import PREVIOUS_SUMMARY, SUMMARY_PROMPT
from .video_prompts import (
    VIDEO_GENERATION_SYSTEM_PROMPT,
    build_audio_guidance_hint,
    build_frame_transition_hint,
)

__all__ = [
    "ANTHROPIC_SYSTEM_PROMPT_TEMPLATE",
    "anthropic_system_prompt_template",
    "GEMINI_SYSTEM_PROMPT_TEMPLATE",
    "gemini_system_prompt_template",
    "OPENAI_SYSTEM_PROMPT_TEMPLATE",
    "openai_system_prompt_template",
    "CUSTOM_SYSTEM_PROMPT_TEMPLATE",
    "custom_system_prompt_template",
    "PREVIOUS_SUMMARY",
    "SUMMARY_PROMPT",
    "VIDEO_GENERATION_SYSTEM_PROMPT",
    "build_audio_guidance_hint",
    "build_frame_transition_hint",
]
