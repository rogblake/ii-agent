# Harness Engineering Gap Analysis

This document maps II-Agent's current state against the full harness engineering vision described in OpenAI's [Harness Engineering](https://openai.com/index/harness-engineering/) article (Ryan Lopopolo, Feb 2026). It identifies what we have, what we lack, and a prioritized roadmap for closing gaps.

## Reference Implementation

We used `openai-agents-python` as a reference for how harness engineering is implemented in practice. Full exploration documented in `harness_exploration.md`.

## Current State Summary

### What We Have (Implemented)

| Harness Principle | II-Agent Implementation |
|-------------------|------------------------|
| **AGENTS.md as table of contents** | `AGENTS.md` (~100 lines) points to `ARCHITECTURE.md`, `CLAUDE.md`, and `docs/` |
| **Progressive disclosure** | Three layers: AGENTS.md → ARCHITECTURE.md → CLAUDE.md + docs/ |
| **Repository knowledge as system of record** | `CLAUDE.md` (633 lines) + `docs/` with design docs, product specs, references |
| **Architecture documentation** | `ARCHITECTURE.md` with domain map, layer rules, API surface |
| **Design patterns documentation** | `docs/DESIGN.md` with service pattern, DI, model conventions |
| **Execution plan framework** | `docs/PLANS.md` with ExecPlan template and living section requirements |
| **Design docs index** | `docs/design-docs/index.md` cataloguing existing design decisions |
| **Core beliefs** | `docs/design-docs/core-beliefs.md` with agent-first principles |
| **Quality tracking** | `docs/QUALITY_SCORE.md` with per-domain quality grades |
| **Tech debt tracking** | `docs/exec-plans/tech-debt-tracker.md` with prioritized items |
| **Security documentation** | `docs/SECURITY.md` covering auth, secrets, data isolation |
| **Reliability documentation** | `docs/RELIABILITY.md` covering billing, outbox, cron, Redis fallbacks |
| **Frontend integration docs** | `docs/FRONTEND.md` with Socket.IO events, REST API surface |
| **Product sense** | `docs/PRODUCT_SENSE.md` with pillars, personas, journeys |
| **Database schema reference** | `docs/generated/db-schema.md` extracted from SQLAlchemy models |
| **LLM-optimized references** | `docs/references/` with FastAPI, SQLAlchemy, E2B reference files |
| **Standard linting** | Ruff (format + lint) + mypy + pre-commit hooks |
| **Coverage threshold** | 85% minimum enforced |
| **CI pipelines** | Build, deploy, gitleaks, Claude Code, Codex review |
| **Claude Code skills** | 11 skills in `.claude/skills/` |

### What We Lack (Gaps)

The following are capabilities described in the harness article or implemented in openai-agents-python that II-Agent does not yet have.

---

## Gap 1: Log Querying by Agents (HIGH PRIORITY)

**Article describes:** Local observability stack — Vector fans out logs/metrics/traces to Victoria Logs/Metrics/Traces. Agents query via LogQL, PromQL, TraceQL APIs. Ephemeral per-worktree.

**We have:** Standard Python logging. No structured log aggregation. No agent-queryable log APIs.

**What's needed:**
1. Structured logging (JSON format) throughout the application
2. Local dev observability stack (docker-compose with Loki or Victoria Logs)
3. Agent-accessible log query endpoint or MCP tool
4. Per-session/per-run log correlation via structured fields

**Impact:** Without this, agents cannot diagnose runtime issues, validate performance, or verify fixes by querying logs. They must read raw stdout.

**Effort:** High

---

## Gap 2: UI Integration / Application Legibility (HIGH PRIORITY)

**Article describes:** Chrome DevTools Protocol wired into agent runtime. Agents can take DOM snapshots, screenshots, navigate the app. App bootable per git worktree.

**We have:** No CDP integration. No screenshot capability. App not bootable per worktree.

**What's needed:**
1. Chrome DevTools Protocol MCP tool for agents
2. DOM snapshot and screenshot capabilities accessible to coding agents
3. Per-worktree app bootability (isolated instances per change)
4. Playwright or similar integration for automated UI validation

**Impact:** Agents cannot visually verify UI changes, reproduce UI bugs, or validate frontend fixes.

**Effort:** High

---

## Gap 3: Video Recording for Bug Reproduction (MEDIUM PRIORITY)

**Article describes:** Agents record video demonstrating bug → implement fix → record second video demonstrating resolution. Both videos attached to PR.

**We have:** No video recording capability.

**What's needed:**
1. Screen recording tool accessible to agents (e.g., via Playwright or headless browser)
2. Integration with PR workflow to attach before/after videos
3. Storage for video artifacts (GCS bucket)

**Impact:** PRs lack visual evidence of bug fixes. Reviewers must manually reproduce.

**Effort:** Medium

---

## Gap 4: Custom Architectural Linters (MEDIUM PRIORITY)

**Article describes:** Custom linters enforce dependency direction, file size limits, naming conventions, structured logging. Error messages are written to inject remediation instructions into agent context.

**We have:** Standard Ruff rules only. No custom architectural enforcement.

**What's needed:**
1. Custom lint rules or structural tests for:
   - Layer boundary enforcement (router cannot import repository)
   - Dependency direction validation (domain A cannot import domain B's internals)
   - Dep alias pattern enforcement (no bare `Depends()`)
   - File size limits per module
2. Agent-targeted error messages that explain HOW to fix violations

**Impact:** Architecture drift detected only in manual code review. Agents may generate code that violates conventions.

**Effort:** Medium

---

## Gap 5: Background Doc-Gardening Agent (MEDIUM PRIORITY)

**Article describes:** Recurring Codex tasks scan for deviations from golden principles, update quality grades, open refactoring PRs. Most reviewable in under a minute and auto-merged.

**We have:** No automated doc maintenance. QUALITY_SCORE.md is manually updated.

**What's needed:**
1. Recurring CI job or Claude Code hook that:
   - Scans for stale documentation (code changed, docs not updated)
   - Validates cross-links between docs files
   - Checks that QUALITY_SCORE.md reflects actual coverage numbers
   - Opens fix-up PRs for documentation drift
2. `$docs-sync` skill (like openai-agents-python has)

**Impact:** Documentation rots silently. Agents work with stale information.

**Effort:** Medium

---

## Gap 6: Agent-to-Agent Review (LOW PRIORITY)

**Article describes:** PR reviews handled agent-to-agent. Agents iterate until all agent reviewers are satisfied. Humans review optional.

**We have:** `codex-review.yml` for Codex code review. No iterative agent-to-agent review loop.

**What's needed:**
1. Multiple agent review passes (architecture, security, billing correctness)
2. Agent iteration loop on review feedback
3. Auto-merge capability for agent-approved changes

**Impact:** Human review remains the bottleneck. Each PR requires manual attention.

**Effort:** High

---

## Gap 7: Auto-Generated API Reference (LOW PRIORITY)

**Article describes:** API reference auto-generated from docstrings. mkdocstrings plugin creates reference stubs for every public module.

**We have:** Docusaurus site with manual docs. No auto-generated API reference from Python docstrings.

**What's needed:**
1. mkdocstrings or similar tool to generate API docs from source
2. Script to create reference stubs for all public modules (like openai-agents-python's `generate_ref_files.py`)
3. CI job to verify docs build on changes

**Impact:** API reference drifts from actual code. Agents must read source to understand APIs.

**Effort:** Medium

---

## Gap 8: Mandatory Verification Skills (LOW PRIORITY)

**Article describes:** `$code-change-verification` skill MUST run before marking work complete. Enforced via AGENTS.md policies.

**We have:** `make format` + `make lint` as manual rules. No enforced skill that runs the full stack.

**What's needed:**
1. `.agents/skills/code-change-verification/` with `run.sh` that executes: format → lint → typecheck → tests
2. AGENTS.md policy requiring agents to run it before marking work complete
3. `$pr-draft-summary` skill for generating PR descriptions
4. `$implementation-strategy` skill for pre-change compatibility analysis

**Impact:** Agents may skip verification steps. PRs land without full validation.

**Effort:** Low

---

## Gap 9: Execution Plan Storage (LOW PRIORITY)

**Article describes:** Active plans, completed plans, and tech debt versioned and co-located in the repository.

**We have:** `docs/exec-plans/active/` and `completed/` directories (empty). Plans framework defined in `docs/PLANS.md`.

**What's needed:**
1. Actually use the exec plans framework for real work
2. Decision on whether to commit plans or keep them local (openai-agents-python gitignores theirs)
3. Regular cadence of moving active → completed

**Impact:** Institutional knowledge about past decisions lost. No paper trail for complex changes.

**Effort:** Low (behavioral, not technical)

---

## Gap 10: LLM-Powered Doc Translation (LOW PRIORITY)

**Article describes:** openai-agents-python auto-translates docs to ja/ko/zh via GPT-5.3-Codex with code-block extraction and git-timestamp freshness checks.

**We have:** No doc translation.

**What's needed:**
1. Translation script (like `translate_docs.py`)
2. CI workflow triggered on English doc changes
3. Language-specific term mappings

**Impact:** Non-English users cannot access documentation.

**Effort:** Medium

---

## Prioritized Roadmap

### Phase 1: Foundation (Next Sprint)
- [ ] Gap 8: Create `$code-change-verification` skill
- [ ] Gap 4: Add structural tests for layer boundaries
- [ ] Gap 5: Create `$docs-sync` skill for documentation coverage auditing

### Phase 2: Observability (Next Month)
- [ ] Gap 1: Add structured JSON logging
- [ ] Gap 1: Create docker-compose with log aggregation for local dev
- [ ] Gap 1: Build MCP tool for agent log querying

### Phase 3: Application Legibility (Next Quarter)
- [ ] Gap 2: Integrate Playwright for agent-accessible screenshots
- [ ] Gap 2: Per-worktree app bootability
- [ ] Gap 3: Video recording capability

### Phase 4: Automation (Ongoing)
- [ ] Gap 5: Recurring doc-gardening job
- [ ] Gap 6: Agent-to-agent review pipeline
- [ ] Gap 7: Auto-generated API reference
- [ ] Gap 9: Adopt exec plans for real work
- [ ] Gap 10: Doc translation pipeline
