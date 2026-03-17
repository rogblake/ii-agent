"""Vector store implementations for chat module."""

from ii_agent.chat.vectorstore.base import (
    VectorStore,
    VectorStoreMetadata,
    VectorStoreFileObject,
)
from ii_agent.chat.vectorstore.openai import OpenAIVectorStore, get_openai_vector_store

# Backwards-compat: ``openai_vector_store`` is resolved lazily so the
# heavy OpenAI client is only created when actually needed.
def __getattr__(name: str):
    if name == "openai_vector_store":
        return get_openai_vector_store()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "VectorStore",
    "VectorStoreMetadata",
    "VectorStoreFileObject",
    "OpenAIVectorStore",
    "get_openai_vector_store",
    "openai_vector_store",
]
