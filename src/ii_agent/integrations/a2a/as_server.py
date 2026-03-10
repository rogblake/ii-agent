"""A2A Agent implementation for II Agent platform."""

import asyncio
import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from a2a.types import (
    Message,
    Part,
    Role,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from sqlalchemy import select

from ii_agent.integrations.a2a.event_stream_adapter import EventStreamAdapter
from ii_agent.integrations.a2a.constants import SANDBOX_REUSE_EXTENSION_URI
from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload
from ii_agent.integrations.a2a.extension_utils import append_extension_issue
from ii_agent.integrations.a2a.resource_pool import resource_pool
from ii_agent.integrations.a2a.session_registry import A2ASessionRegistry, SessionRecord
from ii_agent.agent.types import AgentType
from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.agent.agents.models import AgentRunTask
from ii_agent.agent.agents.repository import AgentRunTaskRepository
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.agents.agent_run_service import AgentRunService
from ii_agent.realtime.events.repository import EventRepository
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.service import SessionService
from ii_agent.auth.users.models import User
from ii_agent.agent.sandboxes.e2b import E2BSandboxManager
from ii_agent.agent.sandboxes.repository import SandboxRepository
from ii_agent.core.config.settings import get_settings
from ii_agent.agent.agents.agent_service import AgentService
from ii_agent.agent.sandboxes.sandbox_client import MCPClient

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ii_agent.agent.agents.agent_service import AgentService

logger = logging.getLogger("a2a_agent")

session_registry = A2ASessionRegistry()


class IIAgentA2AServer:
    """A2A Agent for II Agent platform - Simplified protocol adaptation layer"""

    def __init__(self):
        self._agent_service: "AgentService" = None
        self._config = None
        logger.debug("II Agent A2A Agent initialized")

    @property
    def agent_service_instance(self) -> "AgentService":
        """Lazy initialization of agent service."""
        if self._agent_service is None:
            from ii_agent.core.storage.client import storage
            self._agent_service = AgentService(config=get_settings(), file_store=storage)
        return self._agent_service

    @property
    def config(self):
        """Lazy initialization of config."""
        if self._config is None:
            self._config = get_settings()
        return self._config

    def _build_session_service(self) -> SessionService:
        """Build a SessionService with all required repositories."""
        from ii_agent.core.storage.client import storage

        cfg = self.config
        return SessionService(
            config=cfg,
            session_repo=SessionRepository(),
            event_repo=EventRepository(),
            agent_run_service=AgentRunService(
                repo=AgentRunTaskRepository(), config=cfg
            ),
            file_store=storage,
            sandbox_repo=SandboxRepository(),
        )

    async def process_request(
        self,
        query: str,
        request_payload: Optional[A2ARequestPayload] = None,
        a2a_context=None,
        event_queue=None,
        extension_context: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Process A2A requests and stream responses via event queue.

        ID mapping relationship:
        - A2A context_id -> ii-agent session_id (session continuity, supports multi-turn conversations)
        - A2A task_id -> Only used for logging and resource identification, not passed to ii-agent

        Core logic:
        1. Use A2A context_id as ii-agent session_id
        2. Let ii-agent manage session state and history
        3. A2A task_id is only used for logging and sandbox isolation
        4. All status updates and results are delivered via event_queue
        """
        try:
            # Get ID from A2A context
            task_id = a2a_context.task_id if a2a_context else str(uuid.uuid4())
            context_id = a2a_context.context_id if a2a_context else str(uuid.uuid4())

            logger.info(f"[A2A Task {task_id}] Processing request: {query[:50]}...")

            await self._process_agent_request(
                query,
                request_payload,
                task_id,
                context_id,
                a2a_context,
                event_queue,
                extension_context,
            )

        except Exception as e:
            logger.error(f"[A2A] Error processing request: {e}", exc_info=True)
            # Send error event through event_queue
            if event_queue:
                error_message = Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.agent,
                    parts=[
                        Part(root=TextPart(text=f"Error processing request: {str(e)}"))
                    ],
                    context_id=context_id if "context_id" in locals() else None,
                    task_id=task_id if "task_id" in locals() else None,
                )
                error_status = TaskStatus(
                    state=TaskState.failed,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    message=error_message,
                )
                error_event = TaskStatusUpdateEvent(
                    context_id=context_id if "context_id" in locals() else None,
                    task_id=task_id if "task_id" in locals() else None,
                    status=error_status,
                    final=True,
                    metadata={"code": "request_processing_error", "message": str(e)},
                )
                await event_queue.enqueue_event(error_event)

    async def _process_agent_request(
        self,
        query: str,
        request_payload: Optional[A2ARequestPayload],
        task_id: str,
        context_id: str,
        a2a_context=None,
        event_queue=None,
        extension_context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Process agent request - directly use ii-agent session management"""
        try:
            logger.debug(f"[A2A Task {task_id}] Starting agent processing")
            overall_start = time.perf_counter()

            request_payload = request_payload or A2ARequestPayload()
            existing_session: Optional[SessionRecord] = await session_registry.get(
                context_id
            )

            tool_args: dict[str, Any] = {}
            if existing_session and existing_session.tool_args:
                tool_args.update(existing_session.tool_args)
            tool_args = _deep_merge_dict(tool_args, request_payload.tool_args)

            session_uuid = self._resolve_session_uuid(context_id)
            session_user_id = self._resolve_session_user_id(
                request_payload, existing_session, context_id
            )
            if session_user_id and not request_payload.user.user_id:
                request_payload.user.user_id = session_user_id

            sandbox_user_id = (
                request_payload.user.user_id
                or (existing_session.sandbox_user_id if existing_session else None)
                or self.config.a2a_sandbox_user_id
                or f"a2a-{context_id}"
            )

            preferred_sandbox_id = request_payload.sandbox.sandbox_id or (
                existing_session.sandbox_id
                if request_payload.sandbox.reuse and existing_session
                else None
            )

            llm_config = self._get_default_llm_config()

            # Get shared resources
            resource_start = time.perf_counter()
            await resource_pool.get_llm_client("default", llm_config)
            container_workspace = (
                self.config.workspace_path
                if self.config.use_container_workspace
                else None
            )
            workspace_manager = await resource_pool.get_workspace_manager(
                self.config.workspace_root,
                container_workspace=container_workspace,
            )
            resource_elapsed = time.perf_counter() - resource_start
            logger.info(
                "[A2A Task %s] Core resources ready in %.2fs",
                task_id,
                resource_elapsed,
            )

            # Create or reuse sandbox
            sandbox_start = time.perf_counter()
            sandbox_reused = False
            sandbox_reuse_failure: Optional[str] = None
            sandbox_repo = SandboxRepository()
            if preferred_sandbox_id:
                try:
                    logger.info(
                        "[A2A Task %s] Reusing sandbox %s",
                        task_id,
                        preferred_sandbox_id,
                    )
                    async with get_db_session_local() as db:
                        sandbox_record = await sandbox_repo.get_by_provider_id(
                            db, preferred_sandbox_id
                        )
                    if sandbox_record:
                        sandbox = await E2BSandboxManager.connect(
                            sandbox_id=str(sandbox_record.id),
                            session_id=str(session_uuid),
                            provider_sandbox_id=preferred_sandbox_id,
                        )
                    else:
                        sandbox = await E2BSandboxManager.init(
                            session_id=str(session_uuid)
                        )
                    sandbox_reused = True
                except Exception as exc:
                    logger.warning(
                        "[A2A Task %s] Failed to reuse sandbox %s: %s. "
                        "Falling back to new sandbox.",
                        task_id,
                        preferred_sandbox_id,
                        exc,
                    )
                    sandbox_reuse_failure = str(exc)
                    sandbox = await E2BSandboxManager.init(
                        session_id=str(session_uuid)
                    )
            else:
                sandbox = await E2BSandboxManager.init(
                    session_id=str(session_uuid)
                )
            self._update_sandbox_extension_context(
                extension_context,
                reuse_requested=bool(request_payload.sandbox.reuse),
                reuse_attempted=bool(preferred_sandbox_id),
                reuse_granted=sandbox_reused,
                sandbox_id=getattr(sandbox, "provider_sandbox_id", None)
                or preferred_sandbox_id
                or "",
                sandbox_user_id=sandbox_user_id,
                fallback_reason=sandbox_reuse_failure,
            )
            sandbox_elapsed = time.perf_counter() - sandbox_start
            logger.info(
                "[A2A Task %s] Sandbox ready in %.2fs (reuse=%s)",
                task_id,
                sandbox_elapsed,
                bool(preferred_sandbox_id),
            )

            # Set up MCP tools (with timeout control)
            try:
                credential, credential_source = self._resolve_sandbox_credential(
                    request_payload=request_payload,
                    context_id=context_id,
                )
                if credential_source:
                    logger.info(
                        "[A2A Task %s] Resolved sandbox credential from %s",
                        task_id,
                        credential_source,
                    )

                mcp_port = self.config.mcp.port
                sandbox_url = await sandbox.expose_port(mcp_port)

                # Use timeout control for MCP connection
                await asyncio.wait_for(
                    self._setup_mcp_tools(
                        sandbox_url,
                        self.config.tool_server_url,
                        credential=credential,
                    ),
                    timeout=30.0,
                )
                logger.debug(f"MCP tools configured for task: {task_id}")
            except asyncio.TimeoutError:
                logger.warning(
                    f"MCP connection timeout for task {task_id}, continuing without MCP"
                )
            except Exception as e:
                logger.warning(f"Failed to set tool server URL for task {task_id}: {e}")

            # Create event stream adapter
            runtime_trace_enabled = bool(
                extension_context and extension_context.get("runtime_trace")
            )
            event_stream_adapter = (
                EventStreamAdapter(
                    event_queue=event_queue,
                    context_id=context_id,
                    task_id=task_id,
                    runtime_trace_enabled=runtime_trace_enabled,
                )
                if event_queue
                else None
            )

            # Key mapping: A2A context_id -> ii-agent session_id
            # This way requests with the same context_id will reuse ii-agent session state and history
            agent_start = time.perf_counter()
            agent_task = await self._prepare_agent_task(
                session_uuid=session_uuid,
                session_user_id=session_user_id,
            )

            # Build SessionInfo and create V1 agent
            session_info = await self._get_session_info(session_uuid)
            agent = await self.agent_service_instance.create_agent_v1(
                session_info=session_info,
                llm_config=llm_config,
                workspace_manager=workspace_manager,
                agent_type=AgentType.GENERAL,
                tool_args=tool_args,
                metadata=request_payload.metadata,
            )
            agent_elapsed = time.perf_counter() - agent_start
            logger.info(
                "[A2A Task %s] Agent created in %.2fs",
                task_id,
                agent_elapsed,
            )

            # Execute agent with streaming
            logger.debug(f"[A2A Task {task_id}] Running agent")
            execution_start = time.perf_counter()
            v1_event_stream = await agent.arun(
                query,
                stream=True,
                stream_events=True,
                run_id=str(agent_task.id),
                yield_run_output=False,
            )

            # Convert V1 events to RealtimeEvents and forward to A2A EventStreamAdapter
            async for event in v1_event_stream:
                realtime_event = convert_agent_event_to_realtime(
                    event=event, session_id=str(session_uuid)
                )
                if realtime_event and event_stream_adapter:
                    await event_stream_adapter.add_event(realtime_event)

            execution_elapsed = time.perf_counter() - execution_start
            logger.info(f"[A2A Task {task_id}] Agent execution completed")
            logger.info(
                "[A2A Task %s] Agent execution finished in %.2fs",
                task_id,
                execution_elapsed,
            )

            # Delayed sandbox cleanup
            try:
                timeout_seconds = (
                    request_payload.sandbox.timeout_seconds
                    if request_payload.sandbox.timeout_seconds is not None
                    else 15 * 60
                )
                await sandbox.set_timeout(timeout_seconds)
            except Exception as e:
                logger.warning(f"Failed to schedule sandbox timeout: {e}")

            try:
                await session_registry.update_from_payload(
                    context_id=context_id,
                    sandbox_id=sandbox.provider_sandbox_id,
                    sandbox_user_id=sandbox_user_id,
                    payload=request_payload,
                    merged_tool_args=tool_args,
                )
            except Exception as exc:
                logger.warning(
                    "[A2A Task %s] Failed to update session registry: %s",
                    task_id,
                    exc,
                    exc_info=True,
                )
            total_elapsed = time.perf_counter() - overall_start
            logger.info(
                "[A2A Task %s] Total processing time %.2fs",
                task_id,
                total_elapsed,
            )

        except Exception as e:
            logger.error(
                f"[A2A Task {task_id}] Error in agent processing: {e}", exc_info=True
            )
            try:
                await session_registry.remove(context_id)
            except Exception as cleanup_exc:
                logger.warning(
                    "[A2A Task %s] Failed to clear session registry after error: %s",
                    task_id,
                    cleanup_exc,
                )
            # Send error event through event_queue
            if event_queue:
                error_message = Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.agent,
                    parts=[
                        Part(
                            root=TextPart(
                                text=f"Error processing agent request: {str(e)}"
                            )
                        )
                    ],
                    context_id=context_id,
                    task_id=task_id,
                )
                error_status = TaskStatus(
                    state=TaskState.failed,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    message=error_message,
                )
                error_event = TaskStatusUpdateEvent(
                    context_id=context_id,
                    task_id=task_id,
                    status=error_status,
                    final=True,
                    metadata={"code": "agent_processing_error", "message": str(e)},
                )
                await event_queue.enqueue_event(error_event)

    def _get_default_llm_config(self) -> LLMConfig:
        """Resolve default LLM configuration for A2A requests."""
        llm_configs = getattr(self.config, "llm_configs", {})
        llm_config = llm_configs.get("default")
        if llm_config is None:
            raise ValueError(
                "Default LLM configuration is missing; cannot initialize agent."
            )
        if isinstance(llm_config, LLMConfig):
            return llm_config
        try:
            return LLMConfig.model_validate(llm_config)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("Default LLM configuration is invalid.") from exc

    def _resolve_session_uuid(self, context_id: str) -> uuid.UUID:
        """Convert context_id to UUID, falling back to deterministic UUID5."""
        if not context_id:
            raise ValueError("A2A request is missing context_id.")
        try:
            return uuid.UUID(context_id)
        except ValueError:
            derived_uuid = uuid.uuid5(uuid.NAMESPACE_URL, context_id)
            logger.debug(
                "Context %s is not a valid UUID; derived %s for session_id.",
                context_id,
                derived_uuid,
            )
            return derived_uuid

    def _resolve_session_user_id(
        self,
        request_payload: A2ARequestPayload,
        existing_session: Optional[SessionRecord],
        context_id: str,
    ) -> Optional[str]:
        """Determine which user_id should back the persistent session."""
        if request_payload.user.user_id:
            logger.info(
                "Using user_id from A2A metadata: %s",
                request_payload.user.user_id,
            )
            return request_payload.user.user_id
        if existing_session and existing_session.user and existing_session.user.user_id:
            logger.info(
                "Reusing user_id %s from existing session (context_id: %s)",
                existing_session.user.user_id,
                context_id,
            )
            return existing_session.user.user_id
        if getattr(self.config, "a2a_default_session_user_id", None):
            logger.info(
                "Falling back to configured a2a_default_session_user_id: %s",
                self.config.a2a_default_session_user_id,
            )
            return self.config.a2a_default_session_user_id
        logger.info(
            "Falling back to configured a2a_sandbox_user_id: %s",
            self.config.a2a_sandbox_user_id,
        )
        return self.config.a2a_sandbox_user_id

    async def _get_session_info(self, session_uuid: uuid.UUID) -> SessionInfo:
        """Fetch SessionInfo for the given session."""
        async with get_db_session_local() as db:
            session_info = await self._build_session_service().find_session_by_id_info(
                db, session_uuid
            )
        if session_info is None:
            raise ValueError(f"Session {session_uuid} not found")
        return session_info

    async def _prepare_agent_task(
        self,
        *,
        session_uuid: uuid.UUID,
        session_user_id: Optional[str],
    ) -> AgentRunTask:
        """Ensure session exists and create an AgentRunTask record."""
        if not session_user_id:
            raise ValueError(
                "A2A request is missing user_id and no fallback (a2a_default_session_user_id or a2a_sandbox_user_id) is configured; cannot create session."
            )

        await self._ensure_session_user_exists(session_user_id)

        async with get_db_session_local() as db:
            try:
                await self._build_session_service().ensure_session_exists(
                    db, session_uuid, session_user_id
                )
            except ValueError as exc:
                raise ValueError(
                    f"Failed to create or fetch session for user {session_user_id}: {exc}"
                ) from exc

            repo = AgentRunTaskRepository()
            agent_task = await repo.create(db, session_id=session_uuid)
            await db.commit()

        return agent_task

    async def _ensure_session_user_exists(self, user_id: str) -> None:
        """Create a service user on demand if it doesn't exist."""
        async with get_db_session_local() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            if result.scalar_one_or_none():
                return

            email = getattr(self.config, "a2a_default_session_user_email", None)
            resolved_email: Optional[str] = None

            if email:
                if "{user_id}" in email:
                    try:
                        resolved_email = email.format(user_id=user_id)
                    except Exception:  # pragma: no cover - defensive fallback
                        logger.warning(
                            "Failed to format a2a_default_session_user_email with user_id; "
                            "falling back to synthesized email."
                        )
                        resolved_email = None
                else:
                    email_lookup = await db.execute(
                        select(User).where(User.email == email)
                    )
                    existing_email_user = email_lookup.scalar_one_or_none()
                    if existing_email_user and existing_email_user.id != user_id:
                        logger.info(
                            "Configured a2a_default_session_user_email already in use by %s; "
                            "falling back to synthesized email for user %s.",
                            existing_email_user.id,
                            user_id,
                        )
                        resolved_email = None
                    else:
                        resolved_email = email

            if not resolved_email:
                resolved_email = f"{user_id}@a2a.local"
            else:
                email_conflict_check = await db.execute(
                    select(User).where(User.email == resolved_email)
                )
                conflict_user = email_conflict_check.scalar_one_or_none()
                if conflict_user and conflict_user.id != user_id:
                    logger.info(
                        "Resolved email %s already associated with %s; "
                        "switching to synthesized email for user %s.",
                        resolved_email,
                        conflict_user.id,
                        user_id,
                    )
                    resolved_email = f"{user_id}@a2a.local"

            user = User(
                id=user_id,
                email=resolved_email,
                role="service",
                is_active=True,
                credits=getattr(self.config, "default_user_credits", 0.0),
                bonus_credits=0.0,
            )
            db.add(user)

    async def _setup_mcp_tools(
        self,
        sandbox_url: str,
        tool_server_url: str,
        credential: Optional[dict[str, Any]] = None,
    ):
        """Helper method to set up MCP tools"""
        async with MCPClient(sandbox_url) as client:
            if credential is None:
                logger.warning(
                    "Skipping MCP tool server configuration because credential is missing."
                )
                return
            await client.set_credential(credential)
            await client.set_tool_server_url(tool_server_url)

    def _resolve_sandbox_credential(
        self,
        request_payload: A2ARequestPayload,
        context_id: str,
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Resolve sandbox credential with basic validation and auditing."""

        def _sanitize_key(value: Optional[str]) -> Optional[str]:
            if value is None:
                return None
            trimmed = value.strip()
            return trimmed or None

        request_api_key = _sanitize_key(request_payload.user.api_key)

        if request_payload.user.api_key and request_api_key is None:
            logger.warning(
                "A2A request provided an empty sandbox apiKey; falling back to server configuration."
            )

        if request_api_key:
            credential = {
                "session_id": context_id,
                "user_api_key": request_api_key,
            }
            if request_payload.user.user_id:
                credential["user_id"] = request_payload.user.user_id
            if request_payload.user.extra:
                credential.update(request_payload.user.extra)

            hashed = hashlib.sha256(request_api_key.encode("utf-8")).hexdigest()[:12]
            logger.info(
                "[A2A] Using request-provided sandbox credential (digest=%s)",
                hashed,
            )
            return credential, "request metadata"

        config_api_key = _sanitize_key(self.config.a2a_sandbox_api_key)
        if config_api_key:
            credential = {
                "session_id": context_id,
                "user_api_key": config_api_key,
            }
            if self.config.a2a_sandbox_user_id:
                credential["user_id"] = self.config.a2a_sandbox_user_id

            hashed = hashlib.sha256(config_api_key.encode("utf-8")).hexdigest()[:12]
            logger.info(
                "[A2A] Using server-configured sandbox credential (digest=%s)",
                hashed,
            )
            return credential, "server configuration"

        logger.warning(
            "A2A sandbox API key is not configured; skipping MCP credential setup."
        )
        return None, None

    @staticmethod
    def _update_sandbox_extension_context(
        extension_context: Optional[dict[str, Any]],
        *,
        reuse_requested: bool,
        reuse_attempted: bool,
        reuse_granted: bool,
        sandbox_id: str,
        sandbox_user_id: Optional[str],
        fallback_reason: Optional[str],
    ) -> None:
        """Update extension metadata with actual sandbox reuse outcome."""

        if not extension_context or "sandbox_reuse" not in extension_context:
            return

        sandbox_info = extension_context.setdefault("sandbox_reuse", {})
        sandbox_info["reuse_requested"] = reuse_requested
        sandbox_info["reuse_attempted"] = reuse_attempted
        sandbox_info["reuse_granted"] = reuse_granted
        sandbox_info["sandbox_id"] = sandbox_id
        if sandbox_user_id is not None:
            sandbox_info["sandbox_user_id"] = sandbox_user_id
        if fallback_reason:
            sandbox_info["fallback_reason"] = fallback_reason
            append_extension_issue(
                extension_context,
                uri=SANDBOX_REUSE_EXTENSION_URI,
                code="sandbox_reuse_fallback",
                detail=fallback_reason,
            )


def _deep_merge_dict(
    base: dict[str, Any], incoming: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Recursively merge dictionaries, returning a new dict."""
    if not incoming:
        return dict(base)

    merged = dict(base)
    for key, value in incoming.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged
