---
paths:
  - "**/*.py"
---
# Python Pydantic V2 & FastAPI Conventions

## Pydantic Models Over Raw Dicts

**NEVER use raw `dict` for structured data.** Always define a Pydantic model.

```python
# BAD
def create_event(data: dict) -> dict:
    return {"type": data["type"], "payload": data.get("payload")}

# GOOD
from pydantic import BaseModel

class EventData(BaseModel):
    type: EventType
    payload: dict[str, Any] | None = None
```

When to use which:
- **Pydantic `BaseModel`** — API schemas, configuration, any data crossing boundaries
- **`BaseModel` with `model_config = ConfigDict(frozen=True)`** — immutable value objects
- **`TypedDict`** — only when interfacing with third-party APIs that expect plain dicts
- **raw `dict`** — NEVER for structured data; only for truly dynamic key-value mappings

## Enums Over String Constants

**NEVER use string literals as constants or discriminators.** Define a `StrEnum`.

```python
# BAD
STATUS_ACTIVE = "active"
if event.type == "user_created":
    ...

# GOOD
from enum import StrEnum

class Status(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class EventType(StrEnum):
    USER_CREATED = "user_created"

if event.type == EventType.USER_CREATED:
    ...
```

- Use `StrEnum` for string-valued enums (serializes naturally to/from JSON)
- Use `IntEnum` for integer-valued enums
- Never duplicate enum values as standalone string constants

## No getattr / hasattr Checks

**NEVER use `getattr()` or `hasattr()` to access model attributes.** These bypass type checking.

```python
# BAD
name = getattr(user, "name", None)
if hasattr(event, "payload"):
    process(event.payload)
value = getattr(config, "timeout", 30)

# GOOD — direct attribute access with proper typing
name: str | None = user.name

# GOOD — defaults handled by the model itself
class Config(BaseModel):
    timeout: int = 30
value = config.timeout

# GOOD — pattern matching for polymorphism
match event:
    case UserCreatedEvent():
        process(event.payload)
```

Only acceptable exceptions: test utilities, third-party dynamic objects, framework metaprogramming.

## Imports: Top-Level Only

**NEVER use local imports inside functions/methods.** All imports must be at the top of the file.

```python
# BAD — local import
def process_event(event: Event) -> None:
    from ii_agent.billing.credits.service import CreditService  # hidden dependency
    service = CreditService()
    ...

# GOOD — top-level import
from ii_agent.billing.credits.service import CreditService

def process_event(event: Event) -> None:
    service = CreditService()
    ...
```

The **only** exception is `TYPE_CHECKING` — use it to break circular imports for type annotations only:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ii_agent.sessions.models import Session
    from ii_agent.auth.users.models import User

class EventService:
    async def process(self, session: Session, user: User) -> None:
        ...
```

- `TYPE_CHECKING` imports are erased at runtime — they exist solely for type checkers (mypy/pyright)
- Never put runtime logic inside `if TYPE_CHECKING`
- Never use local imports to "avoid circular imports" — restructure the module or use `TYPE_CHECKING` instead

## Async-First

- All I/O-bound functions **must** be `async`
- Never use synchronous I/O in async code paths (`requests`, blocking `open()`)
- Use `asyncio.gather()` for concurrent independent operations
- Use `asyncio.TaskGroup` (Python 3.11+) for structured concurrency

## FastAPI + Pydantic V2

- Use Pydantic models for all request bodies and response schemas
- Use `Annotated[T, Depends(...)]` for dependency injection
- Return Pydantic models from endpoints, not dicts
- Use `model_config = ConfigDict(...)` instead of inner `class Config`
- Use `model_validator` / `field_validator` instead of `@validator` / `@root_validator`
- Use `model_dump()` / `model_dump_json()` instead of `.dict()` / `.json()`

```python
# BAD
@router.post("/users")
async def create_user(data: dict):
    return {"id": "123", "name": data["name"]}

# GOOD
class CreateUserRequest(BaseModel):
    name: str
    email: str

class UserResponse(BaseModel):
    id: str
    name: str

@router.post("/users", status_code=201, response_model=UserResponse)
async def create_user(body: CreateUserRequest) -> UserResponse:
    ...
```
