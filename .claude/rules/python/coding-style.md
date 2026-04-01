---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Coding Style

> This file extends [common/coding-style.md](../common/coding-style.md) with Python specific content.

## Standards

- Follow **PEP 8** conventions
- Use **type annotations** on all function signatures

## Immutability

Prefer immutable data structures:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    name: str
    email: str

from typing import NamedTuple

class Point(NamedTuple):
    x: float
    y: float
```

## Package Imports & `__init__.py` (MANDATORY)

This is a **strict, non-negotiable rule**. All Python code in this project MUST follow package-level imports. Violating this rule means the code is incorrect and must be fixed.

### The Core Rule

**NEVER import directly from an internal module file. ALWAYS import from the package (directory) that contains it.**

A "package" is a directory with an `__init__.py`. The `__init__.py` is the package's public API. When you write `from genii.agents.sessions import AgentSession`, Python resolves this by looking at `genii/agents/sessions/__init__.py`, which must re-export `AgentSession`.

### How to determine the correct import path

1. Identify where the symbol is defined (e.g., `AgentSession` lives in `genii/agents/sessions/agent.py`)
2. Find the nearest `__init__.py` that exports it (e.g., `genii/agents/sessions/__init__.py` has `from .agent import AgentSession`)
3. Your import path is that package: `from genii.agents.sessions import AgentSession`

**The import path stops at the package directory, NOT the .py file.**

### Correct vs Incorrect examples

```python
# === CORRECT: Import from the PACKAGE (the directory with __init__.py) ===
from genii.agents.sessions import AgentSession
from genii.events import EventBus, Event
from genii.config import Settings
from myapp.models import User, Order
from myapp.services import PaymentService

# === INCORRECT: Import from the MODULE FILE (the .py file) ===
# DO NOT DO THIS — these reach into the internal .py file
from genii.agents.sessions.agent import AgentSession      # BAD: ".agent" is the file
from genii.events.bus import EventBus                      # BAD: ".bus" is the file
from genii.config.settings import Settings                 # BAD: ".settings" is the file
from myapp.models.user import User                         # BAD: ".user" is the file
from myapp.services.payment import PaymentService          # BAD: ".payment" is the file
```

### Why this matters

- **Clean API boundaries** — Consumers depend on the package, not its internal file structure. You can refactor, rename, or split internal files without breaking consumers.
- **Readable imports** — `from genii.events import EventBus` is shorter and clearer than `from genii.events.bus import EventBus`.
- **Enforced encapsulation** — Internal modules are implementation details. Only what's in `__init__.py` is public.

### `__init__.py` requirements

Every package's `__init__.py` MUST:

1. **Re-export all public symbols** from its internal modules using relative imports
2. **Define `__all__`** listing every public symbol explicitly

```python
# genii/agents/sessions/__init__.py
from .agent import AgentSession
from .manager import SessionManager

__all__ = ["AgentSession", "SessionManager"]
```

### When creating or modifying code

- **Adding a new class/function to an existing module** → Update the package's `__init__.py` to export it, then import from the package everywhere.
- **Creating a new .py file in a package** → Add exports for its public symbols to the package's `__init__.py`.
- **Creating a new package (directory)** → Create `__init__.py` with all public exports and `__all__`.
- **Refactoring/moving code** → Update `__init__.py` re-exports. Consumer imports should NOT need to change if they use package-level imports.

### Parent package convenience re-exports (optional)

Parent packages MAY re-export commonly used symbols for shorter import paths:

```python
# genii/agents/__init__.py — re-exports from child packages
from .sessions import AgentSession
from .base import BaseAgent

__all__ = ["AgentSession", "BaseAgent"]

# Now consumers can do:
from genii.agents import AgentSession  # shorter, still correct
```

### Import order (enforced by isort/ruff)

```python
# 1. Standard library
import os
from pathlib import Path

# 2. Third-party packages
from pydantic import BaseModel

# 3. Local application — ALWAYS package-level imports
from genii.agents.sessions import AgentSession
from genii.events import EventBus
```

## Formatting

- **black** for code formatting
- **isort** for import sorting
- **ruff** for linting

## Reference

See skill: `python-patterns` for comprehensive Python idioms and patterns.
