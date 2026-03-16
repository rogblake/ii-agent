from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class FakeNestedTransaction:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        self._db.begin_nested_calls += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDB:
    def __init__(self):
        self.begin_nested_calls = 0

    def begin_nested(self):
        return FakeNestedTransaction(self)


@pytest.mark.asyncio
async def test_query_handler_telemetry_is_best_effort():
    from ii_agent.agent.socket.command.query_handler import UserQueryHandler

    handler = UserQueryHandler(
        event_stream=SimpleNamespace(publish=AsyncMock()),
        container=MagicMock(),
    )
    handler._llm_invocation_repo = SimpleNamespace(
        create=AsyncMock(side_effect=RuntimeError("telemetry failed"))
    )
    db = FakeDB()

    await handler._record_llm_invocation_best_effort(
        db,
        session_id="s1",
        user_id="u1",
        request_kind="agent_query",
    )

    assert db.begin_nested_calls == 1


@pytest.mark.asyncio
async def test_continue_handler_telemetry_is_best_effort():
    from ii_agent.agent.socket.command.continue_run_handler import ContinueRunHandler

    container = MagicMock()
    container.config = MagicMock()

    with patch(
        "ii_agent.agent.socket.command.continue_run_handler.AgentFactory"
    ) as mock_factory:
        mock_factory.return_value = MagicMock()
        handler = ContinueRunHandler(
            event_stream=SimpleNamespace(publish=AsyncMock()),
            container=container,
        )

    handler._llm_invocation_repo = SimpleNamespace(
        create=AsyncMock(side_effect=RuntimeError("telemetry failed"))
    )
    db = FakeDB()

    await handler._record_llm_invocation_best_effort(
        db,
        session_id="s1",
        user_id="u1",
        request_kind="agent_continue",
    )

    assert db.begin_nested_calls == 1
