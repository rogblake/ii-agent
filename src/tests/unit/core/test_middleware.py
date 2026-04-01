import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from ii_agent.core.exceptions import IIAgentError
from ii_agent.core.middleware import (
    exception_logging_middleware,
    ii_agent_error_handler,
    request_tracing_middleware,
)


def _make_request(path: str = "/test", headers: dict | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [
            (k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in (headers or {}).items()
        ],
        "query_string": b"",
    }

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, _receive)


@pytest.mark.asyncio
async def test_request_tracing_adds_request_headers():
    request = _make_request(headers={"x-request-id": "req-123"})

    async def _call_next(_request):
        return Response(content=b"ok", status_code=200)

    response = await request_tracing_middleware(request, _call_next)

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"


@pytest.mark.asyncio
async def test_request_tracing_returns_500_on_unhandled_exception():
    request = _make_request()

    async def _call_next(_request):
        raise RuntimeError("boom")

    response = await request_tracing_middleware(request, _call_next)

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_exception_logging_middleware_handles_http_exception():
    request = _make_request()

    async def _call_next(_request):
        raise HTTPException(status_code=400, detail="bad")

    response = await exception_logging_middleware(request, _call_next)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_ii_agent_error_handler_maps_error_payload():
    class DemoError(IIAgentError):
        status_code = 409

    request = _make_request(path="/x")
    response = await ii_agent_error_handler(request, DemoError("conflict"))

    payload = json.loads(response.body)
    assert response.status_code == 409
    assert payload["detail"] == "conflict"
    assert payload["error"] == "demo"
