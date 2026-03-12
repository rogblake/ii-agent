"""Agent execution logic for MCP SSE server."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from fastmcp import FastMCP

from ii_agent.agent.runtime.agent_controller import AgentController
from ii_agent.agent.types import AgentType
from ii_agent.core.config.llm_config import LLMConfig
from sqlalchemy import select

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.repository import EventRepository
from ii_agent.agent.runs.models import RunStatus
from ii_agent.agent.runs.repository import AgentRunTaskRepository
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.auth.users.models import User
from ii_agent.agent.sandboxes.base import SandboxManager
from ii_agent.agent.sandboxes.e2b import E2BSandboxManager
from ii_agent.agent.application.beta.hooks.session_hooks import register_default_session_hooks
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_tool.mcp.client import MCPClient

from .events import MCPEventCollector

if TYPE_CHECKING:
    import socketio
    from ii_agent.core.container import ServiceContainer

logger = logging.getLogger(__name__)


# ============================================================================
# Background Agent Queue
# ============================================================================

@dataclass
class AgentTask:
    """Task to be processed by the background agent worker."""
    agent_controller: AgentController
    prompt: str
    session_id: uuid.UUID
    sandbox_url: str


# Global queue for agent tasks
_agent_queue: asyncio.Queue[AgentTask] = None
_worker_task: asyncio.Task = None


def get_agent_queue() -> asyncio.Queue[AgentTask]:
    """Get or create the global agent queue."""
    global _agent_queue
    if _agent_queue is None:
        _agent_queue = asyncio.Queue()
    return _agent_queue


async def _agent_worker():
    """Background worker that processes agent tasks from the queue."""
    queue = get_agent_queue()
    logger.info("Agent background worker started")

    while True:
        try:
            # Wait for a task from the queue
            task = await queue.get()
            logger.info(f"Processing agent task for session {task.session_id}")

            try:
                # Run the agent asynchronously
                await task.agent_controller.run_agent_async(
                    instruction=task.prompt,
                    resume=True
                )
                logger.info(f"Agent task completed for session {task.session_id}")
            except Exception as e:
                logger.error(f"Agent task failed for session {task.session_id}: {e}", exc_info=True)
            finally:
                queue.task_done()

        except asyncio.CancelledError:
            logger.info("Agent background worker cancelled")
            break
        except Exception as e:
            logger.error(f"Agent worker error: {e}", exc_info=True)


async def start_agent_worker():
    """Start the background agent worker if not already running."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_agent_worker())
        logger.info("Started agent background worker")


async def enqueue_agent_task(
    agent_controller: AgentController,
    prompt: str,
    session_id: uuid.UUID,
    sandbox_url: str
):
    """Add an agent task to the queue for background processing."""
    # Ensure worker is running
    await start_agent_worker()

    queue = get_agent_queue()
    task = AgentTask(
        agent_controller=agent_controller,
        prompt=prompt,
        session_id=session_id,
        sandbox_url=sandbox_url
    )
    await queue.put(task)
    logger.info(f"Enqueued agent task for session {session_id}")


def _get_default_llm_config(config) -> LLMConfig:
    """Get default LLM configuration."""
    llm_configs = getattr(config, "llm_configs", {})
    llm_config = llm_configs.get("default")
    if llm_config is None:
        raise ValueError("Default LLM configuration is missing")
    if isinstance(llm_config, LLMConfig):
        return llm_config
    return LLMConfig.model_validate(llm_config)


async def _ensure_session_user_exists(user_id: str, config) -> None:
    """Create a service user on demand if it doesn't exist."""
    async with get_db_session_local() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        if result.scalar_one_or_none():
            return

        email = getattr(config, "mcp_default_session_user_email", None)
        resolved_email: Optional[str] = None

        if email:
            if "{user_id}" in email:
                try:
                    resolved_email = email.format(user_id=user_id)
                except Exception:
                    logger.warning(
                        "Failed to format mcp_default_session_user_email with user_id; "
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
                        "Configured mcp_default_session_user_email already in use by %s; "
                        "falling back to synthesized email for user %s.",
                        existing_email_user.id,
                        user_id,
                    )
                    resolved_email = None
                else:
                    resolved_email = email

        if not resolved_email:
            resolved_email = f"{user_id}@mcp.local"
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
                resolved_email = f"{user_id}@mcp.local"

        user = User(
            id=user_id,
            email=resolved_email,
            role="service",
            is_active=True,
            credits=getattr(config, "default_user_credits", 0.0),
            bonus_credits=0.0,
        )
        db.add(user)
        await db.commit()


