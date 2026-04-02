---
name: backend-development
description: Create production-ready FastAPI projects with async patterns, dependency injection, and comprehensive error handling. Use when building new FastAPI applications or setting up backend API projects.
---

# FastAPI Project Templates

Production-ready FastAPI project structures with async patterns, dependency injection, middleware, and best practices for building high-performance APIs.

## When to Use This Skill

- Starting new FastAPI projects from scratch
- Implementing async REST APIs with Python
- Building high-performance web services and microservices
- Creating async applications with PostgreSQL, redis
- Setting up API projects with proper structure and testing
- Pydantic V2 for DTOs and validations

## Core Concepts

### 1. Project Structure

**Recommended Layout:**

```
app/
├── agents/
│   ├── beta/
│   └── v1/
├── prompts/
├── tools/
│   ├── beta/
│   └── v1/             # API routes
├── mcp/
├── migrations/
├── socketio/
├── queues/
├── media/
├── storage
├    ├── client.py
├── core                   # Core configuration
│   ├── config.py
│   ├── security.py
│   └── database.py
├── utils                  # Core configuration
│   ├── models.py
│   ├── openai.py
├── connectors
│   │   ├── router.py
│   │   ├── schemas.py  # pydantic models
│   │   ├── models.py  # db models
│   │   ├── dependencies.py
│   │   ├── config.py  # local configs
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── service.py
│   │   └── utils.py
├── projects
│   │   ├── router.py
│   │   ├── schemas.py  # pydantic models
│   │   ├── models.py  # db models
│   │   ├── dependencies.py
│   │   ├── config.py  # local configs
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── service.py
│   │   └── utils.py
├── metrics
│   │   ├── router.py
│   │   ├── schemas.py  # pydantic models
│   │   ├── models.py  # db models
│   │   ├── dependencies.py
│   │   ├── config.py  # local configs
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── service.py
│   │   └── utils.py
├── billing
│   │   ├── router.py
│   │   ├── schemas.py  # pydantic models
│   │   ├── models.py  # db models
│   │   ├── dependencies.py
│   │   ├── config.py  # local configs
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── service.py
│   │   └── utils.py
├── users
│   │   ├── router.py
│   │   ├── schemas.py  # pydantic models
│   │   ├── models.py  # db models
│   │   ├── dependencies.py
│   │   ├── config.py  # local configs
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── service.py
│   │   └── utils.py
├── chat
│   │   ├── router.py
│   │   ├── schemas.py  # pydantic models
│   │   ├── models.py  # db models
│   │   ├── dependencies.py
│   │   ├── config.py  # local configs
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── service.py
│   │   └── utils.py
├── auth
│   │   ├── router.py
│   │   ├── schemas.py  # pydantic models
│   │   ├── models.py  # db models
│   │   ├── dependencies.py
│   │   ├── config.py  # local configs
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── service.py
│   │   └── utils.py
│── sandboxes 
│   │   ├── client.py  # client model for external service communication
│   │   ├── schemas.py
│   │   ├── config.py
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   └── utils.py
│── sessions
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── models.py
│   │   ├── dependencies.py
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── service.py
│   │   └── utils.py
.........(others critical layers)
└── app.py                 # Application entry
```

### 2. Dependency Injection

FastAPI's built-in DI system using `Depends`:

- Database session management
- Authentication/authorization
- Shared business logic
- Configuration injection

### 3. Async Patterns

Proper async/await usage:

- Async route handlers
- Async database operations
- Async background tasks
- Async middleware

## Implementation Patterns

### Pattern 1: Complete FastAPI Application

```python
# main.py
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    await database.connect()
    yield
    # Shutdown
    await database.disconnect()

app = FastAPI(
    title="API Template",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
from app.api.v1.router import api_router
app.include_router(api_router, prefix="/api/v1")

# core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings."""
    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    API_V1_STR: str = "/api/v1"

settings = Settings()

# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    future=True
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db() -> AsyncSession:
    """Dependency for database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### Pattern 3: Service Layer

```python
# services/user_service.py
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate, User
from app.core.security import get_password_hash, verify_password

