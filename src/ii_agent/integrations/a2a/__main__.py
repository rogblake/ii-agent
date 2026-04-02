"""A2A Server main entry point for II Agent platform."""

import logging
import os
import socket
from importlib import metadata
from urllib.parse import urlparse

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentExtension, AgentSkill
from starlette.types import ASGIApp, Receive, Scope, Send

from ii_agent.integrations.a2a import __version__ as A2A_INTEGRATION_VERSION
from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor
from ii_agent.integrations.a2a.config import A2AConfig
from ii_agent.integrations.a2a.constants import (
    RUNTIME_TRACE_ARTIFACT_NAMES,
    RUNTIME_TRACE_EXTENSION_URI,
    SANDBOX_REUSE_EXTENSION_URI,
    SESSION_CONTEXT_EXTENSION_URI,
    USER_AUTH_HANDOFF_EXTENSION_URI,
)

logger = logging.getLogger(__name__)


def build_app(config: A2AConfig) -> A2AStarletteApplication:
    """Build the A2A application.

    Args:
        config: Loaded A2A configuration
    """
    skills = [
        AgentSkill(
            id="general_assistance",
            name="General Assistance",
            description="Provide general AI assistance with various tasks including coding, analysis, and problem-solving",
            input_modes=["text/plain", "application/json"],
            output_modes=["text/plain", "application/json", "text/markdown"],
            tags=["assistance", "general", "ai", "coding", "analysis"],
            examples=[
                "Help me write a Python function to process data",
                "Analyze this code and suggest improvements",
                "Explain how machine learning algorithms work",
                "Help me debug this error in my application",
            ],
        ),
        AgentSkill(
            id="code_generation",
            name="Code Generation",
            description="Generate code in various programming languages for different purposes",
            input_modes=["text/plain", "application/json"],
            output_modes=["text/plain", "application/json", "text/markdown"],
            tags=["code", "generation", "programming", "development"],
            examples=[
                "Write a REST API in Python using FastAPI",
                "Create a React component for user authentication",
                "Generate SQL queries for database operations",
                "Write unit tests for this function",
            ],
        ),
        AgentSkill(
            id="data_analysis",
            name="Data Analysis",
            description="Analyze data, create visualizations, and provide insights",
            input_modes=["text/plain", "application/json"],
            output_modes=["text/plain", "application/json", "text/markdown"],
            tags=["data", "analysis", "visualization", "insights"],
            examples=[
                "Analyze this dataset and create visualizations",
                "Help me understand the patterns in this data",
                "Create a report based on these metrics",
                "Suggest data preprocessing steps",
            ],
        ),
        AgentSkill(
            id="problem_solving",
            name="Problem Solving",
            description="Help solve complex problems across various domains",
            input_modes=["text/plain", "application/json"],
            output_modes=["text/plain", "application/json", "text/markdown"],
            tags=["problem", "solving", "logic", "reasoning"],
            examples=[
                "Help me design a system architecture",
                "Solve this algorithmic problem",
                "Troubleshoot this technical issue",
                "Plan a project timeline and milestones",
            ],
        ),
    ]

    extensions = [
        AgentExtension(
            uri=SESSION_CONTEXT_EXTENSION_URI,
            description=(
                "Accepts enriched session metadata under the `ii-agent` key, "
                "including tool configuration, sandbox preferences, and user hints."
            ),
            params={
                "metadata_key": "ii-agent",
                "sections": ["tool_args", "sandbox", "user"],
            },
        ),
        AgentExtension(
            uri=SANDBOX_REUSE_EXTENSION_URI,
            description=(
                "Honors sandbox reuse hints such as timeout, template, and sandbox IDs "
                "for long-running coding sessions."
            ),
            params={
                "metadata_key": "ii-agent.sandbox",
                "fields": ["reuse", "timeout", "template_id", "sandbox_id"],
            },
        ),
        AgentExtension(
            uri=USER_AUTH_HANDOFF_EXTENSION_URI,
            description=(
                "Allows clients to forward user-level credentials for downstream tool access."
            ),
            params={
                "metadata_key": "ii-agent.user",
                "fields": ["user_id", "api_key"],
            },
        ),
        AgentExtension(
            uri=RUNTIME_TRACE_EXTENSION_URI,
            description=(
                "Streams structured TaskArtifactUpdateEvent entries for agent thoughts and tool logs."
            ),
            params={
                "artifact_names": RUNTIME_TRACE_ARTIFACT_NAMES,
                "metadata_fields": {
                    "event_type": "A2A realtime event type (e.g. AGENT_THINKING)",
                    "sequence": "Monotonic sequence number",
                    "data": "Original event payload (tokens, tool args/results, etc.)",
                    "timestamp": "Original event timestamp (epoch seconds)",
                },
            },
        ),
    ]

    card_base_url = resolve_agent_card_base_url(config)
    agent_card = AgentCard(
        name="II Agent",
        description="Intelligent Agent platform with comprehensive AI capabilities for coding, analysis, and problem-solving",
        url=f"{card_base_url.rstrip('/')}/",
        version=_resolve_integration_version(),
        protocol_version=_resolve_protocol_version(),
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["text/plain", "application/json", "text/markdown"],
        capabilities=AgentCapabilities(streaming=True, extensions=extensions),
        skills=skills,
    )

    request_handler = DefaultRequestHandler(
        agent_executor=IIAgentExecutor(),
        task_store=InMemoryTaskStore(),
        queue_manager=InMemoryQueueManager(),
    )

    return A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)


