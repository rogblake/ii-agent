"""Widget resource and tool handlers for MCP SSE server."""

from ii_agent.auth.users.waitlist_repository import WaitlistRepository
import hashlib
import logging
import time
import uuid
from typing import TYPE_CHECKING, Dict, Tuple

from mcp import types as mcp_types

from fastmcp.server.dependencies import get_http_headers

from .agent import init_agent, enqueue_agent_task
from .models import (
    WIDGET_MIME_TYPE,
    WIDGETS_BY_URI,
    get_run_task_result,
    get_widget_html,
    get_widget_tool_meta,
)
from ii_agent.engine.types import AgentType
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.sessions.service import SessionService
from ii_agent.sessions.repository import SessionRepository
from ii_agent.realtime.events.repository import EventRepository
from ii_agent.integrations.connectors.service import ConnectorService
from ii_agent.auth.users.service import UserService
from ii_agent.auth.users.repository import UserRepository, APIKeyRepository
from ii_agent.engine.agents.agent_run_service import AgentRunService
from ii_agent.engine.agents.repository import AgentRunTaskRepository
from ii_agent.engine.sandboxes.repository import SandboxRepository
from ii_agent.core.storage.client import storage
from ii_agent.auth.jwt_handler import jwt_handler
from ii_agent.core.config.settings import get_settings

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Request deduplication cache: {request_hash: (session_id, timestamp)}
_request_cache: Dict[str, Tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 10  # Cache requests for 10 seconds


def _generate_request_hash(
    prompt: str,
    context_id: str = None,
    agent_type: str = None
) -> str:
    """Generate a hash for request deduplication.

    Args:
        prompt: The user prompt
        context_id: Optional context/session ID
        agent_type: Optional agent type for the request

    Returns:
        SHA256 hash of the request parameters
    """
    key = f"{prompt}:{context_id or ''}:{agent_type or ''}"
    return hashlib.sha256(key.encode()).hexdigest()


def _cleanup_expired_cache():
    """Remove expired entries from the request cache."""
    current_time = time.time()
    expired_keys = [
        key for key, (_, timestamp) in _request_cache.items()
        if current_time - timestamp > _CACHE_TTL_SECONDS
    ]
    for key in expired_keys:
        del _request_cache[key]


def _check_duplicate_request(
    prompt: str,
    context_id: str = None,
    agent_type: str = None
) -> Tuple[bool, str]:
    """Check if this is a duplicate request.

    Args:
        prompt: The user prompt
        context_id: Optional context/session ID
        agent_type: Optional agent type for the request

    Returns:
        Tuple of (is_duplicate, session_id)
        - is_duplicate: True if this request was recently processed
        - session_id: The session_id from the previous request (if duplicate)
    """
    _cleanup_expired_cache()

    request_hash = _generate_request_hash(prompt, context_id, agent_type)

    if request_hash in _request_cache:
        session_id, _ = _request_cache[request_hash]
        logger.warning(
            f"Duplicate request detected for prompt: '{prompt[:50]}...' "
            f"(context_id: {context_id}, agent_type: {agent_type}). "
            f"Returning existing session: {session_id}"
        )
        return True, session_id

    return False, None


def _cache_request(
    prompt: str,
    context_id: str,
    session_id: str,
    agent_type: str = None
):
    """Cache a request to prevent duplicates.

    Args:
        prompt: The user prompt
        context_id: Optional context/session ID
        session_id: The session ID created for this request
        agent_type: Optional agent type for the request
    """
    request_hash = _generate_request_hash(prompt, context_id, agent_type)
    _request_cache[request_hash] = (session_id, time.time())
    logger.debug(f"Cached request with hash {request_hash[:8]}... for session {session_id}")


def create_read_resource_handler() -> callable:
    """Create ReadResourceRequest handler."""

    async def _handle_read_resource(
        req: mcp_types.ReadResourceRequest,
    ) -> mcp_types.ServerResult:
        """Handle ReadResourceRequest - return widget HTML content."""
        uri = str(req.params.uri) if req.params else None

        # Parse URI to extract base path and query params
        # URI format: ui://widgets/main.html?session_id=xxx
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(uri)
        base_uri = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        query_params = parse_qs(parsed.query)
        session_id = query_params.get("session_id", [""])[0]

        widget = WIDGETS_BY_URI.get(base_uri)

        if widget is None:
            return mcp_types.ServerResult(
                mcp_types.ReadResourceResult(
                    contents=[],
                    _meta={"error": f"Unknown resource: {uri}"},
                )
            )

        # Generate widget HTML with session_id injected
        widget_html = get_widget_html(session_id)

        contents = [
            mcp_types.TextResourceContents(
                uri=widget.template_uri,
                mimeType=WIDGET_MIME_TYPE,
                text=widget_html,
                _meta=get_widget_tool_meta(widget),
            )
        ]
        return mcp_types.ServerResult(
            mcp_types.ReadResourceResult(
                contents=contents,
                _meta=get_widget_tool_meta(widget),
            )
        )

    return _handle_read_resource


def create_call_tool_handler(mcp_server: "FastMCP") -> callable:
    """Create CallToolRequest handler with access to MCP server for notifications."""

    async def _handle_call_tool(
        req: mcp_types.CallToolRequest,
    ) -> mcp_types.ServerResult:
        """Handle CallToolRequest - execute the requested tool."""
        tool_name = req.params.name if req.params else None
        
        # Extract user info from bearer token via database lookup
        headers = get_http_headers()
        auth_header = headers.get("authorization", "")
        user_id = None
        user_email = None
        user_access_token = None
        logger.info(f"CallToolRequest received: {tool_name}, auth_header: {auth_header}")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            logger.info(f"CallToolRequest received: {tool_name}, token: {token}")
            async with get_db_session_local() as db:
                user_info = await ConnectorService(config=get_settings()).get_user_by_mcp_token(db, token=token)
            if user_info:
                user_id = user_info.get("user_id")
                user_email = user_info.get("user_email")

                # Get user details and generate access token (similar to Google login)
                if user_id:
                    async with get_db_session_local() as db:
                        user = await UserService(config=get_settings(), user_repo=UserRepository(), waitlist_repo=WaitlistRepository(), api_key_repo=APIKeyRepository()).get_user_by_id(db, user_id)
                    if user:
                        user_access_token = jwt_handler.create_access_token(
                            user_id=str(user.id),
                            email=str(user.email),
                            role=str(user.role) if user.role else "user",
                        )
        
        logger.info(f"CallToolRequest received: {tool_name}, user_id: {user_id}, user_email: {user_email}")

        if tool_name not in ("run_task", "refresh_session_status"):
            return mcp_types.ServerResult(
                mcp_types.CallToolResult(
                    content=[
                        mcp_types.TextContent(
                            type="text",
                            text=f"Unknown tool: {tool_name}",
                        )
                    ],
                    isError=True,
                )
            )

        # Extract arguments
        args = req.params.arguments or {}
        
        # Handle refresh_session_status TOOL
        if tool_name == "refresh_session_status":
            session_id = args.get("session_id")
            if not session_id:
                return mcp_types.ServerResult(
                    mcp_types.CallToolResult(
                        content=[
                            mcp_types.TextContent(
                                type="text",
                                text="Missing required parameter: session_id",
                            )
                        ],
                        isError=True,
                    )
                )

            tool_meta = get_run_task_result(session_id)

            # Query session status from database
            try:
                session_uuid = uuid.UUID(session_id)
                async with get_db_session_local() as db:
                    _cfg = get_settings()
                    session = await SessionService(
                        config=_cfg,
                        session_repo=SessionRepository(),
                        event_repo=EventRepository(),
                        agent_run_service=AgentRunService(repo=AgentRunTaskRepository(), config=_cfg),
                        file_store=storage,
                        sandbox_repo=SandboxRepository(),
                    ).get_session_by_id(db, session_uuid)

                if not session:
                    return mcp_types.ServerResult(
                        mcp_types.CallToolResult(
                            content=[
                                mcp_types.TextContent(
                                    type="text",
                                    text=f"Session {session_id} not found",
                                )
                            ],
                            isError=True,
                        )
                    )

                # Query events from database
                async with get_db_session_local() as db:
                    event_repo = EventRepository()
                    events = await event_repo.get_by_session(db, session_uuid)

                # Convert events to a serializable format
                events_data = []
                for event in events:
                    events_data.append({
                        "id": event.id,
                        "type": event.type,
                        "content": event.content,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    })

                return mcp_types.ServerResult(
                    mcp_types.CallToolResult(
                        content=[
                            mcp_types.TextContent(
                                type="text",
                                text=f"Session status: {session.status}",
                            )
                        ],
                        structuredContent={
                            "user_id": user_id,
                            "token": user_access_token,
                            "session_id": session_id,
                            "sandbox_id": session.sandbox_id,
                            "public_url": session.public_url,
                            "events": events_data
                        },
                        _meta=tool_meta,
                    )
                )
            except ValueError as e:
                logger.error(f"Invalid session_id format: {e}")
                return mcp_types.ServerResult(
                    mcp_types.CallToolResult(
                        content=[
                            mcp_types.TextContent(
                                type="text",
                                text=f"Invalid session_id format: {session_id}",
                            )
                        ],
                        isError=True,
                    )
                )
            except Exception as e:
                logger.error(f"Error refreshing session status: {e}", exc_info=True)
                return mcp_types.ServerResult(
                    mcp_types.CallToolResult(
                        content=[
                            mcp_types.TextContent(
                                type="text",
                                text=f"Error refreshing session status: {str(e)}",
                            )
                        ],
                        isError=True,
                    )
                )
        
        
        prompt = args.get("prompt")
        context_id = args.get("context_id")
        agent_type_value = args.get("agent_type") or AgentType.WEBSITE_BUILD.value

        if not prompt:
            return mcp_types.ServerResult(
                mcp_types.CallToolResult(
                    content=[
                        mcp_types.TextContent(
                            type="text",
                            text="Missing required parameter: prompt",
                        )
                    ],
                    isError=True,
                )
            )

        try:
            agent_type_enum = AgentType(agent_type_value)
        except ValueError:
            return mcp_types.ServerResult(
                mcp_types.CallToolResult(
                    content=[
                        mcp_types.TextContent(
                            type="text",
                            text=(
                                "Invalid agent_type. Use one of: "
                                "website_build, slide, slide_nano_banana."
                            ),
                        )
                    ],
                    isError=True,
                )
            )

        allowed_agent_types = {
            AgentType.WEBSITE_BUILD,
            AgentType.SLIDE,
            AgentType.SLIDE_NANO_BANANA,
        }
        if agent_type_enum not in allowed_agent_types:
            return mcp_types.ServerResult(
                mcp_types.CallToolResult(
                    content=[
                        mcp_types.TextContent(
                            type="text",
                            text=(
                                "Unsupported agent_type. Use one of: "
                                "website_build, slide, slide_nano_banana."
                            ),
                        )
                    ],
                    isError=True,
                )
            )

        # Check for duplicate requests
        is_duplicate, existing_session_id = _check_duplicate_request(
            prompt,
            context_id,
            agent_type_enum.value
        )

        if is_duplicate:
            # Return the existing session instead of creating a new one
            logger.info(
                f"Returning cached session {existing_session_id} for duplicate request"
            )
            tool_meta = get_run_task_result(existing_session_id)

            return mcp_types.ServerResult(
                mcp_types.CallToolResult(
                    content=[
                        mcp_types.TextContent(
                            type="text",
                            text=f"II-Agent is processing your request with session_id: {existing_session_id}",
                        )
                    ],
                    structuredContent={
                        "user_id": user_id,
                        "token": user_access_token,
                        "session_id": str(existing_session_id),
                        "agent_type": agent_type_enum.value,
                        "status": "processing"
                    },
                    _meta=tool_meta,
                )
            )

        try:
            # Cache this request to prevent duplicates
            # Initialize the agent and get session_id (this sets up sandbox, etc.)
            agent_controller, sandbox_url, session_id = await init_agent(
                prompt=prompt,
                context_id=context_id,
                agent_type=agent_type_enum,
                mcp_server=mcp_server,
                cache_request=_cache_request,
                user_id=user_id
            )
            _cache_request(prompt, context_id, str(session_id), agent_type_enum.value)

            # Enqueue the agent task for background processing
            # This returns immediately without waiting for the agent to complete
            await enqueue_agent_task(
                agent_controller=agent_controller,
                prompt=prompt,
                session_id=session_id,
                sandbox_url=sandbox_url
            )

            logger.info(f"Agent task enqueued for session {session_id}, returning immediately")

            # Get widget metadata
            tool_meta = get_run_task_result(session_id)


            return mcp_types.ServerResult(
                mcp_types.CallToolResult(
                    content=[
                        mcp_types.TextContent(
                            type="text",
                            text=f"II-Agent is processing your request with session_id: {session_id}",
                        )
                    ],

                    structuredContent={
                        "user_id": user_id,
                        "token": user_access_token,
                        "session_id": str(session_id),
                        "agent_type": agent_type_enum.value,
                        "status": "processing"
                    },
                    _meta=tool_meta,
                )
            )

        except Exception as e:
            logger.error(f"Agent initialization error: {e}", exc_info=True)
            return mcp_types.ServerResult(
                mcp_types.CallToolResult(
                    content=[
                        mcp_types.TextContent(
                            type="text",
                            text=f"Error: {str(e)}",
                        )
                    ],
                    isError=True,
                )
            )

    return _handle_call_tool
