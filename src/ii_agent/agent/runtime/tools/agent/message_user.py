"""Tool for communicating with the end user."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from ii_agent.core.config.settings import get_settings
from ii_agent.core.storage.factory import create_storage_client
from ii_agent.agent.runtime.tools.base import ToolResult
from ii_agent.agent.runtime.tools.sandbox.base import BaseSandboxTool
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.core.storage import BaseStorage
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall
    from ii_agent.agent.sandboxes.base import SandboxManager

NAME = "send_user_files"
DISPLAY_NAME = "Sending file to user"
DESCRIPTION = "Send an attachment to the user with optional message. You must only call this tool after the files have been created, not in parallel."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "Short message to send to the user.",
        },
        "attachments": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "List of file paths to deliver with the message. This must be in absolute path or relative to sandbox working directory."
                "Directories must be zipped and archived before attaching."
            ),
            "default": [],
        },
    },
    "required": ["attachments"],
    "additionalProperties": False,
}


class SendUserFile(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        message_text = tool_input.get("message", "")
        if not isinstance(message_text, str):
            return self._error_result("`message` must be a string.")

        attachments_input = tool_input.get("attachments", [])
        if attachments_input is None:
            attachments_input = []
        if not isinstance(attachments_input, list):
            return self._error_result("`attachments` must be an array of file paths.")
        payload = {
            "tool_name": "message",
            "action": {
                "text": message_text,
                "attachments": attachments_input,
            },
        }
        payload_json = json.dumps(payload)

        return ToolResult(
            llm_content=payload_json,
            user_display_content=payload,
            is_error=False,
        )

    async def on_tool_start(self, agent: IIAgent, fc: FunctionCall) -> None:
        await super().on_tool_start(agent, fc)

    async def on_tool_end(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        if fc.error:
            return

        tool_result = fc.result
        if not isinstance(tool_result, ToolResult):
            return
        if tool_result.is_error:
            return

        user_display = tool_result.user_display_content
        if not isinstance(user_display, dict):
            return

        action = user_display.get("action")
        if not isinstance(action, dict):
            return

        attachments = action.get("attachments")
        if not isinstance(attachments, list) or not attachments:
            return

        storage = _build_storage()
        if storage is None:
            return

        sandbox = getattr(agent, "sandbox", None)
        updated_attachments: list[dict[str, str]] = []
        for attachment in attachments:
            meta = await _process_attachment(
                attachment,
                session_id=getattr(agent, "session_id", None),
                sandbox=sandbox,
                storage=storage,
            )
            if meta:
                updated_attachments.append(meta)

        action["attachments"] = updated_attachments
        tool_result.user_display_content = user_display

    def _error_result(self, message: str) -> ToolResult:
        return ToolResult(
            llm_content=message,
            user_display_content=message,
            is_error=True,
        )


def _build_storage() -> Optional["BaseStorage"]:
    settings = get_settings()
    project_id = settings.storage.slide_assets_project_id or settings.storage.file_upload_project_id
    bucket_name = settings.storage.slide_assets_bucket_name or settings.storage.file_upload_bucket_name
    if not project_id or not bucket_name:
        logger.warning("Message attachments skipped: storage config missing")
        return None

    try:
        return create_storage_client(
            settings.storage.provider,
            project_id,
            bucket_name,
            settings.storage.custom_domain,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Message attachments skipped: %s", exc)
        return None


async def _process_attachment(
    attachment: object,
    *,
    session_id: Optional[str],
    sandbox: Optional["SandboxManager"],
    storage: "BaseStorage",
) -> Optional[dict[str, str]]:
    if isinstance(attachment, dict):
        name = attachment.get("name")
        url = attachment.get("url")
        file_type = attachment.get("file_type")
        if isinstance(url, str) and url:
            resolved_name = name if isinstance(name, str) and name else _guess_name_from_path(url)
            determined_type = (
                file_type if isinstance(file_type, str) else _determine_file_type(resolved_name)
            )
            return {
                "name": resolved_name,
                "file_type": determined_type,
                "url": url,
            }
        return None

    if not isinstance(attachment, str) or not attachment.strip():
        return None

    if _is_remote_url(attachment):
        name = _guess_name_from_path(attachment)
        return {
            "name": name,
            "file_type": _determine_file_type(name),
            "url": attachment,
        }

    if not sandbox:
        logger.warning("No sandbox available to fetch attachment %s", attachment)
        return None

    filename = Path(attachment).name or "attachment"
    storage_path = _generate_storage_path(filename, session_id)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    try:
        upload_url = storage.get_upload_signed_url(
            storage_path,
            content_type,
            expiration_seconds=3600,
        )
    except Exception as exc:
        logger.error(
            "Failed to create signed upload URL for attachment %s: %s",
            attachment,
            exc,
        )
        return None

    if not upload_url:
        logger.error(
            "Failed to create signed upload URL for attachment %s",
            attachment,
        )
        return None

    try:
        stream = sandbox.download_file_stream(attachment)
    except Exception as exc:
        logger.warning(
            "Unable to stream attachment %s from sandbox: %s",
            attachment,
            exc,
        )
        return None

    if stream is None:
        logger.warning("Attachment %s could not be streamed from sandbox", attachment)
        return None

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.put(
                upload_url,
                content=stream,
                headers={"Content-Type": content_type},
            )
    except httpx.HTTPError as exc:
        logger.error(
            "Failed to upload attachment %s to signed URL: %s",
            attachment,
            exc,
        )
        return None

    if not response.is_success:
        logger.error(
            "Failed to upload attachment %s to signed URL: %s %s",
            attachment,
            response.status_code,
            response.text,
        )
        return None

    try:
        permanent_url = storage.get_permanent_url(storage_path)
        logger.info("Uploaded attachment %s to %s", attachment, storage_path)
        return {
            "name": filename,
            "file_type": _determine_file_type(filename),
            "url": permanent_url,
        }
    except Exception as exc:
        logger.error(
            "Failed to finalize attachment %s after upload: %s",
            attachment,
            exc,
        )
        return None


def _generate_storage_path(filename: str, session_id: Optional[str]) -> str:
    safe_name = filename or "attachment"
    identifier = uuid4().hex
    session_part = session_id or "unknown-session"
    return f"sessions/{session_part}/attachments/{identifier}-{safe_name}"


def _is_remote_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def _guess_name_from_path(path: str) -> str:
    parsed = urlparse(path)
    candidate = parsed.path or path
    name = Path(candidate).name
    return name or "attachment"


def _determine_file_type(filename: str) -> str:
    extension = Path(filename).suffix.lower()

    code_extensions = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".rb",
        ".go",
        ".rs",
        ".c",
        ".cpp",
        ".cs",
        ".swift",
        ".kt",
        ".php",
        ".html",
        ".css",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".sh",
        ".md",
    }
    spreadsheet_extensions = {
        ".xls",
        ".xlsx",
        ".csv",
        ".tsv",
    }
    archive_extensions = {
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".rar",
        ".7z",
    }

    if extension in code_extensions:
        return "code"
    if extension in spreadsheet_extensions:
        return "xlsx"
    if extension in archive_extensions:
        return "archive"

    document_extensions = {
        ".pdf",
        ".doc",
        ".docx",
        ".txt",
        ".rtf",
        ".ppt",
        ".pptx",
    }
    if extension in document_extensions:
        return "documents"

    return "documents"
