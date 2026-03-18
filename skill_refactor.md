# Skill Refactor Choice

## Decision

Create a dedicated top-level `skills` domain at `src/ii_agent/skills/`.

Do not keep skills under `content/`.
Do not move the whole thing under `agent/`.

## Why

The current design mixes two concerns:

- `content/skills/` owns the persisted skill catalog and `/user-settings/skills` API.
- `agent/runtime/skills/` owns builtin discovery, GitHub import, storage, prompt generation, and runtime loading.

That creates bidirectional coupling between domains. The cleaner boundary is:

```text
agent -> skills -> core
```

Not:

```text
agent <-> skills
```

Skills are not just runtime behavior. They are also:

- a user-facing settings surface
- a persisted database model
- a builtin catalog
- an install/import workflow
- a storage and activation input for agent runtime

That is broader than `agent`, and it does not fit naturally under `content`.

## Proposed Structure

```text
src/ii_agent/
├── skills/
│   ├── __init__.py
│   ├── models.py
│   ├── repository.py
│   ├── service.py
│   ├── dependencies.py
│   ├── router.py
│   ├── schemas.py
│   ├── exceptions.py
│   ├── registry.py
│   ├── seeding.py
│   ├── storage.py
│   ├── importers/
│   │   └── github.py
│   ├── manifest/
│   │   ├── parser.py
│   │   ├── models.py
│   │   └── errors.py
│   └── builtin/
│       ├── pdf/
│       ├── docx/
│       ├── xlsx/
│       └── ...
├── agent/
│   └── runtime/
│       ├── tools/
│       │   └── skill.py
│       └── providers/
│           └── skill_provider.py
```

## Ownership Split

`skills/` owns:

- `Skill` ORM model
- repository and CRUD service
- `/user-settings/skills` router
- builtin skill discovery and merge logic
- GitHub import
- storage URI resolution and GCS zip handling
- startup syncing of builtin skills
- SKILL.md parsing and validation

`agent/` owns:

- runtime prompt/tool wiring
- resolving available skills for an agent run
- sandbox activation of a chosen skill

## Move Map

- `content/skills/*` -> `skills/*`
- `agent/runtime/skills/builtin/*` -> `skills/builtin/*`
- `agent/runtime/skills/github.py` -> `skills/importers/github.py`
- `agent/runtime/skills/storage.py` -> `skills/storage.py`
- `agent/runtime/skills/loader.py` -> split into `skills/registry.py` and `skills/seeding.py`
- `agent/runtime/skills/skills_ref/*` -> `skills/manifest/*`
- keep only runtime execution adapters in `agent/runtime`

## Notes

- Keep the HTTP route as `/user-settings/skills`.
- `settings/skills` would be an acceptable lower-churn fallback.
- A dedicated top-level `skills` domain is the cleanest long-term structure.
