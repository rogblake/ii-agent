"""Abstract base class for vector store implementations."""

from abc import ABC, abstractmethod
import uuid
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


class VectorStoreFileObject(BaseModel):
    """File object metadata for vector store."""

    id: str
    file_name: str
    content_type: str
    bytes: Optional[int]


class VectorStoreMetadata(BaseModel):
    """Generic metadata for vector store across all providers."""

    user_id: uuid.UUID
    provider: str
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    provider_store_id: Optional[str] = None
    files: Optional[dict[str, Any]] = None


class VectorStore(ABC):
    """Abstract base class for vector store implementations."""

    @abstractmethod
    async def retrieve(
        self, db_session: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> Optional[VectorStoreMetadata]:
        """
        Retrieve vector store metadata for a user session.

        Args:
            db_session: Database session
            user_id: The user's ID
            session_id: The session ID

        Returns:
            VectorStoreMetadata object or None if not found
        """
        pass

    @abstractmethod
    async def add_file(self, user_id: uuid.UUID, session_id: uuid.UUID, file_id: str) -> int:
        """
        Add a file to the user's vector store.

        Args:
            user_id: The user's ID
            session_id: The session ID
            file_id: File ID to add to the vector store

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def add_files_batch(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        file_ids: list[str],
    ) -> list[VectorStoreFileObject]:
        """
        Add multiple files to the user's vector store in a batch.

        Args:
            user_id: The user's ID
            session_id: The session ID
            file_ids: List of file IDs to add

        Returns:
            List of VectorStoreFileObject with file metadata
        """
        pass

    @abstractmethod
    async def delete(
        self, db_session: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> bool:
        """
        Delete vector store for a user session.

        Args:
            db_session: Database session
            user_id: The user's ID
            session_id: The session ID

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def search(
        self, user_id: uuid.UUID, session_id: uuid.UUID, query: str
    ) -> list[dict[str, Any]]:
        """
        Search through vector store using a query.

        Args:
            db_session: Database session
            user_id: The user's ID
            session_id: The session ID
            query: Search query string

        Returns:
            List of search results, each result is a dict with:
            - content: The matched content/text
            - score: Relevance score (if available)
            - metadata: Additional metadata (file_id, page, etc.)
        """
        pass
