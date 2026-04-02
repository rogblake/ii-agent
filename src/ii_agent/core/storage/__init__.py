"""Storage module for file storage operations.

Import pattern:
    # For types and factory
    from ii_agent.core.storage import BaseStorage, GCS, create_storage_client

    # For path utilities
    from ii_agent.core.storage.locations import get_session_file_path

    # For singleton instances (import directly from client to avoid circular imports)
    from ii_agent.core.storage.client import storage, media_storage
"""

from .base import BaseStorage
from .gcs import GCS
from .factory import create_storage_client
from .dependencies import get_media_template_storage
from .locations import (
    get_conversation_agent_state_path,
    get_conversation_metadata_path,
    get_session_file_path,
    get_user_upload_file_path,
    get_user_avatar_path,
)

__all__ = [
    "BaseStorage",
    "GCS",
    "create_storage_client",
    "get_media_template_storage",
    "get_conversation_agent_state_path",
    "get_conversation_metadata_path",
    "get_session_file_path",
    "get_user_upload_file_path",
    "get_user_avatar_path",
]
