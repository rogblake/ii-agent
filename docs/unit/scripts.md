# Unit Test Plan: `scripts`

## Scope

- cron abstraction (`scripts/cron_manager.py`)
- scheduled maintenance jobs (`scripts/tasks.py`)
- credit refresh and waitlist import scripts

## Priority test suites

1. Cron manager behavior.
- `install()` replaces old entries with same comment
- `remove()` returns accurate removed/not-removed signal
- `sync()` only replaces managed named jobs
- dry-run mode does not call `write()`

2. Free/annual credit refresh rules.
- free plan refresh uses configured allowance fallback logic
- annual refresh skips users already refreshed this month
- annual refresh ignores expired subscriptions

3. Waitlist import parsing.
- CSV schema validation (`email`, `created_at` required)
- duplicate emails are skipped
- timestamp parsing handles timezone variants

4. Scheduler task cleanup.
- stale running tasks are marked `SYSTEM_INTERRUPTED`
- cleanup loop respects batch and max limits
- start/shutdown scheduler paths safe and idempotent

## Fixtures / mocks

- fake `CronTab` / cron entries
- in-memory DB fixtures for user/waitlist/task rows
- frozen clock for monthly refresh logic

## Proposed test layout

- `src/tests/unit/scripts/test_cron_manager.py`
- `src/tests/unit/scripts/test_refresh_free_credits.py`
- `src/tests/unit/scripts/test_refresh_annual_credits.py`
- `src/tests/unit/scripts/test_import_waitlist.py`
- `src/tests/unit/scripts/test_scheduler_tasks.py`

## Exit criteria

- scheduled financial/accounting updates are regression-protected
- CLI helper parsing and cron installation behavior are deterministic
