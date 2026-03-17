"""Optional sub-application mounting helpers."""

from __future__ import annotations

import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def mount_fastmcp_server(app: FastAPI, mount_path: str = "/mcp") -> None:
    """Mount the FastMCP server for ChatGPT integration."""
    try:
        from ii_agent.integrations.mcp_sse.fastmcp_server import mount_to_fastapi

        mount_to_fastapi(app, mount_path)
    except Exception as exc:
        logger.warning("Failed to mount FastMCP server: %s", exc, exc_info=True)


def mount_a2a_server(app: FastAPI, mount_path: str = "/a2a") -> None:
    """Mount the embedded A2A server as a sub-application."""
    try:
        from ii_agent.integrations.a2a.__main__ import (
            create_a2a_asgi_app,
            resolve_agent_card_base_url,
        )
        from ii_agent.integrations.a2a.config import A2AConfig

        a2a_config = A2AConfig()
        a2a_asgi = create_a2a_asgi_app(a2a_config)
        app.mount(mount_path, a2a_asgi)
        logger.info("Mounted embedded A2A server at %s", mount_path)
        card_base = resolve_agent_card_base_url(a2a_config)
        logger.info(
            "Embedded A2A Agent Card available at %s/.well-known/agent-card.json",
            card_base.rstrip("/"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to mount embedded A2A server: %s", exc, exc_info=True)
