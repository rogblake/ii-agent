"""Workspace explorer service -- file trees, file reads, and live sandbox watcher.

Starts an E2B ``watch_dir`` watcher lazily on the first ``file_tree`` request.
The watcher runs for the sandbox's lifetime and dies with it -- no explicit
stop, no subscriber tracking, no Redis coordination.
"""

from __future__ import annotations

import asyncio
import queue
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.stream import EventStream
from ii_agent.agent.sandboxes.e2b import E2BSandboxManager
from ii_agent.agent.sandboxes.schemas import (
    INLINE_CONTENT_PREFETCH_DEPTH,
    WATCHER_IGNORED_PREFIXES,
    SandboxStatus,
    is_binary_file_path,
)
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agent.sandboxes.models import AgentSandbox
    from ii_agent.agent.sandboxes.service import SandboxService
    from ii_agent.sessions.schemas import SessionInfo
    from ii_agent.sessions.service import SessionService

WATCH_ROOT = "/workspace"


@dataclass
class _WatcherState:
    """Local state for one sandbox's filesystem watcher."""

    provider_id: str
    sandbox_manager: E2BSandboxManager | None = None
    watch_handle: Any = None
    debounce_task: asyncio.Task | None = None
    # Thread-safe -- E2B SDK fires on_event from a background thread.
    event_queue: queue.Queue = field(default_factory=queue.Queue)
    # Session IDs that have opened the code explorer for this sandbox.
    # Used to fan-out FILE_TREE_UPDATE events. Stale entries are harmless
    # (EventStream publishes to the room; if no one is in it the event is dropped).
    session_ids: set[str] = field(default_factory=set)


