# Core Beliefs: Agent-First Operating Principles

These principles define how II-Agent is built and maintained. They are informed by the harness engineering methodology — the discipline of designing environments that allow coding agents to do reliable work.

## 1. Repository Knowledge Is the System of Record

Everything an agent needs to work effectively must be discoverable in the repository. Slack discussions, Google Docs, and tacit knowledge are invisible to agents. If a decision, pattern, or constraint matters, it belongs in a versioned file.

- Architecture decisions go in `docs/design-docs/`.
- Code patterns and conventions are documented in `CLAUDE.md` and `docs/DESIGN.md`.
- Execution plans are tracked in `docs/exec-plans/`.

## 2. Progressive Disclosure Over Monolithic Instructions

`AGENTS.md` is a map, not a manual. It points agents to deeper documentation. This prevents context overload — when everything is "important," nothing is.

The disclosure layers:
1. `AGENTS.md` — Table of contents (~120 lines)
2. `ARCHITECTURE.md` — Domain map and structural rules
3. `CLAUDE.md` — Full development reference with code examples
4. `docs/` — Deep dives into specific concerns

## 3. Enforce Architecture Mechanically

Constraints are multipliers for agents. Rules that exist only in documentation drift. Rules encoded in tooling apply everywhere at once.

Current enforcement:
- **Ruff** — Formatting and linting on changed Python files (`uv run ruff check --fix-only <changed_python_files>`, `uv run ruff format <changed_python_files>`, `uv run ruff check <changed_python_files>`, `uv run ruff format --check <changed_python_files>`)
- **Type checking** — Mypy for static analysis
- **Pre-commit hooks** — Automated checks before commits
- **Coverage threshold** — 85% minimum enforced in CI

Aspirational:
- Custom linters for dependency direction validation
- Structural tests for layer boundaries
- Naming convention enforcement with agent-targeted error messages

## 4. Prefer Boring Technology

Technologies that are composable, have stable APIs, and are well-represented in LLM training data are easier for agents to reason about. II-Agent uses:

- **FastAPI** — Well-documented, widely known
- **SQLAlchemy 2.0** — Mature ORM with async support
- **PostgreSQL** — Battle-tested relational database
- **Redis** — Standard caching and pub/sub (with in-memory fallbacks)
- **Pydantic** — Data validation with clear error messages

## 5. Reserve, Settle, Release — Never Direct Deductions

All billable work (LLM calls, tool executions) follows the reservation lifecycle. This ensures:
- Users are never overcharged (overage is refunded on settle)
- Failed work is fully refunded (release)
- Partial work is charged accurately (settle to actual cost)
- Idempotency keys prevent double-charging on retries

See `CLAUDE.md` > "Billing & Credit System" for implementation details.

## 6. Domain Boundaries Are Non-Negotiable

Each domain (auth, billing, sessions, etc.) owns its own models, repository, service, dependencies, and router. Cross-domain access happens only through Dep aliases — never by importing another domain's repository directly.

This keeps the codebase navigable for both humans and agents as it grows.

## 7. Every Service Takes `db: AsyncSession` as First Parameter

Services are stateless. All state lives in the database. Services receive their database session from the caller (typically a FastAPI dependency). This makes services testable, composable, and predictable.

## 8. Correctness Over Cleverness

When in doubt, choose the simpler, more explicit approach. Agent-generated code should be correct, maintainable, and legible to future agent runs — not clever or aesthetically optimized.