class UserService:
    """Business logic for users."""

    def __init__(self):
       

    async def create_user(
        self,
        db: AsyncSession,
        user_in: UserCreate
    ) -> User:
        """Create new user with hashed password."""
        # Check if email exists
        existing = await self.get_by_email(db, user_in.email)
        if existing:
            raise ValueError("Email already registered")

        # Hash password
        user_in_dict = user_in.dict()
        user_in_dict["hashed_password"] = get_password_hash(user_in_dict.pop("password"))

        # Create user
        user = await self.create(db, UserCreate(**user_in_dict))
        return user

    async def authenticate(
        self,
        db: AsyncSession,
        email: str,
        password: str
    ) -> Optional[User]:
        """Authenticate user."""
        user = await self.get_by_email(db, email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def update_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        user_in: UserUpdate
    ) -> Optional[User]:
        """Update user."""
        user = await db.get(db, user_id)
        if not user:
            return None
        
        if user_in.password:
            user.hashed_password = get_password_hash(
                user_in_dict.password
            )
        if user_in.name:
            user.name = user_in.name
        
        return user

user_service = UserService()
```

### Pattern 4: API Endpoints with Dependencies

```python
# api/v1/endpoints/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.schemas.user import User, UserCreate, UserUpdate
from app.services.user_service import user_service
from app.api.dependencies import get_current_user

router = APIRouter()

