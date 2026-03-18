"""Cross-cutting engine enums.

These enums are used across engine, realtime, integrations, and billing
layers. Keeping them here avoids dependency direction violations from
reaching into v1 sub-packages.
"""

from enum import Enum


class Provider(str, Enum):
    OPENAI = "OpenAI"
    ANTHROPIC = "Anthropic"
    VERTEX_AI = "VertexAI"
    GOOGLE = "Google"
    AZURE = "Azure"
    CEREBRAS = "Cerebras"
    CUSTOM = "Custom"


class AgentType(str, Enum):
    """Agent type enumeration."""

    GENERAL = "general"
    TASK_AGENT = "task_agent"
    RESEARCHER = "researcher"
    DESIGN_DOCUMENT = "design_document"
    MEDIA = "media"
    SLIDE = "slide"
    SLIDE_NANO_BANANA = "slide_nano_banana"
    WEBSITE_BUILD = "website_build"
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"
    DEEP_RESEARCH = "deep_research"
    FAST_RESEARCH = "fast_research"
    RESEARCH_TO_WEBSITE = "research_to_website"
    MOBILE_APP = "mobile_app"
