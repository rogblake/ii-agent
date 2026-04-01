from __future__ import annotations


class StorageError(Exception):
    """Base storage exception."""


class StorageObjectNotFoundError(StorageError):
    """Object not found in storage."""


class StoragePermissionError(StorageError):
    """Credential or IAM failure."""


class StorageConfigError(StorageError):
    """Invalid storage configuration."""