@router.post("/", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create new user."""
    try:
        user = await user_service.create_user(db, user_in)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/me", response_model=User)
async def read_current_user(
    current_user: User = Depends(get_current_user)
):
    """Get current user."""
    return current_user

@router.get("/{user_id}", response_model=User)
async def read_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user by ID."""
    user = await user_service.get(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.patch("/{user_id}", response_model=User)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update user."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    user = await user_service.update_user(db, user_id, user_in)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete user."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    deleted = await user_service.delete(db, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
```

## Testing

```python
# tests/conftest.py
import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db, Base

TEST_DATABASE_URL = "..."

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        yield session

@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

# tests/test_users.py
import pytest

@pytest.mark.asyncio
async def test_create_user(client):
    response = await client.post(
        "/api/v1/users/",
        json={
            "email": "test@example.com",
            "password": "testpass123",
            "name": "Test User"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
```

## Resources
- **references/async-sqlalchemy.md**: Async/await for sqlalschemy
- **references/testing-async.md**: Comprehensive testing guide
- **references/pydantic-v2.md**: Comprehensive pydandic v2 guide
- **references/endpoints-routing.md**: Comprehensive authentication guide

## Best Practices

1. **Async All The Way**: Use async for database, external APIs
2. **Dependency Injection**: Leverage FastAPI's DI system
4. **Service Layer**: Keep business logic out of routes
5. **Pydantic Schemas**: Strong typing for request/response
6. **Error Handling**: Consistent error responses
7. **Testing**: Test all layers independently
8. **Dataclass**: Use @dataclass for intercomunication, context object, domain objects.. to avoid a lot of method arguments

## Common Pitfalls

- **Blocking Code in Async**: Using synchronous database drivers
- **No Service Layer**: Business logic in route handlers
- **Missing Type Hints**: Loses FastAPI's benefits
- **Ignoring Sessions**: Not properly managing database sessions
- **No Testing**: Skipping integration tests
- **Tight Coupling**: Direct database access in routes


## MUST DO
- Use type hints everywhere (FastAPI requires them)
- Use Pydantic V2 syntax (field_validator, model_validator, model_config)
- Use Annotated pattern for dependency injection
- Use async/await for all I/O operations
- Use X | None instead of Optional[X]
- Return proper HTTP status codes
- Document endpoints (auto-generated OpenAPI)

## MUST NOT DO
- Use synchronous database operations
- Skip Pydantic validation
- Store passwords in plain text
- Expose sensitive data in responses
- Use Pydantic V1 syntax (@validator, class Config)
- Mix sync and async code improperly
- Hardcode configuration values
- Lazy import patterns in __init__.py like this , It's anti pattern and really hard for runtime debugging.
```
def __getattr__(name: str):
    """Lazy import services to avoid circular imports."""
    if name == "agent_service":
        from .agent_service import agent_service
        return agent_service
    elif name == "AgentService":
        from .agent_service import AgentService
        return AgentService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

```

## Best Practices Checklist

### Architecture
- ✅ Domain layer has NO dependencies on API or Infrastructure
- ✅ Business logic lives in domain entities and services
- ✅ Infrastructure implements domain interfaces
- ✅ API layer only handles HTTP concerns


### Database
- ✅ Use SQLAlchemy 2.0 async patterns
- ✅ Separate ORM models from domain entities
- ✅ Implement mapper methods (`_to_entity`)
- ✅ Use connection pooling
- ✅ Handle transactions properly (commit/rollback)

### Testing
- ✅ 100% coverage for domain layer (pure logic)
- ✅ Use AsyncMock for async methods
- ✅ Integration tests for endpoints
- ✅ Separate test database for integration tests

### Naming Conventions
- ✅ Entities: PascalCase (`User`, `Order`)
- ✅ Services: `I{Name}Service` (interface), `{Name}Service` (implementation)(implementation)
- ✅ DTOs: `{Name}Request`, `{Name}Response`
- ✅ Use ptBR names for database columns if applicable

### Error Handling
- ✅ Domain exceptions for business rule violations
- ✅ HTTP exceptions at API layer only
- ✅ Proper status codes (400, 404, 409, 500)
- ✅ Meaningful error messages
- ✅ Global exception handler

## Common Pitfalls to Avoid

1. **Importing Infrastructure in Domain**
   - ❌ Never import SQLAlchemy models in domain layer
   - ✅ Use mapper functions to convert between layers

2. **Business Logic in API Layer**
   - ❌ Never put validation or business rules in endpoints
   - ✅ Move all logic to services or entities

3. **Tight Coupling**
   - ❌ Don't instantiate dependencies directly
   - ✅ Use dependency injection everywhere

4. **Anemic Entities**
   - ❌ Don't use entities as plain data containers
   - ✅ Put behavior and validation in entities

5. **Repository Leakage**
   - ❌ Don't expose SQLAlchemy queries outside repositories
   - ✅ Return domain entities only

6. **Improper Transaction Management**
   - ❌ Don't commit/rollback in repositories
   - ✅ Manage transactions at service or endpoint level

7. **Avoid local package import if possible**
   - ❌ Do not import package under method
   - ✅ Import in head of the file, using TYPE_CHECKING if circular import


8. **Use module import in __init__.py** 
   - ❌ BAD: from agents.agent import Agent (# agents.agent file)
   - ✅ GOOD: from agents import Agent (# agents.agent file, expose Agent in __init__.py)

## Migration Guide (Legacy → Clean Architecture)

### Step 1: Create Domain Layer
1. Extract business entities from database models
2. Define repository interfaces
3. Define service interfaces
4. Move business logic to entities/services

### Step 2: Create Infrastructure Layer
1. Implement repositories with SQLAlchemy
2. Create service implementations
3. Keep database models separate from entities

### Step 3: Refactor API Layer
1. Create request/response DTOs
2. Update endpoints to use services
3. Remove direct database access
4. Add dependency injection

### Step 4: Testing
1. Write unit tests for domain layer
2. Add service tests with mocked repositories
3. Create integration tests for endpoints
4. Ensure 100% coverage

## References

- [Clean Architecture by Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [Pydantic](https://docs.pydantic.dev/)

## Production Examples

This skill is based on patterns from:
- **GEFIN Backend**: Financial management system with 595+ tests
- **Clean Architecture**: Domain-driven design principles
- **Enterprise Best Practices**: Scalability, maintainability, testability


## Knowledge Reference
FastAPI, Pydantic V2, async SQLAlchemy, Alembic migrations, JWT/OAuth2, pytest-asyncio, httpx, BackgroundTasks, WebSockets, dependency injection, OpenAPI/Swagger