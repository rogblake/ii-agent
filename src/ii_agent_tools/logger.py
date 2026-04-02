"""Centralized logging helpers for ii_agent_tools."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import sys
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Optional

# Use project directory for logs by default instead of /app/log
DEFAULT_LOG_DIR = Path.cwd() / "logs"
LOG_FILE_PATH = Path(os.environ.get("II_TOOL_LOG_FILE", str(DEFAULT_LOG_DIR / "app.log")))
LOG_LEVEL = os.environ.get("II_TOOL_LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.environ.get(
    "II_TOOL_LOG_FORMAT",
    "%(asctime)s | %(levelname)s | %(name)s | %(request_id)s | %(message)s",
)
# Enable JSON logging for production environments
USE_JSON_LOGGING = os.environ.get("II_TOOL_USE_JSON_LOGGING", "false").lower() == "true"

_REQUEST_ID_CTX: ContextVar[str] = ContextVar("request_id", default="-")
_CONFIGURED = False


class RequestIdFilter(logging.Filter):
    """Inject request_id from the context into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - simple passthrough
        record.request_id = _REQUEST_ID_CTX.get("-")
        return True


class SensitiveDataFilter(logging.Filter):
    """Filter to redact sensitive data from log messages."""

    # Patterns for sensitive data
    PATTERNS = [
        (r'password["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)', r"password=***"),
        (r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)', r"api_key=***"),
        (r'token["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)', r"token=***"),
        (r'secret["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)', r"secret=***"),
        (
            r"authorization:\s*bearer\s+([^\s]+)",
            r"authorization: bearer ***",
            re.IGNORECASE,
        ),
        # Credit card patterns (basic)
        (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", r"****-****-****-****"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive data from log message and args."""
        if hasattr(record, "msg") and record.msg:
            msg_str = str(record.msg)
            for pattern, replacement, *flags in self.PATTERNS:
                flag = flags[0] if flags else 0
                msg_str = re.sub(pattern, replacement, msg_str, flags=flag)
            record.msg = msg_str

        # Also filter args if present - only filter string args
        if record.args and isinstance(record.args, (tuple, list)):
            filtered_args = []
            for arg in record.args:
                # Only filter string arguments, leave others untouched
                if isinstance(arg, str):
                    filtered_arg = arg
                    for pattern, replacement, *flags in self.PATTERNS:
                        flag = flags[0] if flags else 0
                        filtered_arg = re.sub(pattern, replacement, filtered_arg, flags=flag)
                    filtered_args.append(filtered_arg)
                else:
                    # Keep non-string args as-is (int, float, etc.)
                    filtered_args.append(arg)

            if isinstance(record.args, tuple):
                record.args = tuple(filtered_args)
            else:
                record.args = filtered_args

        return True


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "message",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "request_id",
                ]:
                    log_data[key] = value

        return json.dumps(log_data)


def _build_handlers(formatter: logging.Formatter) -> list[logging.Handler]:
    """Build logging handlers with rotation and filtering."""
    handlers: list[logging.Handler] = []

    # Stream handler for stdout
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(RequestIdFilter())
    stream_handler.addFilter(SensitiveDataFilter())
    handlers.append(stream_handler)

    # File handler with rotation
    try:
        LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Use RotatingFileHandler with 10MB max size and 5 backup files
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE_PATH,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(RequestIdFilter())
        file_handler.addFilter(SensitiveDataFilter())
        handlers.append(file_handler)
    except OSError as exc:
        # Fall back to stdout if we cannot use the requested log file.
        print(
            f"[ii_agent_tools] Failed to initialize file logging at {LOG_FILE_PATH}: {exc}. "
            "Falling back to stdout.",
            file=sys.stderr,
        )

    return handlers


def configure_logging(level: str | int | None = None, fmt: str | None = None) -> None:
    """
    Configure root logging with context-aware formatting.

    Features:
    - Request ID tracking via context variables
    - Sensitive data filtering (passwords, API keys, tokens)
    - Log rotation (10MB max, 5 backup files)
    - Optional JSON logging for production (set II_TOOL_USE_JSON_LOGGING=true)
    - Configurable via environment variables
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = level or LOG_LEVEL

    # Use JSON formatter if enabled, otherwise use standard formatter
    if USE_JSON_LOGGING:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(fmt or LOG_FORMAT)

    handlers = _build_handlers(formatter)

    root_logger = logging.getLogger()
    for handler in handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    _CONFIGURED = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a configured logger; configuration is initialized on first call."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)


def bind_request_id(request_id: str | None) -> Token:
    """Bind a request ID to the logging context and return the token for reset."""
    return _REQUEST_ID_CTX.set(request_id or "-")


def reset_request_id(token: Token | None) -> None:
    """Reset the request ID context to the previous value."""
    if token is None:
        return
    try:
        _REQUEST_ID_CTX.reset(token)
    except ValueError:
        # Already reset; ignore to avoid raising from finally blocks
        pass


__all__ = [
    "get_logger",
    "configure_logging",
    "LOG_FILE_PATH",
    "bind_request_id",
    "reset_request_id",
]
