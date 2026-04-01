from enum import Enum


class Provider(str, Enum):
    OPENAI = "OpenAI"
    ANTHROPIC = "Anthropic"
    VERTEX_AI = "VertexAI"
    GOOGLE = "Google"
    AZURE = "Azure"
    CEREBRAS = "Cerebras"
    CUSTOM = "Custom"
