---
paths:
  - "**/*.py"
---
# Python Strict Typing Rules

## Mandatory Type Annotations

**Every function, method, and variable assignment at module/class scope MUST have type annotations.**

```python
# BAD — missing return type
def get_user(db, user_id):
    ...

# BAD — missing parameter types
async def process(self, data, session):
    ...

# GOOD — all params and return typed
async def process(self, data: QueryContent, session: SessionInfo) -> None:
    ...

def get_user(db: AsyncSession, user_id: uuid.UUID) -> UserResponse:
    ...
```

## No `Any` at Boundaries

**NEVER use `Any` for data crossing system boundaries** (WebSocket payloads, API requests, service method params). Define a Pydantic model or TypedDict instead.

```python
# BAD — Any at a boundary
async def handle(self, content: dict[str, Any], session: SessionInfo) -> None:
    name = content.get("name")  # no type safety

# GOOD — typed model at a boundary
async def handle(self, content: MyContent, session: SessionInfo) -> None:
    name = content.name  # str, type-checked
```

**Acceptable uses of `Any`:**
- Third-party library return types that are genuinely dynamic
- Generic utility code (serializers, loggers)
- `**kwargs` in event/content dicts that are truly open-ended

## Generic Types for Polymorphic Handlers

**When a base class processes data whose type varies per subclass, use `Generic[T]` with a `ClassVar` selector — not `Any`.**

```python
# BAD — loses type info
class BaseHandler(ABC):
    async def handle(self, content: dict[str, Any]) -> None: ...

# GOOD — preserves type info per subclass
TContent = TypeVar("TContent", bound=BaseModel)

class BaseHandler(ABC, Generic[TContent]):
    _content_type: ClassVar[type[BaseModel]]

    async def dispatch(self, raw: dict[str, Any]) -> None:
        content = self._content_type.model_validate(raw)
        await self.handle(content)

    @abstractmethod
    async def handle(self, content: TContent) -> None: ...
```

## `dict` vs Pydantic Model Decision Tree

```
Is the data structured (known keys)?
  ├── YES → Use a Pydantic BaseModel
  │         Is it immutable? → Add ConfigDict(frozen=True)
  │         Does it cross a boundary? → MUST be a model
  └── NO  → Is it truly dynamic (user-defined keys)?
            ├── YES → dict[str, ValueType] is OK
            └── NO  → You probably know the keys — use a model
```

## Attribute Access — Never `.get()` on Models

```python
# BAD — dict-style access on Pydantic models
name = content.get("name", "")
if content.get("confirmed") is None:
    ...

# GOOD — direct attribute access
name = content.name
confirmed = content.confirmed
```

## Union Types Over Optional Flags

```python
# BAD — stringly-typed discrimination
class Event(BaseModel):
    type: str  # "user" | "system"
    user_data: dict | None = None
    system_data: dict | None = None

# GOOD — discriminated union
class UserEvent(BaseModel):
    type: Literal["user"]
    user_data: UserData

class SystemEvent(BaseModel):
    type: Literal["system"]
    system_data: SystemData

Event = UserEvent | SystemEvent
```

## ClassVar vs Instance Variable

```python
# BAD — instance variable for class-level constant
class MyHandler(BaseHandler[MyContent]):
    def __init__(self):
        self._content_type = MyContent  # re-assigned per instance

# GOOD — ClassVar for class-level constant
class MyHandler(BaseHandler[MyContent]):
    _content_type: ClassVar[type[BaseModel]] = MyContent  # set once, shared
```

## Return Types

- **Services** return Pydantic schemas, NEVER ORM models
- **Repositories** return ORM models or `None`
- **Handlers** return `None` (side-effect only)
- Use `T | None` instead of `Optional[T]`
- Use `list[T]` instead of `List[T]` (Python 3.9+ builtins)

## Import Style for Types

```python
# Use lowercase builtins (Python 3.9+)
x: dict[str, Any]     # GOOD
x: Dict[str, Any]     # BAD — deprecated typing.Dict

x: list[str]           # GOOD
x: List[str]           # BAD

x: tuple[int, str]     # GOOD
x: Tuple[int, str]     # BAD

x: str | None          # GOOD
x: Optional[str]       # BAD — less readable
```
