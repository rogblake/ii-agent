"""Custom exceptions for files domain."""

from ii_agent.core.exceptions import (
    InternalError,
    NotFoundError,
    PayloadTooLargeError,
    PermissionDeniedError,
)


class FileUploadNotFoundError(NotFoundError):
    """Raised when a file upload is not found."""

    def __init__(self, message: str | None = None, *, file_id: str | None = None):
        self.file_id = file_id
        if message is None:
            message = f"File '{file_id}' not found" if file_id else "File not found"
        super().__init__(message)



class FileAccessDeniedError(PermissionDeniedError):
    """Raised when a user does not have access to a file."""

    def __init__(self, file_id: str | None = None):
        self.file_id = file_id
        msg = (
            f"Access denied to file '{file_id}'"
            if file_id
            else "File access denied"
        )
        super().__init__(msg)


class FileSizeLimitExceededError(PayloadTooLargeError):
    """Raised when a file exceeds the maximum allowed size."""

    def __init__(self, file_size: int, max_size: int):
        self.file_size = file_size
        self.max_size = max_size
        super().__init__(
            f"File size {file_size} bytes exceeds maximum allowed size of {max_size} bytes"
        )


class FileStorageError(InternalError):
    """Raised when a storage operation fails."""

    pass