class WorkspaceExplorerService:
    """File trees, file reads, and a lazy ``/workspace`` watcher per sandbox.

    The watcher is started on the first ``ensure_watching`` call and runs
    until the E2B sandbox dies (``on_exit`` fires).  No Redis coordination,
    no subscriber tracking, no heartbeat.
    """

    DEBOUNCE_SECONDS = 0.2

    def __init__(
        self,
        *,
        sandbox_service: SandboxService,
        session_service: SessionService,
    ) -> None:
        self._sandbox_service = sandbox_service
        self._session_service = session_service
        self._event_stream: EventStream | None = None
        self._watchers: dict[str, _WatcherState] = {}

    def bind_event_stream(self, event_stream: EventStream) -> None:
        self._event_stream = event_stream

    # ── Public API ────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        for pid in list(self._watchers):
            await self._stop_watcher(pid)

    async def get_tree(self, *, session_info: SessionInfo) -> dict[str, Any]:
        try:
            sandbox_manager, error, status = await self._get_sandbox_manager(
                session_info.id
            )
            if sandbox_manager is None:
                payload: dict[str, Any] = {"tree": None, "error": error}
                if status is not None:
                    payload["status"] = status
                return payload
            tree, contents = await sandbox_manager.list_files_with_contents(
                WATCH_ROOT,
                inline_content_max_depth=INLINE_CONTENT_PREFETCH_DEPTH,
            )
            return {
                "tree": tree.model_dump(),
                "root_path": WATCH_ROOT,
                "contents": contents,
            }
        except Exception as exc:
            logger.error(
                "Error getting file tree for session {}: {}",
                session_info.id,
                exc,
            )
            return {"tree": None, "error": "Failed to load file tree"}

    async def read_file(
        self, *, session_info: SessionInfo, path: str
    ) -> dict[str, Any]:
        if not path:
            return {"error": "No file path provided"}
        try:
            sandbox_manager, error, status = await self._get_sandbox_manager(
                session_info.id
            )
            if sandbox_manager is None:
                payload: dict[str, Any] = {"error": error, "path": path}
                if status is not None:
                    payload["status"] = status
                return payload
            result = await sandbox_manager.read_file_content(path)
            return {
                "path": result.path,
                "content": result.content,
                "language": result.language,
                "file_kind": result.file_kind,
                "mime_type": result.mime_type,
                "message": result.message,
                "too_big": result.too_big,
            }
        except Exception as exc:
            logger.warning(
                "Could not read file {} for session {}: {}",
                path,
                session_info.id,
                exc,
            )
            return {"error": "Failed to read file", "path": path}

    async def ensure_watching(
        self, *, session_info: SessionInfo
    ) -> None:
        """Start a watcher for the session's sandbox if one isn't running."""
        await self.ensure_watching_by_session_id(session_id=session_info.id)

    async def ensure_watching_by_session_id(
        self, *, session_id: uuid.UUID
    ) -> None:
        """Start a watcher for the session's sandbox if one isn't running."""
        if self._event_stream is None:
            return

        sandbox_record = await self._resolve_sandbox_record(session_id)
        if not sandbox_record or not sandbox_record.provider_sandbox_id:
            return

        provider_id = sandbox_record.provider_sandbox_id
        sid = str(session_id)

        # Already running -- just register the session.
        state = self._watchers.get(provider_id)
        if state is not None:
            state.session_ids.add(sid)
            return

        await self._start_watcher(provider_id, sid, sandbox_record)

    # ── Sandbox resolution ────────────────────────────────────────────

    async def _resolve_sandbox_record(
        self, session_id: uuid.UUID
    ) -> AgentSandbox | None:
        async with get_db_session_local() as db:
            return await self._sandbox_service.resolve_sandbox_for_session(
                db, session_id, session_service=self._session_service
            )

    async def _get_sandbox_manager(
        self, session_id: uuid.UUID
    ) -> tuple[E2BSandboxManager | None, str | None, str | None]:
        record = await self._resolve_sandbox_record(session_id)
        if not record or not record.provider_sandbox_id:
            return None, "No sandbox found", None
        return await self._connect_sandbox(record)

    async def _connect_sandbox(
        self, sandbox_record: AgentSandbox
    ) -> tuple[E2BSandboxManager | None, str | None, str | None]:
        sandbox_manager = await E2BSandboxManager.from_sandbox_record(
            sandbox_record=sandbox_record
        )
        if not sandbox_manager:
            return None, "Could not connect to sandbox", None
        info = await sandbox_manager.get_info()
        if info.status != SandboxStatus.RUNNING:
            return None, "Sandbox is not running", info.status.value
        return sandbox_manager, None, None

    # ── Watcher lifecycle ─────────────────────────────────────────────

    async def _start_watcher(
        self,
        provider_id: str,
        session_id: str,
        sandbox_record: AgentSandbox,
    ) -> None:
        try:
            sandbox_manager, error, _ = await self._connect_sandbox(
                sandbox_record
            )
            if sandbox_manager is None:
                logger.debug(
                    "Cannot start watcher for sandbox {}: {}",
                    provider_id,
                    error,
                )
                return

            state = _WatcherState(
                provider_id=provider_id,
                sandbox_manager=sandbox_manager,
                session_ids={session_id},
            )
            loop = asyncio.get_running_loop()

            def on_event(evt: Any) -> None:
                state.event_queue.put_nowait(evt)
                try:
                    loop.call_soon_threadsafe(
                        self._schedule_flush, provider_id
                    )
                except RuntimeError:
                    pass

            async def on_exit(exc: Exception | None) -> None:
                logger.opt(exception=exc).info(
                    "File watcher exited for sandbox {}", provider_id
                )
                self._cleanup_watcher(provider_id)

            await sandbox_manager._ensure_sandbox_connection()
            # timeout=0 means watch indefinitely (no expiry).
            state.watch_handle = await sandbox_manager.sandbox.files.watch_dir(
                WATCH_ROOT,
                on_event=on_event,
                on_exit=on_exit,
                timeout=0,
                recursive=True,
            )
            self._watchers[provider_id] = state
            logger.info(
                "File watcher started for sandbox {}", provider_id
            )
        except Exception:
            logger.opt(exception=True).debug(
                "Failed to start file watcher for sandbox {}", provider_id
            )

    def _cleanup_watcher(self, provider_id: str) -> None:
        """Remove watcher state after on_exit fires (no async needed)."""
        state = self._watchers.pop(provider_id, None)
        if state is not None and state.debounce_task and not state.debounce_task.done():
            state.debounce_task.cancel()

    async def _stop_watcher(self, provider_id: str) -> None:
        state = self._watchers.pop(provider_id, None)
        if state is None:
            return
        if state.debounce_task and not state.debounce_task.done():
            state.debounce_task.cancel()
        if state.watch_handle:
            try:
                await state.watch_handle.stop()
            except Exception:
                logger.opt(exception=True).debug(
                    "Error stopping watcher for sandbox {}", provider_id
                )

    # ── Debounced flush ───────────────────────────────────────────────

    def _schedule_flush(self, provider_id: str) -> None:
        state = self._watchers.get(provider_id)
        if state is None:
            return
        if state.debounce_task is not None and not state.debounce_task.done():
            return
        state.debounce_task = asyncio.create_task(
            self._debounced_flush(provider_id, state)
        )

    async def _debounced_flush(
        self, provider_id: str, state: _WatcherState
    ) -> None:
        try:
            while True:
                await asyncio.sleep(self.DEBOUNCE_SECONDS)
                await self._flush(provider_id, state)
                if state.event_queue.empty():
                    return
        except asyncio.CancelledError:
            return
        except Exception:
            logger.opt(exception=True).error(
                "File watcher flush error for sandbox {}", provider_id
            )

    async def _flush(
        self, provider_id: str, state: _WatcherState
    ) -> None:
        sandbox_manager = state.sandbox_manager
        event_stream = self._event_stream
        if sandbox_manager is None or event_stream is None:
            return

        events: list[Any] = []
        try:
            while True:
                events.append(state.event_queue.get_nowait())
        except queue.Empty:
            pass
        if not events:
            return

        session_ids = state.session_ids
        if not session_ids:
            return

        changes = self._build_changes(events)
        if not changes:
            return

        updated_contents = await self._read_updated_contents(
            sandbox_manager, changes
        )

        content: dict[str, Any] = {
            "changes": changes,
            "updated_contents": updated_contents,
        }

        if self._needs_tree_refresh(changes):
            tree, contents = await sandbox_manager.list_files_with_contents(
                WATCH_ROOT,
                inline_content_max_depth=INLINE_CONTENT_PREFETCH_DEPTH,
            )
            content["tree"] = tree.model_dump()
            content["root_path"] = WATCH_ROOT
            content["contents"] = contents

        for sid in list(session_ids):
            try:
                await event_stream.publish(
                    RealtimeEvent(
                        type=EventType.FILE_TREE_UPDATE,
                        session_id=uuid.UUID(sid),
                        content=content,
                    )
                )
            except ValueError:
                continue

    # ── Pure helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_changes(events: list[Any]) -> list[dict[str, str]]:
        changes: list[dict[str, str]] = []
        for evt in events:
            evt_type = (
                evt.type.value if hasattr(evt.type, "value") else str(evt.type)
            )
            evt_name = str(evt.name)
            path = (
                evt_name
                if evt_name.startswith("/")
                else f"{WATCH_ROOT}/{evt_name.lstrip('/')}"
            )
            if path.startswith(WATCHER_IGNORED_PREFIXES):
                continue
            changes.append(
                {"type": evt_type.lower(), "name": evt_name, "path": path}
            )
        return changes

    @staticmethod
    async def _read_updated_contents(
        sandbox_manager: E2BSandboxManager,
        changes: list[dict[str, str]],
    ) -> dict[str, dict[str, str]]:
        write_paths = [
            c["path"]
            for c in changes
            if c["type"] == "write" and not is_binary_file_path(c["path"])
        ]
        if not write_paths:
            return {}

        sem = asyncio.Semaphore(20)

        async def _read_one(
            path: str,
        ) -> tuple[str, dict[str, str]] | None:
            async with sem:
                try:
                    result = await sandbox_manager.read_file_content(
                        path, skip_metadata_check=True
                    )
                except Exception:
                    return None
                if (
                    result.file_kind != "text"
                    or result.content is None
                    or result.language is None
                ):
                    return None
                return result.path, {
                    "content": result.content,
                    "language": result.language,
                }

        results = await asyncio.gather(*(_read_one(p) for p in write_paths))
        return dict(r for r in results if r is not None)

    @staticmethod
    def _needs_tree_refresh(changes: list[dict[str, str]]) -> bool:
        return any(c["type"] in {"create", "remove", "rename"} for c in changes)


__all__ = ["WorkspaceExplorerService"]
