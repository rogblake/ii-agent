"""Unit tests for cron tasks, refresh scripts, and import_waitlist (r4)."""

from __future__ import annotations

import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# refresh_free_user_credits.py
# ===========================================================================

class TestMonthlyFreeCredit:
    def test_returns_from_default_plans(self):
        from ii_agent.workers.cron.refresh_free_user_credits import (
            _monthly_free_credit_allowance,
        )

        mock_settings = MagicMock()
        mock_settings.credits.default_plans_credits = {"free": 500.0}
        mock_settings.credits.default_user_credits = 100.0

        with patch(
            "ii_agent.workers.cron.refresh_free_user_credits.get_settings",
            return_value=mock_settings,
        ):
            result = _monthly_free_credit_allowance()
            assert result == 500.0

    def test_falls_back_to_default_user_credits_when_free_plan_missing(self):
        from ii_agent.workers.cron.refresh_free_user_credits import (
            _monthly_free_credit_allowance,
        )

        mock_settings = MagicMock()
        mock_settings.credits.default_plans_credits = {}
        mock_settings.credits.default_user_credits = 250.0

        with patch(
            "ii_agent.workers.cron.refresh_free_user_credits.get_settings",
            return_value=mock_settings,
        ):
            result = _monthly_free_credit_allowance()
            assert result == 250.0


class TestRefreshFreeUserCredits:
    @pytest.mark.asyncio
    async def test_updates_users_with_none_subscription(self):
        from ii_agent.workers.cron.refresh_free_user_credits import refresh_free_user_credits

        user1 = MagicMock()
        user1.subscription_plan = None
        user1.credits = 0.0

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user1]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.credits.default_plans_credits = {"free": 300.0}
        mock_settings.credits.default_user_credits = 100.0

        with (
            patch("ii_agent.workers.cron.refresh_free_user_credits.get_db_session_local", return_value=mock_ctx),
            patch("ii_agent.workers.cron.refresh_free_user_credits.get_settings", return_value=mock_settings),
        ):
            await refresh_free_user_credits()

        assert user1.subscription_plan == "free"
        assert user1.credits == 300.0

    @pytest.mark.asyncio
    async def test_skips_users_with_correct_credits_and_plan(self):
        from ii_agent.workers.cron.refresh_free_user_credits import refresh_free_user_credits

        user1 = MagicMock()
        user1.subscription_plan = "free"
        user1.credits = 300.0

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user1]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.credits.default_plans_credits = {"free": 300.0}
        mock_settings.credits.default_user_credits = 100.0

        with (
            patch("ii_agent.workers.cron.refresh_free_user_credits.get_db_session_local", return_value=mock_ctx),
            patch("ii_agent.workers.cron.refresh_free_user_credits.get_settings", return_value=mock_settings),
        ):
            await refresh_free_user_credits()

        # User had correct plan and credits - no change should have happened
        assert user1.credits == 300.0


class TestBuildFreeUserCronJobDefinition:
    def test_returns_correct_name(self):
        from ii_agent.workers.cron.refresh_free_user_credits import build_cron_job_definition

        job = build_cron_job_definition()
        assert job.name == "ii-agent-free-credit-refresh"

    def test_default_schedule_is_monthly(self):
        from ii_agent.workers.cron.refresh_free_user_credits import (
            build_cron_job_definition,
            DEFAULT_CRON_SCHEDULE,
        )

        job = build_cron_job_definition()
        assert job.schedule == DEFAULT_CRON_SCHEDULE

    def test_custom_schedule_accepted(self):
        from ii_agent.workers.cron.refresh_free_user_credits import build_cron_job_definition

        job = build_cron_job_definition(schedule="0 0 * * 0")
        assert job.schedule == "0 0 * * 0"

    def test_command_contains_module_path(self):
        from ii_agent.workers.cron.refresh_free_user_credits import build_cron_job_definition

        job = build_cron_job_definition()
        assert "refresh_free_user_credits" in job.command


class TestInstallFreeCronJob:
    def test_calls_manager_install(self):
        from ii_agent.workers.cron.refresh_free_user_credits import install_cron_job

        mock_manager = MagicMock()
        install_cron_job(manager=mock_manager)
        mock_manager.install.assert_called_once()

    def test_dry_run_passed_to_manager(self):
        from ii_agent.workers.cron.refresh_free_user_credits import install_cron_job

        mock_manager = MagicMock()
        install_cron_job(dry_run=True, manager=mock_manager)
        call_kwargs = mock_manager.install.call_args.kwargs
        assert call_kwargs["dry_run"] is True


