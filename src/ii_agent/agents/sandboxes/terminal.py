"""Provider-agnostic live terminal interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


TerminalDataCallback = Callable[[bytes], None] | Callable[[bytes], Awaitable[None]]


class LiveTerminalError(Exception):
    """Base exception for live terminal operations."""


class LiveTerminalNotFoundError(LiveTerminalError):
    """Raised when a live terminal process is no longer available."""


class LiveTerminalHandle(ABC):
    """Provider-agnostic handle for a live PTY session."""

    @property
    @abstractmethod
    def pid(self) -> int:
        """Return the provider process identifier for this PTY."""

    @abstractmethod
    async def send_input(self, data: bytes) -> None:
        """Write raw bytes to the PTY stdin."""

    @abstractmethod
    async def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY in character cells."""

    @abstractmethod
    async def kill(self) -> bool:
        """Terminate the PTY."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Detach the current client handle without necessarily killing the PTY."""

    @abstractmethod
    async def wait(self) -> int | None:
        """Wait for the PTY to exit and return its exit code when available."""
