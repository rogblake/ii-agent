"""Tests for centralized LLM invocation telemetry in Model base class.

Telemetry was moved from scattered handler-level _record_llm_invocation_best_effort
calls into Model._record_llm_invocation, called from aprocess_response_stream.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agent.runtime.models.base import Model
from ii_agent.agent.runtime.models.message import Message
from ii_agent.agent.runtime.models.metrics import Metrics
from ii_agent.agent.runtime.models.response import ModelResponse


@dataclass
class _ConcreteModel(Model):
    id: str = "test-model"

    async def ainvoke(self, *args, **kwargs) -> ModelResponse:
        return ModelResponse(role="assistant", content="ok")

    async def ainvoke_stream(self, *args, **kwargs) -> AsyncIterator[ModelResponse]:
        yield ModelResponse(role="assistant", content="streaming")

    def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
        return ModelResponse(role="assistant", content=str(response))

    def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
        return ModelResponse(role="assistant", content=str(response), is_delta=True)


@asynccontextmanager
async def _noop_db_cm():
    db = MagicMock()
    db.commit = AsyncMock()
    yield db


def _make_run_response(**overrides):
    defaults = dict(
        run_id="run-1",
        session_id="session-1",
        user_id="user-1",
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


@pytest.mark.asyncio
async def test_record_llm_invocation_writes_row_on_success():
    model = _ConcreteModel()
    model.llm_invocation_repo = MagicMock()
    model.llm_invocation_repo.create = AsyncMock()

    settlement = MagicMock(total_charged=Decimal("1.5"))
    metrics = Metrics(input_tokens=100, output_tokens=50, duration=0.5)

    with patch("ii_agent.core.db.manager.get_db_session_local", _noop_db_cm):
        await model._record_llm_invocation(
            run_response=_make_run_response(),
            metrics=metrics,
            settlement_result=settlement,
        )

    model.llm_invocation_repo.create.assert_called_once()
    kwargs = model.llm_invocation_repo.create.call_args.kwargs
    assert kwargs["prompt_tokens"] == 100
    assert kwargs["completion_tokens"] == 50
    assert kwargs["latency_ms"] == 500
    assert kwargs["credits_charged"] == 1.5
    assert kwargs["success"] is True
    assert kwargs["error_code"] is None


@pytest.mark.asyncio
async def test_record_llm_invocation_writes_row_on_failure():
    model = _ConcreteModel()
    model.llm_invocation_repo = MagicMock()
    model.llm_invocation_repo.create = AsyncMock()

    with patch("ii_agent.core.db.manager.get_db_session_local", _noop_db_cm):
        await model._record_llm_invocation(
            run_response=_make_run_response(),
            metrics=None,
            settlement_result=None,
            success=False,
            error_code="ModelProviderError",
        )

    kwargs = model.llm_invocation_repo.create.call_args.kwargs
    assert kwargs["prompt_tokens"] == 0
    assert kwargs["completion_tokens"] == 0
    assert kwargs["latency_ms"] is None
    assert kwargs["credits_charged"] is None
    assert kwargs["success"] is False
    assert kwargs["error_code"] == "ModelProviderError"


@pytest.mark.asyncio
async def test_record_llm_invocation_is_best_effort():
    """Telemetry failure must not propagate."""
    model = _ConcreteModel()
    model.llm_invocation_repo = MagicMock()
    model.llm_invocation_repo.create = AsyncMock(side_effect=RuntimeError("db down"))

    with patch("ii_agent.core.db.manager.get_db_session_local", _noop_db_cm):
        # Should not raise
        await model._record_llm_invocation(
            run_response=_make_run_response(),
            metrics=Metrics(input_tokens=10, output_tokens=5),
        )


@pytest.mark.asyncio
async def test_record_llm_invocation_skips_when_no_run_response():
    model = _ConcreteModel()
    model.llm_invocation_repo = MagicMock()
    model.llm_invocation_repo.create = AsyncMock()

    await model._record_llm_invocation(
        run_response=None,
        metrics=Metrics(input_tokens=10),
    )

    model.llm_invocation_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_record_llm_invocation_skips_when_no_user_id():
    model = _ConcreteModel()
    model.llm_invocation_repo = MagicMock()
    model.llm_invocation_repo.create = AsyncMock()

    await model._record_llm_invocation(
        run_response=_make_run_response(user_id=""),
        metrics=Metrics(input_tokens=10),
    )

    model.llm_invocation_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_record_llm_invocation_without_billing():
    """Non-billed calls should still record telemetry (credits_charged=None)."""
    model = _ConcreteModel()
    model.llm_invocation_repo = MagicMock()
    model.llm_invocation_repo.create = AsyncMock()

    metrics = Metrics(input_tokens=200, output_tokens=80, duration=1.0)

    with patch("ii_agent.core.db.manager.get_db_session_local", _noop_db_cm):
        await model._record_llm_invocation(
            run_response=_make_run_response(),
            metrics=metrics,
            settlement_result=None,
        )

    kwargs = model.llm_invocation_repo.create.call_args.kwargs
    assert kwargs["prompt_tokens"] == 200
    assert kwargs["completion_tokens"] == 80
    assert kwargs["credits_charged"] is None