# ===========================================================================
# refresh_annual_subscription_credits.py
# ===========================================================================

class TestEnsureMetadataDict:
    def test_dict_returned_as_is_copy(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import (
            _ensure_metadata_dict,
        )

        meta = {"key": "value"}
        result = _ensure_metadata_dict(meta)
        assert result == meta
        # It should be a copy
        result["new"] = "thing"
        assert "new" not in meta

    def test_none_returns_empty_dict(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import (
            _ensure_metadata_dict,
        )

        assert _ensure_metadata_dict(None) == {}

    def test_non_dict_returns_empty_dict(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import (
            _ensure_metadata_dict,
        )

        assert _ensure_metadata_dict("not a dict") == {}
        assert _ensure_metadata_dict(42) == {}


class TestParseIsoDate:
    def test_valid_iso_date_with_tz(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import _parse_iso_date

        result = _parse_iso_date("2025-01-15T12:00:00+00:00")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1

    def test_none_returns_none(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import _parse_iso_date

        assert _parse_iso_date(None) is None

    def test_empty_string_returns_none(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import _parse_iso_date

        assert _parse_iso_date("") is None

    def test_invalid_format_returns_none(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import _parse_iso_date

        assert _parse_iso_date("not-a-date") is None

    def test_naive_datetime_gets_utc_tz(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import _parse_iso_date

        result = _parse_iso_date("2025-06-01T10:00:00")
        assert result is not None
        assert result.tzinfo is not None


class TestAsUtc:
    def test_none_returns_none(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import _as_utc

        assert _as_utc(None) is None

    def test_naive_datetime_gets_utc(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import _as_utc

        dt = datetime(2025, 1, 1, 12, 0, 0)
        result = _as_utc(dt)
        assert result.tzinfo is not None
        assert result.year == 2025

    def test_aware_datetime_converted_to_utc(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import _as_utc
        import pytz

        dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = _as_utc(dt)
        assert result.tzinfo.utcoffset(result).total_seconds() == 0


class TestRefreshUserCredits:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_plan_credits(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import _refresh_user_credits

        mock_user = MagicMock()
        mock_user.subscription_plan = "pro"
        mock_user.subscription_current_period_end = None
        mock_user.user_metadata = {}

        mock_settings = MagicMock()
        mock_settings.credits.default_plans_credits = {}

        with patch(
            "ii_agent.workers.cron.refresh_annual_subscription_credits.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)
            result = await _refresh_user_credits(mock_user, now=now)
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_subscription_expired(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import _refresh_user_credits

        mock_user = MagicMock()
        mock_user.subscription_plan = "pro"
        mock_user.subscription_current_period_end = datetime(2020, 1, 1, tzinfo=timezone.utc)
        mock_user.user_metadata = {}

        mock_settings = MagicMock()
        mock_settings.credits.default_plans_credits = {"pro": 500.0}

        with patch(
            "ii_agent.workers.cron.refresh_annual_subscription_credits.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)
            result = await _refresh_user_credits(mock_user, now=now)
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_already_refreshed_this_month(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import (
            _refresh_user_credits,
            REFRESH_METADATA_KEY,
        )

        now = datetime(2025, 6, 15, tzinfo=timezone.utc)
        last_refresh = datetime(2025, 6, 1, tzinfo=timezone.utc)

        mock_user = MagicMock()
        mock_user.subscription_plan = "pro"
        mock_user.subscription_current_period_end = None
        mock_user.user_metadata = {REFRESH_METADATA_KEY: last_refresh.isoformat()}

        mock_settings = MagicMock()
        mock_settings.credits.default_plans_credits = {"pro": 500.0}

        with patch(
            "ii_agent.workers.cron.refresh_annual_subscription_credits.get_settings",
            return_value=mock_settings,
        ):
            result = await _refresh_user_credits(mock_user, now=now)
            assert result is False

    @pytest.mark.asyncio
    async def test_updates_credits_and_returns_true(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import (
            _refresh_user_credits,
            REFRESH_METADATA_KEY,
        )

        now = datetime(2025, 7, 1, tzinfo=timezone.utc)

        mock_user = MagicMock()
        mock_user.subscription_plan = "pro"
        mock_user.subscription_current_period_end = None
        mock_user.user_metadata = {}

        mock_settings = MagicMock()
        mock_settings.credits.default_plans_credits = {"pro": 500.0}

        with patch(
            "ii_agent.workers.cron.refresh_annual_subscription_credits.get_settings",
            return_value=mock_settings,
        ):
            result = await _refresh_user_credits(mock_user, now=now)
            assert result is True
            assert mock_user.credits == 500.0


class TestBuildAnnualCronJobDefinition:
    def test_returns_correct_name(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import (
            build_cron_job_definition,
        )

        job = build_cron_job_definition()
        assert job.name == "ii-agent-annual-credit-refresh"

    def test_default_schedule_is_daily(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import (
            build_cron_job_definition,
            DEFAULT_CRON_SCHEDULE,
        )

        job = build_cron_job_definition()
        assert job.schedule == DEFAULT_CRON_SCHEDULE

    def test_custom_schedule_accepted(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import (
            build_cron_job_definition,
        )

        job = build_cron_job_definition(schedule="0 1 * * *")
        assert job.schedule == "0 1 * * *"

    def test_command_contains_module_path(self):
        from ii_agent.workers.cron.refresh_annual_subscription_credits import (
            build_cron_job_definition,
        )

        job = build_cron_job_definition()
        assert "refresh_annual_subscription_credits" in job.command


# ===========================================================================
# cron/tasks.py - cleanup_long_running_tasks
# ===========================================================================

class TestCleanupLongRunningTasks:
    @pytest.mark.asyncio
    async def test_runs_without_error_when_no_tasks(self):
        from ii_agent.workers.cron.tasks import cleanup_long_running_tasks

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("ii_agent.workers.cron.tasks.get_db", return_value=mock_ctx):
            await cleanup_long_running_tasks()

    @pytest.mark.asyncio
    async def test_marks_tasks_as_system_interrupted(self):
        from ii_agent.workers.cron.tasks import cleanup_long_running_tasks
        from ii_agent.agent.runs.models import RunStatus

        mock_task = MagicMock()
        mock_task.status = RunStatus.RUNNING
        mock_task.session_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_task.id = "task-1"

        # First call returns tasks, second call returns empty
        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalars.return_value.all.return_value = [mock_task]
            else:
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_event_repo = MagicMock()
        mock_event_repo.save = AsyncMock()

        with (
            patch("ii_agent.workers.cron.tasks.get_db", return_value=mock_ctx),
            patch("ii_agent.workers.cron.tasks.EventRepository", return_value=mock_event_repo),
        ):
            await cleanup_long_running_tasks()

        assert mock_task.status == RunStatus.SYSTEM_INTERRUPTED


class TestStartScheduler:
    def test_scheduler_adds_job_and_starts(self):
        from ii_agent.workers.cron.tasks import start_scheduler, scheduler

        mock_scheduler = MagicMock()
        mock_scheduler.running = False

        with patch("ii_agent.workers.cron.tasks.scheduler", mock_scheduler):
            start_scheduler()
            mock_scheduler.add_job.assert_called_once()
            mock_scheduler.start.assert_called_once()


class TestShutdownScheduler:
    def test_shuts_down_running_scheduler(self):
        from ii_agent.workers.cron.tasks import shutdown_scheduler

        mock_scheduler = MagicMock()
        mock_scheduler.running = True

        with patch("ii_agent.workers.cron.tasks.scheduler", mock_scheduler):
            shutdown_scheduler()
            mock_scheduler.shutdown.assert_called_once_with(wait=True)

    def test_does_not_shutdown_when_not_running(self):
        from ii_agent.workers.cron.tasks import shutdown_scheduler

        mock_scheduler = MagicMock()
        mock_scheduler.running = False

        with patch("ii_agent.workers.cron.tasks.scheduler", mock_scheduler):
            shutdown_scheduler()
            mock_scheduler.shutdown.assert_not_called()


# ===========================================================================
# cron/jobs/import_waitlist.py
# ===========================================================================

class TestNormaliseTzSuffix:
    def test_no_tz_suffix_unchanged(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _normalise_tz_suffix

        assert _normalise_tz_suffix("2025-01-01T00:00:00") == "2025-01-01T00:00:00"

    def test_adds_minutes_to_tz_suffix(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _normalise_tz_suffix

        result = _normalise_tz_suffix("2025-01-01T00:00:00+00")
        assert result.endswith("+0000")

    def test_negative_tz_also_normalized(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _normalise_tz_suffix

        result = _normalise_tz_suffix("2025-01-01T00:00:00-05")
        assert result.endswith("-0500")


class TestParseCreatedAt:
    def test_empty_string_returns_now(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _parse_created_at

        result = _parse_created_at("")
        assert isinstance(result, datetime)

    def test_none_returns_now(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _parse_created_at

        result = _parse_created_at(None)
        assert isinstance(result, datetime)

    def test_valid_iso_format_parsed(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _parse_created_at

        result = _parse_created_at("2025-03-15T10:30:00+00:00")
        assert result.year == 2025
        assert result.month == 3
        assert result.day == 15

    def test_naive_datetime_gets_utc(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _parse_created_at

        result = _parse_created_at("2025-01-01T00:00:00")
        assert result.tzinfo is not None

    def test_invalid_format_raises_value_error(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _parse_created_at

        with pytest.raises(ValueError):
            _parse_created_at("not-a-date-at-all")


class TestNormaliseEmail:
    def test_strips_whitespace_and_lowercases(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _normalise_email

        result = _normalise_email("  TEST@EXAMPLE.COM  ")
        assert result == "test@example.com"

    def test_none_raises_value_error(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _normalise_email

        with pytest.raises(ValueError):
            _normalise_email(None)

    def test_empty_string_raises_value_error(self):
        from ii_agent.workers.cron.jobs.import_waitlist import _normalise_email

        with pytest.raises(ValueError):
            _normalise_email("")


class TestImportWaitlist:
    @pytest.mark.asyncio
    async def test_raises_when_csv_not_found(self, tmp_path):
        from ii_agent.workers.cron.jobs.import_waitlist import import_waitlist

        non_existent = tmp_path / "missing.csv"
        with pytest.raises(FileNotFoundError):
            await import_waitlist(non_existent)

    @pytest.mark.asyncio
    async def test_raises_when_missing_required_columns(self, tmp_path):
        from ii_agent.workers.cron.jobs.import_waitlist import import_waitlist

        csv_file = tmp_path / "test.csv"
        csv_file.write_text("email\ntest@example.com\n")

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=iter([]))))
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("ii_agent.workers.cron.jobs.import_waitlist.get_db_session_local", return_value=mock_ctx):
            with pytest.raises(ValueError, match="missing required columns"):
                await import_waitlist(csv_file)

    @pytest.mark.asyncio
    async def test_inserts_new_entries(self, tmp_path):
        from ii_agent.workers.cron.jobs.import_waitlist import import_waitlist

        csv_file = tmp_path / "test.csv"
        csv_file.write_text("email,created_at\nnew@example.com,2025-01-01T00:00:00+00:00\n")

        # _existing_emails returns empty set
        mock_result_existing = MagicMock()
        mock_result_existing.scalars.return_value = iter([])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result_existing)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("ii_agent.workers.cron.jobs.import_waitlist.get_db_session_local", return_value=mock_ctx):
            inserted, skipped = await import_waitlist(csv_file)

        assert inserted == 1
        assert skipped == 0

    @pytest.mark.asyncio
    async def test_skips_duplicate_emails(self, tmp_path):
        from ii_agent.workers.cron.jobs.import_waitlist import import_waitlist

        csv_file = tmp_path / "test.csv"
        csv_file.write_text("email,created_at\nexisting@example.com,2025-01-01T00:00:00+00:00\n")

        # _existing_emails returns the existing email
        mock_result_existing = MagicMock()
        mock_result_existing.scalars.return_value = iter(["existing@example.com"])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result_existing)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("ii_agent.workers.cron.jobs.import_waitlist.get_db_session_local", return_value=mock_ctx):
            inserted, skipped = await import_waitlist(csv_file)

        assert inserted == 0
        assert skipped == 1

    @pytest.mark.asyncio
    async def test_inserts_multiple_rows(self, tmp_path):
        from ii_agent.workers.cron.jobs.import_waitlist import import_waitlist

        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "email,created_at\n"
            "a@example.com,2025-01-01T00:00:00+00:00\n"
            "b@example.com,2025-01-02T00:00:00+00:00\n"
        )

        mock_result_existing = MagicMock()
        mock_result_existing.scalars.return_value = iter([])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result_existing)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("ii_agent.workers.cron.jobs.import_waitlist.get_db_session_local", return_value=mock_ctx):
            inserted, skipped = await import_waitlist(csv_file)

        assert inserted == 2
        assert skipped == 0
