from abc import ABC, abstractmethod
from typing import BinaryIO


# Abstract Object Storage Interface
class BaseStorage(ABC):
    @abstractmethod
    def write(self, content: BinaryIO, path: str, content_type: str | None = None):
        pass

    @abstractmethod
    def write_from_url(
        self, url: str, path: str, content_type: str | None = None
    ) -> str:
        pass

    @abstractmethod
    def read(self, path: str) -> BinaryIO:
        pass

    @abstractmethod
    def get_download_signed_url(
        self, path: str, expiration_seconds: int = 3600
    ) -> str | None:
        pass

    @abstractmethod
    def get_download_signed_urls_batch(
        self, paths: list[str], expiration_seconds: int = 3600
    ) -> list[str | None]:
        """Generate signed URLs for multiple files efficiently."""
        pass

    @abstractmethod
    def get_upload_signed_url(
        self, path: str, content_type: str, expiration_seconds: int
    ) -> str:
        pass

    @abstractmethod
    def is_exists(self, path: str) -> bool:
        pass

    @abstractmethod
    def get_file_size(self, path: str) -> int:
        pass

    @abstractmethod
    def get_public_url(self, path: str) -> str:
        pass

    @abstractmethod
    def get_permanent_url(self, path: str) -> str:
        pass

    @abstractmethod
    def upload_and_get_permanent_url(
        self, content: BinaryIO, path: str, content_type: str | None = None
    ) -> str:
        pass

    def close(self) -> None:
        """Close the storage client and release resources.

        Override in subclasses that need cleanup (e.g., closing HTTP sessions).
        Default implementation does nothing.
        """
        pass
