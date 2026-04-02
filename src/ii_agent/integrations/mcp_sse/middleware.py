"""ASGI middleware for MCP SSE server."""

from starlette.types import ASGIApp, Receive, Scope, Send


class AcceptHeaderMiddleware:
    """Middleware to ensure the Accept header includes required MIME types.

    The MCP protocol requires clients to accept both application/json and
    text/event-stream. Some clients (like ChatGPT) may not include these
    in their Accept header, so this middleware adds them automatically.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            # Get the current headers
            headers = dict(scope.get("headers", []))
            accept_header = headers.get(b"accept", b"").decode("utf-8")

            # Parse accept types
            accept_types = [t.strip() for t in accept_header.split(",") if t.strip()]

            # Check what's missing
            has_json = any(t.startswith("application/json") for t in accept_types)
            has_sse = any(t.startswith("text/event-stream") for t in accept_types)

            # Add missing types
            if not has_json or not has_sse:
                # Always set the complete required Accept header
                new_accept = "application/json, text/event-stream"

                # Create new headers list
                new_headers = [(k, v) for k, v in scope.get("headers", []) if k.lower() != b"accept"]
                new_headers.append((b"accept", new_accept.encode("utf-8")))

                # Create new scope with updated headers
                scope = dict(scope)
                scope["headers"] = new_headers

        await self.app(scope, receive, send)
