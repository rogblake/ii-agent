"""Interceptors used by the IIAgentA2AClient implementation."""

from __future__ import annotations

from typing import Any

import httpx
from a2a.client import ClientCallContext, ClientCallInterceptor
from a2a.extensions.common import HTTP_EXTENSION_HEADER
from a2a.types import AgentCard

__all__ = ["ExtensionsHeaderInterceptor"]


class ExtensionsHeaderInterceptor(ClientCallInterceptor):
    """Ensure message-level extensions propagate to HTTP headers for negotiation."""

    _STATE_KEY = "a2a_extensions"

    async def intercept(
        self,
        method_name: str,
        request_payload: dict[str, Any],
        http_kwargs: dict[str, Any],
        agent_card: AgentCard | None,
        context: ClientCallContext | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Attach X-A2A-Extensions header based on payload content."""
        if method_name not in {"message/send", "message/stream"}:
            return request_payload, http_kwargs

        extensions = self._extract_extensions(request_payload)
        if not extensions:
            return request_payload, http_kwargs

        updated_kwargs = dict(http_kwargs or {})
        headers = dict(updated_kwargs.get("headers") or {})
        headers[HTTP_EXTENSION_HEADER] = ", ".join(sorted(extensions))
        updated_kwargs["headers"] = headers

        if context is not None:
            state = context.state.setdefault(self._STATE_KEY, {})
            state.setdefault("requested", extensions.copy())
            hooks = dict(updated_kwargs.get("hooks") or {})
            response_hooks = list(hooks.get("response") or [])
            response_hooks.append(self._build_response_hook(context))
            hooks["response"] = response_hooks
            updated_kwargs["hooks"] = hooks

        return request_payload, updated_kwargs

    @staticmethod
    def _extract_extensions(payload: dict[str, Any]) -> list[str]:
        """Pull extension URIs from standard JSON-RPC send payload."""
        params = payload.get("params")
        if not isinstance(params, dict):
            return []
        message = params.get("message")
        if not isinstance(message, dict):
            return []
        extensions = message.get("extensions")
        if not isinstance(extensions, list):
            return []
        cleaned = [
            str(ext).strip()
            for ext in extensions
            if isinstance(ext, (str, int, float)) and str(ext).strip()
        ]
        # Preserve original order but drop duplicates
        seen: set[str] = set()
        ordered: list[str] = []
        for ext in cleaned:
            if ext not in seen:
                seen.add(ext)
                ordered.append(ext)
        return ordered

    @staticmethod
    def _split_header(value: str | None) -> list[str]:
        if not value:
            return []
        return [token.strip() for token in value.split(",") if token and token.strip()]

    def _build_response_hook(self, context: ClientCallContext) -> Any:
        async def _capture(response: httpx.Response) -> None:
            values = self._split_header(response.headers.get(HTTP_EXTENSION_HEADER))
            if not values:
                return
            state = context.state.setdefault(self._STATE_KEY, {})
            activated = set(state.get("activated") or [])
            activated.update(values)
            state["activated"] = sorted(activated)

        return _capture