async def _pre_configure_mcp_server(config, sandbox: SandboxManager, session_id: uuid.UUID) -> bool:
    """Pre-configure MCP server in sandbox before loading tools."""
    mcp_port = config.mcp.port
    sandbox_url = await sandbox.expose_port(mcp_port)

    api_key = config.sandbox.e2b_api_key or config.a2a_sandbox_api_key

    if not api_key:
        logger.warning("No sandbox API key configured. MCP tools may not be available.")
        return False

    credentials = {
        "session_id": str(session_id),
        "user_api_key": api_key,
        "host_url": "-".join(sandbox_url.split("-")[1:]),
    }

    max_retries = 5
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            async with MCPClient(sandbox_url) as client:
                await client.set_credential(credentials)
                await client.set_tool_server_url(config.tool_server_url)
                await client.ping()
                tools = await client.list_tools()
                logger.info(f"MCP server ready with {len(tools)} tools after {attempt + 1} attempts")
                return True
        except Exception as e:
            logger.warning(f"MCP server not ready (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)

    logger.error("Failed to configure MCP server after all retries")
    return False


async def init_agent(
    prompt: str,
    context_id: Optional[str] = None,
    agent_type: AgentType = AgentType.WEBSITE_BUILD,
    mcp_server: Optional[FastMCP] = None,
    user_id: Optional[str] = None,
    cache_request: Optional[callable] = None,
    container: Optional[ServiceContainer] = None,
    sio: Optional[socketio.AsyncServer] = None,
) -> Tuple[AgentController, str, uuid.UUID]:
    """
    Initialize the II-Agent controller.

    Args:
        prompt: The task or question for the agent to handle
        context_id: Optional session ID for multi-turn conversations
        agent_type: Agent type to use for the task
        mcp_server: Optional MCP server for streaming progress notifications
        user_id: Optional user ID for the request
        cache_request: Optional function to cache requests to prevent duplicates
        container: Optional service container for dependency injection
        sio: Optional Socket.IO server for broadcasting to web clients

    Returns:
        Tuple of (AgentController, sandbox_url, session_id)
    """
    # Resolve services from container or fall back to globals
    if container is not None:
        _config = container.config
        _session_service = container.session_service
        _agent_service = container.agent_service
    else:
        from ii_agent.core.config.settings import get_settings
        from ii_agent.sessions.service import SessionService
        from ii_agent.sessions.repository import SessionRepository
        from ii_agent.agent.application.agent_service import AgentService
        from ii_agent.agent.runs.service import AgentRunService
        from ii_agent.core.storage.client import storage
        from ii_agent.agent.sandboxes.repository import SandboxRepository
        _config = get_settings()
        _session_service = SessionService(
            config=_config,
            session_repo=SessionRepository(),
            event_repo=EventRepository(),
            agent_run_service=AgentRunService(repo=AgentRunTaskRepository(), config=_config),
            file_store=storage,
            sandbox_repo=SandboxRepository(),
        )
        _agent_service = AgentService(config=_config, file_store=storage)

    if sio is None:
        from ii_agent.app import sio

    # Generate or reuse session ID
    if context_id:
        try:
            session_id = uuid.UUID(context_id)
        except ValueError:
            # context_id is not a valid UUID, generate a new one
            logger.warning(f"Invalid context_id '{context_id}', generating new session ID")
            session_id = uuid.uuid4()
    else:
        session_id = uuid.uuid4()

    if not isinstance(agent_type, AgentType):
        agent_type = AgentType(agent_type)

    if cache_request:
        cache_request(prompt, context_id, str(session_id), agent_type.value)

    if not user_id:
        raise ValueError(
            "MCP request is missing user_id and no fallback "
        )

    # Ensure user exists in database
    await _ensure_session_user_exists(user_id, _config)

    # Ensure session exists using session service
    try:
        async with get_db_session_local() as db:
            await _session_service.ensure_session_exists(db, session_id, user_id)
    except ValueError as exc:
        raise ValueError(
            f"Failed to create or fetch session for user {user_id}: {exc}"
        ) from exc

    # Abort any existing RUNNING tasks for this session to prevent duplicates
    async with get_db_session_local() as db:
        repo = AgentRunTaskRepository()
        existing_tasks = await repo.get_by_session_id(db, session_id=session_id)
        for task in existing_tasks:
            if task.status == RunStatus.RUNNING:
                task.status = RunStatus.ABORTED
                logger.info(f"Aborted existing RUNNING task {task.id} for session {session_id}")
        await db.commit()

    # Get or create sandbox via E2BSandboxManager
    sandbox = await E2BSandboxManager.init(session_id=str(session_id))
    logger.info(f"Sandbox ready: {sandbox.provider_sandbox_id}")

    # Pre-configure MCP server in sandbox
    mcp_configured = await _pre_configure_mcp_server(_config, sandbox, session_id)
    if not mcp_configured:
        logger.warning("MCP server configuration failed, tools may be limited")

    # Get sandbox URL for the widget (VS Code server)
    sandbox_url = None
    try:
        sandbox_url = await sandbox.expose_port(_config.vscode_port)
        logger.info(f"Sandbox VS Code URL: {sandbox_url}")
    except Exception as e:
        logger.warning(f"Failed to get sandbox URL: {e}")

    # Create workspace manager
    container_workspace = Path(_config.workspace_path) if _config.use_container_workspace else None
    workspace_manager = WorkspaceManager(
        Path(_config.workspace_root),
        container_workspace=container_workspace,
    )

    # Get default LLM config
    llm_config = _get_default_llm_config(_config)

    # Update session name from prompt and set is_public to True
    from ii_agent.sessions.title_service import SessionTitleService
    _title_service = SessionTitleService(config=_config.session_title)
    session_name, title_pending = _title_service.build_initial_title(
        prompt or "",
        80,
    )
    async with get_db_session_local() as db:
        if prompt:
            await _session_service.update_session_title_state(
                db,
                session_id,
                name=session_name,
                title_pending=title_pending,
            )

        # Update agent_type and llm_setting_id in database
        await _session_service.update_session_agent_type(db, session_id, agent_type.value)
        await _session_service.update_session_llm_setting_id(db, session_id, "default")

        if agent_type == AgentType.SLIDE or agent_type == AgentType.SLIDE_NANO_BANANA:
            logger.info(f"Setting session {session_id} to public")
            await _session_service.set_session_public(db, str(session_id), str(user_id), True)

    if prompt and title_pending:
        _title_service.schedule_title_update(str(session_id), prompt)

    # Create event collector with MCP server for streaming notifications
    # Also pass Socket.IO server for broadcasting to web clients
    event_collector = MCPEventCollector(
        mcp_server=mcp_server,
        session_id=session_id,
        sio=sio,
    )

    # Send sandbox ready notification early so widget can display iframe immediately
    if sandbox_url:
        await event_collector.send_sandbox_ready_notification(sandbox_url, str(session_id))

    # Create agent run task and save user message event
    async with get_db_session_local() as db:
        repo = AgentRunTaskRepository()
        agent_task = await repo.create(db, session_id=session_id)

        # Save user message as the first event
        user_event = RealtimeEvent(
            session_id=session_id,
            type=EventType.USER_MESSAGE,
            content={
                "text": prompt,
                "files": [],
            },
        )
        event_repo = EventRepository()
        user_db_event = await event_repo.save(db, session_id, user_event)
        user_db_event.run_id = agent_task.id

        await db.commit()

    # Create agent controller
    logger.info(f"Creating agent controller for session {session_id}")
    agent_controller = await _agent_service.create_agent(
        agent_task=agent_task,
        llm_config=llm_config,
        sandbox=sandbox,
        workspace_manager=workspace_manager,
        event_stream=event_collector,
        agent_type=agent_type,
        tool_args=None,
        user_id=user_id
    )
    logger.info(f"Agent controller created, starting execution with prompt: {prompt[:100]}...")

    return agent_controller, sandbox_url, session_id

    

def run_agent_internal(
    agent_controller: AgentController,
    prompt: str,
    session_id: uuid.UUID,
    sandbox_url: str,
) -> Dict[str, Any]:
    """Run the agent with the given prompt (sync version).
    """
    # Run agent
    agent_controller.run_agent(instruction=prompt, resume=True)

    # Build metadata for widget
    metadata = {
        "session_id": str(session_id),
        "sandbox_url": sandbox_url,
    }

    return metadata
