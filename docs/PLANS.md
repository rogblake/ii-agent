# Execution Plans (ExecPlans)

This file defines how to write and maintain an ExecPlan: a self-contained, living specification that guides multi-step work in this repository.

## When to Use an ExecPlan

- Required for multi-step or multi-file work, new features, refactors, or tasks expected to take more than about an hour.
- Optional for trivial fixes (typos, small docs), but if you skip it for a substantial task, state the reason.

## How to Use This File

- **Authoring:** Read this file before drafting. Start from the skeleton. Embed all context (paths, commands, definitions) so no external docs are needed.
- **Implementing:** Move directly to the next milestone without asking for next steps. Keep living sections current at every stopping point.
- **Discussing:** Record decisions and rationale inside the plan so work can be resumed later using only the ExecPlan.

## Non-Negotiable Requirements

- **Self-contained and beginner-friendly:** Define every term. Include needed repo knowledge. Avoid assuming prior plans or external links.
- **Living document:** Revise Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective as work proceeds.
- **Outcome-focused:** Describe what the user can do after the change and how to see it working.
- **Explicit acceptance:** State behaviors, commands, and observable outputs that prove success.

## Guidelines

- Define jargon immediately and tie it to concrete files or commands in this repo.
- Anchor on outcomes: acceptance should be phrased as observable behavior.
- Specify repository context explicitly: full paths, functions, modules, working directory for commands.
- Be idempotent and safe: describe retries or rollbacks for risky steps.
- Validation is required: state exact test commands and expected outputs.

## Living Sections (must be present and maintained)

- **Progress:** Checkbox list with timestamps. Every pause should update what is done and what remains.
- **Surprises & Discoveries:** Unexpected behaviors, performance notes, or bugs with brief evidence.
- **Decision Log:** Each decision with rationale and date/author.
- **Outcomes & Retrospective:** What was achieved, remaining gaps, and lessons learned.

## Where to Store Plans

- Active plans go in `docs/exec-plans/active/`.
- Completed plans move to `docs/exec-plans/completed/`.
- Known technical debt is tracked in `docs/exec-plans/tech-debt-tracker.md`.

## ExecPlan Skeleton

```md
# <Short, action-oriented description>

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must stay up to date as work proceeds.

## Purpose / Big Picture

Explain the user-visible behavior gained after this change and how to observe it.

## Progress

- [x] (2026-03-17 13:00Z) Example completed step.
- [ ] Example incomplete step.

## Surprises & Discoveries

- Observation: ...
  Evidence: ...

## Decision Log

- Decision: ...
  Rationale: ...
  Date/Author: ...

## Outcomes & Retrospective

Summarize outcomes, gaps, and lessons learned; compare to the original purpose.

## Context and Orientation

Describe the current state relevant to this task. Name key files and modules by full path.
Define any non-obvious terms.

## Plan of Work

Prose description of the sequence of edits and additions. For each edit, name the file
and location and what to change.

## Validation and Acceptance

Behavioral acceptance criteria plus test commands and expected results.

## Idempotence and Recovery

How to retry or roll back safely; ensure steps can be rerun without harm.
```

## Revising a Plan

When the scope shifts, rewrite affected sections so the document remains coherent and self-contained. After significant edits, add a short note at the end explaining what changed and why.
