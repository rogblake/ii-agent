# Design Patterns

This document describes the recurring patterns used throughout the II-Agent codebase. Follow these patterns when adding new code to maintain consistency.

For the full reference with code examples, see `CLAUDE.md`.

## Domain Module Structure

Every domain follows this file layout:

```
src/ii_agent/{domain_name}/
├── __init__.py         # Export all public APIs
├── models.py           # SQLAlchemy 2.0 models
├── repository.py       # Data access layer (queries)
├── service.py          # Business logic
├── dependencies.py     # Factory functions & Dep aliases
├── router.py           # FastAPI endpoints
├── schemas.py          # Pydantic request/response DTOs
└── exceptions.py       # Domain-specific exceptions
```

Not every domain has all files. Simpler domains may omit `repository.py` or `exceptions.py`.

## Service Pattern

Services are stateless classes. All state lives in the database. The `db: AsyncSession` parameter is always first.

```python
class SessionService:
    async def get_session(self, db: AsyncSession, session_id: str) -> Session | None:
        result = await db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()
```

Services may be initialized as singletons at module level or constructed via dependency injection factories.

## Dependency Injection (Dep Aliases)

Every domain defines Dep aliases using `Annotated[T, Depends(factory)]`. These are the ONLY way to inject dependencies into routers and other factories.

```python
# 1. Factory function
def get_session_repository() -> SessionRepository:
    return SessionRepository()

# 2. Dep alias defined IMMEDIATELY after its factory
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]

# 3. Downstream factories use Dep aliases
def get_session_service(
    session_repo: SessionRepositoryDep,
    event_repo: EventRepositoryDep,        # Cross-domain Dep alias
) -> SessionService:
    return SessionService(session_repo, event_repo)

SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
```

### Rules

- Define Dep alias **immediately after** its factory function.
- **Use Dep aliases everywhere** — in routers AND in other factory functions.
- **Import Dep aliases** from other domains, never their factory functions.
- Never use bare `= Depends(get_x)` in function signatures.

## SQLAlchemy 2.0 Models

All models use the `mapped_column` style with explicit type annotations:

```python
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ii_agent.core.db.base import Base, TimestampColumn

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    state: Mapped[SessionStateEnum] = mapped_column(default=SessionStateEnum.IDLE)

    user: Mapped["User"] = relationship(back_populates="sessions")
```

- Use `TimestampColumn` or `TimestampMixin` for `created_at`/`updated_at`.
- Use `Mapped[T]` for all column type declarations.
- Define relationships with string forward references.

## Router Pattern

Routers use Dep aliases for all dependencies:

```python
from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.sessions.dependencies import SessionServiceDep

router = APIRouter(prefix="/sessions", tags=["Sessions"])

@router.get("/{session_id}")
async def get_session(
    session_id: str,
    current_user: CurrentUser,
    db: DBSession,
    session_service: SessionServiceDep,
):
    return await session_service.get_session(db, session_id)
```

## Domain `__init__.py` Exports

Export all public APIs from the domain's `__init__.py`:

```python
from .models import Session, SessionStateEnum
from .service import SessionService
from .router import router
from .schemas import SessionCreate, SessionInfo

__all__ = ["Session", "SessionStateEnum", "SessionService", "router", "SessionCreate", "SessionInfo"]
```

## Error Handling

- Domain-specific exceptions go in `exceptions.py`.
- Use FastAPI's `HTTPException` only in routers, never in services.
- Services raise domain exceptions; routers catch and convert to HTTP responses.

## Configuration

All configuration uses the `Settings` singleton from `core/config/settings.py`:

```python
from ii_agent.core.config.settings import get_settings

settings = get_settings()
```

Settings support environment variables, `.env` files, and GCP Secret Manager (in production).
