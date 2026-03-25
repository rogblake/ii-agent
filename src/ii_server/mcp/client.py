from __future__ import annotations

from typing import Any, Dict

import httpx
from fastmcp.client import Client

from ii_server.logger import get_logger

DEFAULT_TIMEOUT = 1800

logger = get_logger(__name__)


class MCPClient(Client):
    def __init__(self, server_url: str, **args):
        logger.info("Initializing MCPClient with server URL: %s", server_url)
        self.server_url = server_url
        self.http_session: httpx.AsyncClient | None = None
        mcp_url = server_url + "/mcp/"
        super().__init__(mcp_url, **args)

    async def __aenter__(self):
        self.http_session = httpx.AsyncClient()
        return await super().__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.http_session:
            await self.http_session.aclose()
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def register_custom_mcp(self, mcp_config: Dict[str, Any]) -> Dict[str, Any]:
        if not self.http_session:
            raise RuntimeError("MCPClient is not initialized")

        response = await self.http_session.post(
            self.server_url + "/custom-mcp",
            json=mcp_config,
            timeout=DEFAULT_TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Failed to register custom mcp: {response.text}")
        return response.json()

    async def register_codex(self) -> Dict[str, Any]:
        if not self.http_session:
            raise RuntimeError("MCPClient is not initialized")

        response = await self.http_session.post(
            self.server_url + "/register-codex",
            timeout=DEFAULT_TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Failed to register codex: {response.text}")
        return response.json()
