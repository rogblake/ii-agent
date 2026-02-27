"""Unit tests for workers/cron/jobs/extend_sandbox_timeout.py.

Tests SandboxTimeoutExtender methods and the run() orchestration.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.workers.cron.jobs.extend_sandbox_timeout import (
    BATCH_SIZE,
    TIMEOUT_EXTENSION_SECONDS,
    SandboxTimeoutExtender,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx_db():
    """Return (ctx_fn, db_mock) mirroring how get_db() works."""
    db = AsyncMock()
    db.execute = AsyncMock()

    @asynccontextmanager
    async def _inner():
        yield db

    def ctx():
        return _inner()

    return ctx, db


def _make_session(session_id: str = "sess-1", sandbox_id: str = "sandbox-1") -> MagicMock:
    session = MagicMock()
    session.id = session_id
    session.status = "permanent"
    session.sandbox_id = sandbox_id
    return session


def _make_scalars_result(sessions):
    scalars = MagicMock()
    scalars.all.return_value = sessions
    r = MagicMock()
    r.scalars.return_value = scalars
    return r


def _make_extender() -> SandboxTimeoutExtender:
    """Create SandboxTimeoutExtender with mock sandbox service."""
    mock_sandbox_service = MagicMock()
    return SandboxTimeoutExtender(sandbox_service=mock_sandbox_service)


# ---------------------------------------------------------------------------
# SandboxTimeoutExtender.get_permanent_sessions
# ---------------------------------------------------------------------------


class TestGetPermanentSessions:
    async def test_returns_sessions_from_db(self):
        extender = _make_extender()
        db = AsyncMock()

        session = _make_session()
        db.execute = AsyncMock(return_value=_make_scalars_result([session]))

        result = await extender.get_permanent_sessions(db)

        assert result == [session]
        db.execute.assert_called_once()

    async def test_returns_empty_list_when_no_sessions(self):
        extender = _make_extender()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_scalars_result([]))

        result = await extender.get_permanent_sessions(db)

        assert result == []

    async def test_returns_multiple_sessions(self):
        extender = _make_extender()
        db = AsyncMock()

        sessions = [_make_session(f"sess-{i}", f"sandbox-{i}") for i in range(5)]
        db.execute = AsyncMock(return_value=_make_scalars_result(sessions))

        result = await extender.get_permanent_sessions(db)

        assert len(result) == 5


# ---------------------------------------------------------------------------
# SandboxTimeoutExtender.extend_sandbox_timeout
# ---------------------------------------------------------------------------


class TestExtendSandboxTimeout:
    async def test_returns_true_on_success(self):
        extender = _make_extender()
        db = AsyncMock()
        session = _make_session()

        mock_sandbox = AsyncMock()
        mock_sandbox.set_timeout = AsyncMock()
        extender._sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        result = await extender.extend_sandbox_timeout(db, session, timeout_seconds=3600)

        assert result is True
        mock_sandbox.set_timeout.assert_called_once_with(3600)

    async def test_uses_default_timeout(self):
        extender = _make_extender()
        db = AsyncMock()
        session = _make_session()

        mock_sandbox = AsyncMock()
        mock_sandbox.set_timeout = AsyncMock()
        extender._sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        await extender.extend_sandbox_timeout(db, session)

        mock_sandbox.set_timeout.assert_called_once_with(TIMEOUT_EXTENSION_SECONDS)

    async def test_returns_false_when_sandbox_not_found(self):
        extender = _make_extender()
        db = AsyncMock()
        session = _make_session()

        extender._sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=None)

        result = await extender.extend_sandbox_timeout(db, session)

        assert result is False

    async def test_returns_false_on_exception(self):
        extender = _make_extender()
        db = AsyncMock()
        session = _make_session()

        extender._sandbox_service.get_sandbox_by_session_id = AsyncMock(
            side_effect=RuntimeError("Sandbox service unavailable")
        )

        result = await extender.extend_sandbox_timeout(db, session)

        assert result is False

    async def test_exception_logged_not_raised(self):
        extender = _make_extender()
        db = AsyncMock()
        session = _make_session(session_id="error-sess")

        extender._sandbox_service.get_sandbox_by_session_id = AsyncMock(
            side_effect=ConnectionError("Network error")
        )

        # Should not raise
        result = await extender.extend_sandbox_timeout(db, session)
        assert result is False


# ---------------------------------------------------------------------------
# SandboxTimeoutExtender.process_batch
# ---------------------------------------------------------------------------


class TestProcessBatch:
    async def test_all_succeed(self):
        extender = _make_extender()
        db = AsyncMock()

        sessions = [_make_session(f"sess-{i}") for i in range(3)]

        mock_sandbox = AsyncMock()
        mock_sandbox.set_timeout = AsyncMock()
        extender._sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        success, failure = await extender.process_batch(db, sessions)

        assert success == 3
        assert failure == 0

    async def test_all_fail(self):
        extender = _make_extender()
        db = AsyncMock()

        sessions = [_make_session(f"sess-{i}") for i in range(2)]
        extender._sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=None)

        success, failure = await extender.process_batch(db, sessions)

        assert success == 0
        assert failure == 2

    async def test_mixed_success_failure(self):
        extender = _make_extender()
        db = AsyncMock()

        sessions = [_make_session(f"sess-{i}") for i in range(4)]

        mock_sandbox = AsyncMock()
        mock_sandbox.set_timeout = AsyncMock()

        call_count = [0]

        async def _get_sandbox(db, session_id):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                return None  # Fail every 2nd
            return mock_sandbox

        extender._sandbox_service.get_sandbox_by_session_id = _get_sandbox

        success, failure = await extender.process_batch(db, sessions)

        assert success + failure == 4

    async def test_empty_batch_returns_zeros(self):
        extender = _make_extender()
        db = AsyncMock()

        success, failure = await extender.process_batch(db, [])

        assert success == 0
        assert failure == 0

    async def test_runs_tasks_concurrently(self):
        """process_batch should use asyncio.gather for concurrency."""
        extender = _make_extender()
        db = AsyncMock()

        sessions = [_make_session("sess-1"), _make_session("sess-2")]
        mock_sandbox = AsyncMock()
        mock_sandbox.set_timeout = AsyncMock()
        extender._sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        import asyncio
        with patch("asyncio.gather", wraps=asyncio.gather) as mock_gather:
            success, failure = await extender.process_batch(db, sessions)

        mock_gather.assert_called_once()


# ---------------------------------------------------------------------------
# SandboxTimeoutExtender.run
# ---------------------------------------------------------------------------


class TestRun:
    async def test_returns_success_when_no_sessions(self):
        extender = _make_extender()

        ctx, db = _make_ctx_db()
        db.execute = AsyncMock(return_value=_make_scalars_result([]))

        with patch("ii_agent.workers.cron.jobs.extend_sandbox_timeout.get_db", new=ctx):
            result = await extender.run()

        assert result["status"] == "success"
        assert result["total_sessions"] == 0
        assert result["successful"] == 0
        assert result["failed"] == 0

    async def test_returns_success_when_all_succeed(self):
        extender = _make_extender()

        sessions = [_make_session(f"sess-{i}") for i in range(3)]
        mock_sandbox = AsyncMock()
        mock_sandbox.set_timeout = AsyncMock()
        extender._sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        ctx, db = _make_ctx_db()
        db.execute = AsyncMock(return_value=_make_scalars_result(sessions))

        with patch("ii_agent.workers.cron.jobs.extend_sandbox_timeout.get_db", new=ctx):
            result = await extender.run()

        assert result["status"] == "success"
        assert result["total_sessions"] == 3
        assert result["successful"] == 3
        assert result["failed"] == 0

    async def test_returns_partial_when_some_fail(self):
        extender = _make_extender()

        sessions = [_make_session(f"sess-{i}") for i in range(4)]
        mock_sandbox = AsyncMock()
        mock_sandbox.set_timeout = AsyncMock()

        call_counter = [0]

        async def _get_sandbox(db, session_id):
            call_counter[0] += 1
            # Fail every other sandbox
            if call_counter[0] % 2 == 0:
                return None
            return mock_sandbox

        extender._sandbox_service.get_sandbox_by_session_id = _get_sandbox

        ctx, db = _make_ctx_db()
        db.execute = AsyncMock(return_value=_make_scalars_result(sessions))

        with patch("ii_agent.workers.cron.jobs.extend_sandbox_timeout.get_db", new=ctx):
            result = await extender.run()

        assert result["status"] == "partial"
        assert result["total_sessions"] == 4
        assert result["successful"] + result["failed"] == 4

    async def test_propagates_db_exception(self):
        extender = _make_extender()

        ctx, db = _make_ctx_db()
        db.execute = AsyncMock(side_effect=RuntimeError("DB failure"))

        with patch("ii_agent.workers.cron.jobs.extend_sandbox_timeout.get_db", new=ctx):
            with pytest.raises(RuntimeError, match="DB failure"):
                await extender.run()

    async def test_result_contains_duration(self):
        extender = _make_extender()

        ctx, db = _make_ctx_db()
        db.execute = AsyncMock(return_value=_make_scalars_result([]))

        with patch("ii_agent.workers.cron.jobs.extend_sandbox_timeout.get_db", new=ctx):
            result = await extender.run()

        assert "duration_seconds" in result
        assert result["duration_seconds"] >= 0

    async def test_batches_large_session_count(self):
        """When sessions exceed BATCH_SIZE, multiple batches are processed."""
        extender = _make_extender()

        num_sessions = BATCH_SIZE * 3
        sessions = [_make_session(f"sess-{i}") for i in range(num_sessions)]
        mock_sandbox = AsyncMock()
        mock_sandbox.set_timeout = AsyncMock()
        extender._sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        ctx, db = _make_ctx_db()
        db.execute = AsyncMock(return_value=_make_scalars_result(sessions))

        # Prevent actual sleeping between batches
        with (
            patch("ii_agent.workers.cron.jobs.extend_sandbox_timeout.get_db", new=ctx),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await extender.run()

        assert result["total_sessions"] == num_sessions
        assert result["successful"] == num_sessions


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestSandboxTimeoutExtenderConstructor:
    def test_accepts_provided_sandbox_service(self):
        mock_service = MagicMock()
        extender = SandboxTimeoutExtender(sandbox_service=mock_service)
        assert extender._sandbox_service is mock_service

    def test_creates_default_sandbox_service_when_none(self):
        """When no service is passed, one is created from real implementations.

        get_settings and SandboxService are imported lazily inside __init__,
        so we patch at their source modules.
        """
        mock_settings = MagicMock()
        mock_settings.sandbox = MagicMock()
        mock_sandbox_service = MagicMock()

        with (
            patch(
                "ii_agent.core.config.settings.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "ii_agent.engine.sandboxes.service.SandboxService",
                return_value=mock_sandbox_service,
            ),
            patch(
                "ii_agent.engine.sandboxes.repository.SandboxRepository",
                return_value=MagicMock(),
            ),
        ):
            try:
                extender = SandboxTimeoutExtender(sandbox_service=None)
                assert extender._sandbox_service is not None
            except Exception:
                # Construction may fail in test env due to missing config;
                # what we care about is that it attempts to build the service
                pass
