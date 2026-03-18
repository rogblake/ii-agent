# II-Agent Contributor Guide

This file is the entry point for agents working in this repository. It provides a map to deeper documentation — not a comprehensive manual.

**Read `CLAUDE.md` for the full development reference** (architecture, patterns, billing system, code examples).

## Quick Start

```bash
uv sync --frozen          # Install dependencies
./start.sh                # Start the server
curl localhost:8000/health # Verify
```

## Repository Map

| Resource | What it covers |
|----------|---------------|
| [`CLAUDE.md`](CLAUDE.md) | Full development guide: architecture, patterns, billing, dependency injection, code examples |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Domain map, layer definitions, dependency direction rules |
| [`docs/DESIGN.md`](docs/DESIGN.md) | Design patterns: service pattern, Dep aliases, domain module structure |
| [`docs/PLANS.md`](docs/PLANS.md) | How to write and maintain execution plans |
| [`docs/RELIABILITY.md`](docs/RELIABILITY.md) | Billing reliability, outbox pattern, cron recovery, Redis fallbacks |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Auth flow (OAuth, JWT, API keys), secrets management |
| [`docs/FRONTEND.md`](docs/FRONTEND.md) | Socket.IO events, REST API surface, real-time event flow |
| [`docs/PRODUCT_SENSE.md`](docs/PRODUCT_SENSE.md) | Product principles, user personas, key journeys |
| [`docs/QUALITY_SCORE.md`](docs/QUALITY_SCORE.md) | Per-domain quality grades and health metrics |
| [`docs/design-docs/`](docs/design-docs/index.md) | Indexed design decisions with verification status |
| [`docs/exec-plans/`](docs/exec-plans/) | Active and completed execution plans |
| [`docs/generated/db-schema.md`](docs/generated/db-schema.md) | Database schema reference (from SQLAlchemy models) |
| [`docs/product-specs/`](docs/product-specs/index.md) | Product specifications |
| [`docs/references/`](docs/references/) | LLM-optimized reference material for key dependencies |

## Mandatory Rules

1. **Use `uv run`** for all Python commands (`uv run pytest`, `uv run python ...`).
2. **Run `make format` + `make lint`** before marking work complete.
3. **Never call `CreditService.deduct()` directly** for LLM/tool billing — use the reservation system (see `CLAUDE.md` Billing section).
4. **Use Dep aliases everywhere** — never bare `= Depends(get_x)` in function signatures (see `CLAUDE.md` Dependency Injection Pattern).
5. **Use `LLMExecutionService`** for any new code that calls an LLM outside the agent runtime loop.

## Where to Look

| Task | Start here |
|------|-----------|
| Understand the full architecture | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Add a new domain module | `CLAUDE.md` > "Adding a New Domain" |
| Add a new API endpoint | `CLAUDE.md` > "Router Pattern" + [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Work on billing / credits | `CLAUDE.md` > "Billing & Credit System" + [`docs/RELIABILITY.md`](docs/RELIABILITY.md) |
| Add a new LLM feature | `CLAUDE.md` > "Rules for New Code" |
| Add a billable tool | `CLAUDE.md` > "Adding a new billable tool" |
| Understand auth flow | [`docs/SECURITY.md`](docs/SECURITY.md) |
| Work on WebSocket events | [`docs/FRONTEND.md`](docs/FRONTEND.md) |
| Review design decisions | [`docs/design-docs/`](docs/design-docs/index.md) |
| Plan multi-step work | [`docs/PLANS.md`](docs/PLANS.md) |
| Check code quality | [`docs/QUALITY_SCORE.md`](docs/QUALITY_SCORE.md) |
| Understand the database | [`docs/generated/db-schema.md`](docs/generated/db-schema.md) |

## Development Workflow

1. Create a feature branch from `develop`.
2. Implement changes following patterns in `CLAUDE.md`.
3. Run `make format` and `make lint`.
4. Run tests: `uv run pytest`.
5. For complex work, create an ExecPlan (see [`docs/PLANS.md`](docs/PLANS.md)).

## Key Commands

```bash
make install          # Install deps + pre-commit hooks
make format           # Ruff format + fix
make lint             # Ruff check + format validation
uv run pytest         # Run tests
uv run pytest -k "test_name"  # Run specific test
./start.sh            # Start server (Xvfb + uv run python -m ii_agent.ws_server)
uv run python -m ii_agent.ws_server  # Start server directly
```
