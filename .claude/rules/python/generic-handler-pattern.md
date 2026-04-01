---
paths:
  - "src/ii_agent/realtime/handlers/**/*.py"
  - "src/ii_agent/realtime/schemas.py"
---
# Generic Handler Pattern (BaseCommandHandler[TContent])

## The Rule

**Every handler MUST declare its content type via `_content_type` and `Generic[TContent]`.** Never accept `dict[str, Any]` in `handle()`.

## Architecture

```
Manager.chat_message()
  │
  ▼  raw dict
handler.dispatch(raw_content: dict, session_info)
  │  Pydantic validation (automatic, base class)
  ▼  typed model
handler.handle(content: TContent, session_info)
  │  Business logic (subclass)
  ▼
```

- `dispatch()` is the entry point (called by `SocketIOManager`) — **never override it**
- `handle()` is the abstract method subclasses implement — receives a **validated Pydantic model**
- Validation errors are automatically sent to the client as `validation_error` events

## Required Structure for Every Handler

```python
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.schemas import MyContent  # or EmptyContent

class MyHandler(BaseCommandHandler[MyContent]):
    """Handler for my_command."""

    _content_type = MyContent  # REQUIRED — must match the Generic parameter

    def get_command_type(self) -> CommandType:
        return CommandType.MY_COMMAND

    async def handle(self, content: MyContent, session_info: SessionInfo) -> None:
        # content is already validated — use attribute access directly
        value = content.some_field  # GOOD
        # value = content.get("some_field")  # BAD — this is a Pydantic model, not a dict
```

## Content Model Rules

1. **Define in `realtime/schemas.py`** — all content models live here
2. **Add to `CommandContent` union** — every new model must be added
3. **Use `EmptyContent`** for handlers that need no payload (ping, cancel, status checks)
4. **Required fields = Pydantic required** — no `field | None = None` for truly required fields
5. **Use `field_validator`** for domain validation (e.g., 6-digit codes, non-empty strings)
6. **Use `ConfigDict(extra="allow")`** only when the frontend may send extra fields

```python
# GOOD — required fields are required, optional have defaults
class ContinueRunContent(BaseModel):
    run_id: str                     # required — Pydantic enforces this
    confirmed: bool                 # required
    user_input: dict[str, str] = {} # optional with default

# BAD — manual validation of required fields
class ContinueRunContent(BaseModel):
    run_id: str | None = None       # DON'T — let Pydantic enforce required
    confirmed: bool | None = None   # DON'T
```

## Anti-Patterns (DO NOT)

```python
# BAD: dict in handle signature
async def handle(self, content: dict[str, Any], session_info: SessionInfo) -> None:

# BAD: manual .get() extraction inside handle
run_id = content.get("run_id")
if run_id is None:
    await self._send_error_event(...)
    return

# BAD: manual model construction inside handle
query_command = QueryCommandContent(**content)

# BAD: calling handle() from external code (use dispatch)
await handler.handle(raw_dict, session)  # NO
await handler.dispatch(raw_dict, session)  # YES

# BAD: missing _content_type class variable
class MyHandler(BaseCommandHandler[MyContent]):
    # forgot _content_type = MyContent  →  defaults to EmptyContent

# BAD: handler-to-handler delegation via handle()
await self._query_handler.handle(query_content.model_dump(), session_info)  # NO
await self._query_handler.dispatch(query_content.model_dump(), session_info)  # YES
```

## Adding a New Handler — Checklist

1. Define content model in `realtime/schemas.py`
2. Add model to `CommandContent` union type
3. Add `CommandType` enum value in `schemas.py`
4. Create handler class with `BaseCommandHandler[MyContent]` and `_content_type = MyContent`
5. Register in `CommandHandlerFactory._initialize_handlers()`
6. Tests call `handler.dispatch({...}, session)`, never `handler.handle()`

## Reference Implementation

`realtime/handlers/continue_run.py` — clean example with required + optional fields.
`realtime/handlers/ping.py` — minimal example with `EmptyContent`.
