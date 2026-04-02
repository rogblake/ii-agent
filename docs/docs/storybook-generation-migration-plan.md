---
id: storybook-generation-migration-plan
title: Storybook Generation Migration Plan
sidebar_label: Storybook Migration Plan
sidebar_position: 6
description: Refactor plan to make storybook generation backend-agnostic while keeping Celery as an implementation detail.
---

# Storybook Generation Migration Plan

## Problem statement

`generate_storybook` currently leaks execution details (`Celery`) into tool flow and orchestration logic. This makes the tool contract harder to maintain and couples chat behavior to one backend implementation.

## Target architecture

- Tool/API contract stays stable regardless of execution backend.
- Backend selection (`celery` vs `inprocess`) happens in service wiring/configuration.
- Progress, cancel, and completion semantics remain unchanged for clients.
- Celery-specific details are isolated to `src/ii_agent/celery/*` and backend adapters.

## Scope

Included:

- Storybook tool invocation path (`generate_storybook`).
- Storybook generation orchestration/service layers.
- Celery adapter boundary.
- LLM loop handling for long-running tool calls.

Excluded:

- UI polling protocol redesign.
- Storybook data model redesign beyond compatibility metadata keys.
- Non-storybook task refactors.

## Refactor phases

### Phase 1: Introduce backend-agnostic contract

1. Add `StorybookGenerationBackend` protocol in `src/ii_agent/content/storybook/generation/backend.py`.
2. Add backend-neutral request/response types:
   - `StorybookGenerationRequest`
   - `StorybookGenerationAccepted`
   - `StorybookGenerationProgress`
   - `StorybookGenerationResult`
3. Add `StorybookGenerationService` that delegates to configured backend.

Acceptance criteria:

- No business logic references Celery task names outside backend adapters.
- Storybook tool can call a single service method to start generation.

### Phase 2: Implement backend adapters

1. Add `CeleryStorybookBackend` in `src/ii_agent/content/storybook/generation/celery_backend.py`.
2. Add `InProcessStorybookBackend` in `src/ii_agent/content/storybook/generation/inprocess_backend.py`.
3. Ensure both adapters share identical accepted/progress/result semantics.

Acceptance criteria:

- Switching backend requires config change only.
- Existing `/storybooks/{id}/progress` and cancel endpoints continue to work.

### Phase 3: Decouple tool and LLM loop from Celery details

1. Remove `start_celery_generation` from `StorybookGenerationTool`.
2. Keep one tool entrypoint (`run`) that calls `StorybookGenerationService.start(...)`.
3. Replace special-case Celery branching in `llm_loop_service` with generic “long-running accepted” handling.

Acceptance criteria:

- Tool logic has no `queue_task`, task name strings, or Celery-specific flags.
- LLM loop does not inspect tool implementation methods (e.g., no `hasattr(...start_celery_generation)`).

### Phase 4: Metadata compatibility and cleanup

1. Migrate generation metadata keys to backend-neutral names:
   - `active_task_id` -> `active_job_id`
2. Keep backward read compatibility for existing records.
3. Remove dead code paths and legacy comments mentioning Celery as API behavior.

Acceptance criteria:

- Existing storybooks still report progress correctly.
- New records use backend-neutral metadata keys.

### Phase 5: Tests and rollout

1. Unit tests:
   - Tool returns backend-neutral accepted output.
   - Backend adapters map to common contract correctly.
2. Integration tests:
   - Start -> progress -> completion for both backends.
   - Cancel behavior for both backends.
3. Rollout:
   - Default to Celery backend in production config.
   - Optional canary: run in-process backend in local/dev for comparison.

Acceptance criteria:

- No regressions in tool output schema.
- No regressions in polling/cancel endpoints.

## File-level change map

Primary new files:

- `src/ii_agent/content/storybook/generation/backend.py`
- `src/ii_agent/content/storybook/generation/service.py`
- `src/ii_agent/content/storybook/generation/celery_backend.py`
- `src/ii_agent/content/storybook/generation/inprocess_backend.py`

Primary modified files:

- `src/ii_agent/chat/tools/storybook_generate.py`
- `src/ii_agent/chat/llm_loop_service.py`
- `src/ii_agent/content/storybook/service.py`
- `src/ii_agent/content/storybook/repository.py`
- `src/ii_agent/core/container.py`
- `src/ii_agent/content/storybook/dependencies.py`

## Risks and mitigations

Risk: Contract drift between backends.
Mitigation: Shared response models + adapter conformance tests.

Risk: Hidden Celery coupling in orchestration.
Mitigation: Strict adapter boundary and grep checks for Celery symbols outside adapter/`src/ii_agent/celery`.

Risk: Backward-compat issues on existing generation metadata.
Mitigation: Dual-read support during transition; one-way write to new keys after rollout.

## Definition of done

- Tool/API contract is backend-agnostic.
- Celery is implementation-only, not part of chat/tool orchestration contracts.
- Both backends pass integration scenarios.
- Documentation and config clearly define backend selection.
