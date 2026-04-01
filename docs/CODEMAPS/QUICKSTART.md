<!-- Generated: 2026-03-29 | Token estimate: ~500 -->
# Quick Start Lookup

## Add a New API Endpoint

1. Create/edit `{domain}/router.py` with `APIRouter`
2. Use `CurrentUser`, `DBSession` from `auth/dependencies.py`
3. Use `{Service}Dep` from `{domain}/dependencies.py`
4. Path params for IDs: `session_id: uuid.UUID` (FastAPI auto-validates)
5. Register in `app/routers.py::include_routers()`

## Add a New Domain

```
src/ii_agent/{domain}/
├── __init__.py       # Export public APIs
├── models.py         # SQLAlchemy models (inherit Base — gives uuid.UUID PK + timestamps)
├── repository.py     # Data access (extends BaseRepository[T])
├── service.py        # Business logic (returns Pydantic, NOT ORM)
├── schemas.py        # Pydantic DTOs (with ConfigDict(from_attributes=True))
├── types.py          # StrEnum types (if domain has enums)
├── dependencies.py   # Factory functions + Dep aliases
├── exceptions.py     # Domain exceptions
└── router.py         # FastAPI endpoints
```

Reference implementation: `tasks/` domain.
Register router in `app/routers.py`.

## Add a New Database Table

1. Define model in `{domain}/models.py`:
   - Inherit `Base` (gives `id: uuid.UUID`, `created_at`, `updated_at`)
   - Use `TimestampColumn` for extra datetime columns (= `DateTime(timezone=True)`)
   - Use `Mapped[uuid.UUID]` with `UUID(as_uuid=True)` for FK columns
2. Run `alembic revision --autogenerate -m "description"`
3. Review + apply: `alembic upgrade head`

## Add a New Socket.IO Handler

1. Create `realtime/handlers/{command}.py` extending `BaseCommandHandler`
2. Add command to `CommandType` enum in `realtime/schemas.py`
3. Register in `CommandHandlerFactory` (`realtime/handlers/factory.py`)

## Add a New Cron Job

1. Create `workers/cron/jobs/{job_name}.py` with async runner
2. Add `CronJobSpec` to `workers/cron/cron_jobs.py::CRON_JOBS`

## Key Import Patterns

```python
# Auth (always needed in routers)
from ii_agent.auth.dependencies import CurrentUser, DBSession

# Domain service dep
from ii_agent.sessions.dependencies import SessionServiceDep

# Settings
from ii_agent.core.config.settings import get_settings

# Container (for non-DI contexts like Socket.IO, cron)
from ii_agent.core.container import get_app_container

# Base + TimestampColumn (for models)
from ii_agent.core.db.base import Base, TimestampColumn
```

## ID Types

```python
# In models:
user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

# In services/repos:
async def get_session(self, db: AsyncSession, session_id: uuid.UUID) -> ...:

# In routers:
@router.get("/{session_id}")
async def get_session(session_id: uuid.UUID, ...):

# In schemas:
from uuid import UUID
class SessionInfo(BaseModel):
    id: UUID
    user_id: UUID
```

## Verify

```bash
python -c "from ii_agent.{domain} import router; print('OK')"
./scripts/start.sh
curl http://localhost:8000/health
```
