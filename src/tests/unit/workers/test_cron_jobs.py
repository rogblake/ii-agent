"""Unit tests for workers/cron/cron_jobs.py.

Tests CronJobSpec dataclass, _run_job, run_all_jobs, install_all_jobs,
and the CRON_JOBS constant.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from ii_agent.workers.cron.cron_jobs import (
    CRON_JOBS,
    CronJobSpec,
    CronJobStatus,
    _run_job,
    install_all_jobs,
    main,
    run_all_jobs,
)


# ---------------------------------------------------------------------------
# CronJobSpec
# ---------------------------------------------------------------------------


class TestCronJobSpec:
    def test_default_status_is_active(self):
        spec = CronJobSpec(
            name="test-job",
            schedule="0 * * * *",
            task=lambda: None,
            command="echo test",
        )
        assert spec.status == "active"

    def test_status_can_be_set_to_inactive(self):
        spec = CronJobSpec(
            name="inactive-job",
            schedule="0 * * * *",
            task=lambda: None,
            command="echo test",
            status="inactive",
        )
        assert spec.status == "inactive"

    def test_fields_stored_correctly(self):
        async def my_task():
            pass

        spec = CronJobSpec(
            name="my-job",
            schedule="*/5 * * * *",
            task=my_task,
            command="python -m my.module",
        )
        assert spec.name == "my-job"
        assert spec.schedule == "*/5 * * * *"
        assert spec.task is my_task
        assert spec.command == "python -m my.module"


# ---------------------------------------------------------------------------
# CRON_JOBS constant
# ---------------------------------------------------------------------------


class TestCronJobsConstant:
    def test_is_non_empty_sequence(self):
        assert len(CRON_JOBS) > 0

    def test_all_items_are_cron_job_spec(self):
        for job in CRON_JOBS:
            assert isinstance(job, CronJobSpec)

    def test_all_items_have_name_schedule_command(self):
        for job in CRON_JOBS:
            assert job.name
            assert job.schedule
            assert job.command

    def test_status_values_are_valid(self):
        valid_statuses = {"active", "inactive"}
        for job in CRON_JOBS:
            assert job.status in valid_statuses


# ---------------------------------------------------------------------------
# _run_job
# ---------------------------------------------------------------------------


class TestRunJob:
    async def test_runs_sync_task(self):
        called = []

        def sync_task():
            called.append(True)

        spec = CronJobSpec(
            name="sync-job",
            schedule="* * * * *",
            task=sync_task,
            command="cmd",
        )

        await _run_job(spec)
        assert called == [True]

    async def test_runs_async_task(self):
        called = []

        async def async_task():
            called.append(True)

        spec = CronJobSpec(
            name="async-job",
            schedule="* * * * *",
            task=async_task,
            command="cmd",
        )

        await _run_job(spec)
        assert called == [True]

    async def test_propagates_exception_from_sync_task(self):
        def failing_task():
            raise ValueError("task failed")

        spec = CronJobSpec(
            name="fail-job",
            schedule="* * * * *",
            task=failing_task,
            command="cmd",
        )

        with pytest.raises(ValueError, match="task failed"):
            await _run_job(spec)

    async def test_propagates_exception_from_async_task(self):
        async def failing_async_task():
            raise RuntimeError("async failed")

        spec = CronJobSpec(
            name="async-fail-job",
            schedule="* * * * *",
            task=failing_async_task,
            command="cmd",
        )

        with pytest.raises(RuntimeError, match="async failed"):
            await _run_job(spec)


# ---------------------------------------------------------------------------
# run_all_jobs
# ---------------------------------------------------------------------------


class TestRunAllJobs:
    async def test_active_jobs_are_executed(self):
        executed = []

        async def task1():
            executed.append("job1")

        async def task2():
            executed.append("job2")

        jobs = [
            CronJobSpec(name="job1", schedule="* * * * *", task=task1, command="cmd1", status="active"),
            CronJobSpec(name="job2", schedule="* * * * *", task=task2, command="cmd2", status="active"),
        ]

        with patch("ii_agent.workers.cron.cron_jobs.CRON_JOBS", jobs):
            await run_all_jobs()

        assert "job1" in executed
        assert "job2" in executed

    async def test_inactive_jobs_are_skipped(self):
        executed = []

        async def active_task():
            executed.append("active")

        async def inactive_task():
            executed.append("inactive")

        jobs = [
            CronJobSpec(
                name="active-job",
                schedule="* * * * *",
                task=active_task,
                command="cmd",
                status="active",
            ),
            CronJobSpec(
                name="inactive-job",
                schedule="* * * * *",
                task=inactive_task,
                command="cmd",
                status="inactive",
            ),
        ]

        with patch("ii_agent.workers.cron.cron_jobs.CRON_JOBS", jobs):
            await run_all_jobs()

        assert "active" in executed
        assert "inactive" not in executed

    async def test_failure_collected_and_raises_system_exit(self):
        async def failing_task():
            raise RuntimeError("boom")

        jobs = [
            CronJobSpec(
                name="fail-job",
                schedule="* * * * *",
                task=failing_task,
                command="cmd",
                status="active",
            ),
        ]

        with patch("ii_agent.workers.cron.cron_jobs.CRON_JOBS", jobs):
            with pytest.raises(SystemExit) as exc_info:
                await run_all_jobs()

        assert "fail-job" in str(exc_info.value)

    async def test_multiple_failures_listed_in_exit(self):
        async def fail_a():
            raise Exception("a")

        async def fail_b():
            raise Exception("b")

        jobs = [
            CronJobSpec(name="job-a", schedule="*", task=fail_a, command="a", status="active"),
            CronJobSpec(name="job-b", schedule="*", task=fail_b, command="b", status="active"),
        ]

        with patch("ii_agent.workers.cron.cron_jobs.CRON_JOBS", jobs):
            with pytest.raises(SystemExit) as exc_info:
                await run_all_jobs()

        msg = str(exc_info.value)
        assert "job-a" in msg
        assert "job-b" in msg

    async def test_no_active_jobs_completes_without_error(self):
        jobs = [
            CronJobSpec(
                name="inactive-job",
                schedule="*",
                task=lambda: None,
                command="cmd",
                status="inactive",
            )
        ]

        with patch("ii_agent.workers.cron.cron_jobs.CRON_JOBS", jobs):
            # Should not raise
            await run_all_jobs()

    async def test_all_jobs_executed_count_reported(self):
        executed = []

        async def task():
            executed.append(1)

        jobs = [
            CronJobSpec(name=f"job-{i}", schedule="*", task=task, command="cmd", status="active")
            for i in range(3)
        ]

        with patch("ii_agent.workers.cron.cron_jobs.CRON_JOBS", jobs):
            await run_all_jobs()

        assert len(executed) == 3


# ---------------------------------------------------------------------------
# install_all_jobs
# ---------------------------------------------------------------------------


class TestInstallAllJobs:
    def test_calls_manager_sync_with_active_jobs(self):
        async def task1():
            pass

        jobs = [
            CronJobSpec(
                name="active-job",
                schedule="0 * * * *",
                task=task1,
                command="echo active",
                status="active",
            ),
            CronJobSpec(
                name="inactive-job",
                schedule="0 0 * * *",
                task=task1,
                command="echo inactive",
                status="inactive",
            ),
        ]

        mock_manager = MagicMock()
        mock_manager.sync = MagicMock()

        with (
            patch("ii_agent.workers.cron.cron_jobs.CRON_JOBS", jobs),
            patch(
                "ii_agent.workers.cron.cron_jobs.CronManager",
                return_value=mock_manager,
            ),
        ):
            install_all_jobs()

        mock_manager.sync.assert_called_once()
        call_kwargs = mock_manager.sync.call_args.kwargs
        definitions = call_kwargs["jobs"]

        # Only active job should be included
        names = [d.name for d in definitions]
        assert "active-job" in names
        assert "inactive-job" not in names

    def test_sync_called_with_dry_run_false(self):
        mock_manager = MagicMock()

        with patch("ii_agent.workers.cron.cron_jobs.CronManager", return_value=mock_manager):
            install_all_jobs()

        call_kwargs = mock_manager.sync.call_args.kwargs
        assert call_kwargs.get("dry_run") is False
