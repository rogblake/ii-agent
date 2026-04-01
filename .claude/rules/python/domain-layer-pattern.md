---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
Every domain module under `src/ii_agent/` MUST follow this layering pattern. This is non-negotiable for all new domains, refactors, and modifications.

When creating or modifying ANY domain module (sessions, files, credits, projects, chat, agents, content, etc.), verify it follows all rules below.

## Required File Structure

Each domain module should contain:

```
src/ii_agent/{domain}/
├── __init__.py       # Exports all public APIs
├── models.py         # SQLAlchemy ORM models
├── repository.py     # Data access layer (extends BaseRepository)
├── service.py        # Business logic (returns Pydantic, not ORM)
├── schemas.py        # Pydantic response models
├── types.py          # StrEnum types (if domain has enums)
├── exceptions.py     # Domain-specific exceptions
└── dependencies.py   # FastAPI DI factories & Dep aliases
```

## Layer Rules

### 1. Repository (`repository.py`) — Pure CRUD + Queries

- Extends `BaseRepository[T]` from `ii_agent.core.db.base`
- Set `model = MyModel` as class variable
- Inherits: `get_by_id(db, entity_id)`, `save(db, entity)`, `update(db, entity)`
- Add domain-specific query methods (e.g., `find_by_x`, `list_by_y`)
- Takes `db: AsyncSession` as first param on every method
- Returns ORM entities (`T`) or `None` — NEVER Pydantic models
- No business logic — only SELECT/INSERT/UPDATE/DELETE
- No cache operations — that belongs in the service layer

### 2. Service (`service.py`) — Business Logic

- Constructor takes repository instances + config (injected via container)
- Takes `db: AsyncSession` as first param on public methods
- Creates ORM objects internally, delegates persistence to repos
- **MUST return Pydantic response models, NEVER ORM entities**
- Use `ResponseModel.model_validate(orm_entity)` with `ConfigDict(from_attributes=True)`
- Handles: validation, cache (Redis entity_cache), audit logs, error wrapping
- Wraps `IntegrityError` into domain exceptions

### 3. Schema (`schemas.py`) — Pydantic Response Models

- Use `ConfigDict(from_attributes=True)` for ORM-to-Pydantic conversion
- Map fields to proper types — use enums, not raw `str`
- These are the public API — callers only see Pydantic models

### 4. Models (`models.py`) — SQLAlchemy ORM

- Use `Mapped[EnumType]` for enum columns — never `Mapped[str]` for enum fields
- StrEnum auto-coerces — no need for `.value` when assigning or comparing
- Move SQL fragments to enum static methods (e.g., `MyStatus.active_status_sql()`)
- Keep models lean — no business logic, no relationships unless needed

### 5. Exceptions (`exceptions.py`) — Domain Exceptions

- Domain-specific exceptions for callers to catch
- Include relevant context as attributes (e.g., `entity_id`, `session_id`)

### 6. Types (`types.py`) — Enums

- Use `StrEnum` — stored as VARCHAR in DB, no PG enum migration needed
- Keep enums minimal — no duplicate meanings
- Add helper static methods where useful (`active_states()`, `terminal_states()`)

## Anti-Patterns (DO NOT)

```python
# BAD: Repository returns Pydantic
class MyRepo(BaseRepository[MyModel]):
    async def get(self, db, id) -> MyResponse:  # NO
        ...

# BAD: Service returns ORM
class MyService:
    async def get(self, db, id) -> MyModel:  # NO — return MyResponse
        ...

# BAD: Service uses raw SQL or db.execute
class MyService:
    async def get(self, db, id):
        await db.execute(select(...))  # NO — delegate to repo

# BAD: Using .value on StrEnum columns
entity.status = MyStatus.ACTIVE.value  # NO
entity.status = MyStatus.ACTIVE        # YES — auto-coerces

# BAD: Raw str for enum fields in Pydantic
class MyResponse(BaseModel):
    status: str       # NO
    status: MyStatus  # YES
```

## Reference Implementation

`src/ii_agent/tasks/` is the canonical example. All other domains must match this structure:
- `types.py` — `RunStatus`, `TaskType` (StrEnum)
- `models.py` — `RunTask`, `TaskLog` (ORM with `Mapped[RunStatus]`)
- `repository.py` — `RunTaskRepository(BaseRepository[RunTask])`
- `service.py` — `RunTaskService` (returns `RunTaskResponse`)
- `schemas.py` — `RunTaskResponse`, `TaskLogResponse` (Pydantic with enums)
- `exceptions.py` — `TaskConflictException`
- `__init__.py` — exports all public APIs