def create_a2a_asgi_app(config: A2AConfig) -> ASGIApp:
    """Build the full ASGI application (with optional auth middleware)."""

    base_app = build_app(config=config)
    asgi_app = base_app.build()

    allowed_keys = _parse_allowed_keys(config.allowed_api_keys)
    if allowed_keys:
        logger.info(
            "A2A API key authentication enabled (%d keys configured)",
            len(allowed_keys),
        )
        return A2AAuthMiddleware(asgi_app, allowed_keys=allowed_keys)

    logger.warning("No API keys configured for A2A server; authentication disabled")
    return asgi_app


def main():
    """Main entry point for the A2A server."""
    config = A2AConfig()

    log_level_value = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level_value,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    third_party_agents = config.get_third_party_agents()
    if third_party_agents:
        logger.info(
            f"Third-party A2A agents configured: {len(third_party_agents)} agents"
        )
        for agent_name, agent_config in third_party_agents.items():
            logger.info(f"  - {agent_name}: {agent_config.get('url', 'No URL')}")
    else:
        logger.info("No third-party A2A agents configured")

    asgi_app = create_a2a_asgi_app(config)

    logger.info(
        "Starting II Agent A2A Server on %s:%s (workers=%s, timeout=%ss)",
        config.server_host,
        config.server_port,
        config.max_workers,
        config.timeout,
    )
    card_base_url = resolve_agent_card_base_url(config)
    logger.info(
        "Agent Card: %s/.well-known/agent-card.json",
        card_base_url.rstrip("/"),
    )

    try:
        uvicorn.run(
            asgi_app,
            host=config.server_host,
            port=config.server_port,
            log_level=config.log_level.lower(),
            workers=config.max_workers,
            timeout_keep_alive=config.timeout,
        )
    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Shutting down A2A server gracefully.")
    finally:
        logger.info("A2A server shutdown complete.")


def _parse_allowed_keys(value: str) -> set[str]:
    """Parse comma-separated API key string into a set."""

    if not value:
        return set()

    keys = {key.strip() for key in value.split(",") if key.strip()}
    return keys


def resolve_agent_card_base_url(config: A2AConfig) -> str:
    """Derive a user-facing base URL for the agent card."""

    host_value = (config.public_base_url or "").strip() or (
        config.server_host or ""
    ).strip()
    port_value = int(config.server_port)
    default_scheme = "https" if port_value == 443 else "http"

    if host_value.startswith(("http://", "https://")):
        parsed = urlparse(host_value)
        scheme = parsed.scheme or default_scheme
        netloc = parsed.netloc or parsed.path
        if not netloc:
            netloc = _fallback_hostname()
        base = f"{scheme}://{netloc}"
        if parsed.path and parsed.path != "/":
            base = f"{base}{parsed.path.rstrip('/')}"
        return base.rstrip("/")

    if host_value.startswith("//"):
        host_value = host_value[2:]

    parsed_host = urlparse(f"{default_scheme}://{host_value}")
    hostname = parsed_host.hostname or host_value
    port = parsed_host.port or port_value
    scheme = "https" if port == 443 else default_scheme

    if not hostname or hostname in {"0.0.0.0", "::"}:
        hostname = _fallback_hostname()

    return _format_host_with_scheme(hostname, port, scheme)


def _format_host_with_scheme(hostname: str, port: int, scheme: str) -> str:
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return f"{scheme}://{hostname}"
    return f"{scheme}://{hostname}:{port}"


def _fallback_hostname() -> str:
    candidate = os.environ.get("HOSTNAME")
    if candidate:
        return candidate
    try:
        return socket.getfqdn() or socket.gethostname() or "localhost"
    except Exception:  # pragma: no cover - defensive
        return "localhost"


def _resolve_integration_version() -> str:
    version = (A2A_INTEGRATION_VERSION or "").strip()
    return version or "0.0.0"


def _resolve_protocol_version() -> str:
    try:
        return metadata.version("a2a_sdk")
    except Exception:  # pragma: no cover - metadata not installed
        return "0.3.0"


WELL_KNOWN_PUBLIC_PATHS = {
    "/.well-known/agent-card.json",
    "/.well-known/agent.json",
}


class A2AAuthMiddleware:
    """Simple API key authentication middleware for A2A endpoints."""

    def __init__(self, app: ASGIApp, allowed_keys: set[str]):
        self.app = app
        self.allowed_keys = allowed_keys

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in WELL_KNOWN_PUBLIC_PATHS:  # allow public discovery documents
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method == "OPTIONS":  # allow CORS preflight without auth
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1"): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        auth_header = headers.get("authorization")
        token = None
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        else:
            token = headers.get("x-a2a-api-key")

        if token and token in self.allowed_keys:
            await self.app(scope, receive, send)
            return

        client = scope.get("client") or (None, None)
        client_ip = client[0] if isinstance(client, tuple) else None
        logger.warning(
            "Unauthorized A2A request rejected",
            extra={"client_ip": client_ip, "path": path},
        )
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"error": "Unauthorized"}',
            }
        )


if __name__ == "__main__":
    main()
