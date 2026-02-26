# Unit Test Plan Index (`src/ii_agent`)

This directory contains one dedicated unit-test plan file for each **source-bearing** top-level folder in `src/ii_agent`.

## Covered folders

- `auth` -> `docs/unit/auth.md`
- `billing` -> `docs/unit/billing.md`
- `celery` -> `docs/unit/celery.md`
- `chat` -> `docs/unit/chat.md`
- `content` -> `docs/unit/content.md`
- `core` -> `docs/unit/core.md`
- `engine` -> `docs/unit/engine.md`
- `files` -> `docs/unit/files.md`
- `integrations` -> `docs/unit/integrations.md`
- `projects` -> `docs/unit/projects.md`
- `realtime` -> `docs/unit/realtime.md`
- `scripts` -> `docs/unit/scripts.md`
- `sessions` -> `docs/unit/sessions.md`
- `settings` -> `docs/unit/settings.md`
- `utils` -> `docs/unit/utils.md`

## Not in this set

Some top-level folders under `src/ii_agent` currently contain no `.py` source files (only cache artifacts or compatibility namespace shells). Those are intentionally excluded from dedicated unit plans until they contain executable source.

## Baseline testing conventions

- Test framework: `pytest` + `pytest-asyncio`
- Preferred unit location: `src/tests/unit/<folder>/`
- External calls must be mocked (Stripe, GitHub, GCP, MCP, Celery broker, sandbox providers)
- Unit tests should not rely on network or shared mutable global state
- Every bug fix should add at least one regression test in the nearest folder plan
