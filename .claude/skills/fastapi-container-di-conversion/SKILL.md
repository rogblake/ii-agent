---
name: fastapi-container-di-conversion
description: "Convert FastAPI dependencies.py from factory-wiring to container-primary DI accessor pattern"
---

# FastAPI Container-Primary DI Conversion

**Extracted:** 2026-03-27
**Context:** Converting domain `dependencies.py` files from inline factory-wiring to thin container accessors

## Problem
Service wiring duplicated in two places: `ServiceContainer.create()` and each domain's `dependencies.py` factory functions. DRY violation causes drift.

## Solution

### The Pattern
- `ServiceContainer.create()` = single source of truth for service wiring
- Domain `dependencies.py` = thin accessors pulling from container via `ContainerDep`
- Repositories stay as factory functions (stateless leaf nodes)


```python
from ii_agent.core.dependencies import ContainerDep
from ii_agent.foo.repository import FooRepository
from ii_agent.foo.service import FooService

def get_foo_repository() -> FooRepository:
    return FooRepository()

FooRepositoryDep = Annotated[FooRepository, Depends(get_foo_repository)]

def _get_foo_service(container: ContainerDep) -> FooService:
    return container.foo_service

FooServiceDep = Annotated[FooService, Depends(_get_foo_service)]
```

### Conversion Steps
1. **Check container** — verify `ServiceContainer` has the service as a field
2. **Keep repo factories** — `get_*_repository()` + `*RepositoryDep` unchanged
3. **Replace service factory** — `get_*_service(deps...)` → `_get_*_service(container: ContainerDep)`
4. **Underscore prefix** — `_get_*` (private, not re-exported)
5. **Remove unused imports** — `get_settings()`, cross-domain Dep aliases only used by old factory
6. **Add ContainerDep** — `from ii_agent.core.dependencies import ContainerDep`
7. **Preserve Dep alias name** — `FooServiceDep` stays identical so consumers don't change

### Decision Table
| Component | Pattern | Reason |
|-----------|---------|--------|
| Repository | Factory function | Lightweight, stateless, no cross-deps |
| Service (in container) | Container accessor | Single wiring source |
| Service (NOT in container yet) | Factory function | Until migrated |
| Infrastructure (auth, DB session) | Request-scoped Depends | Per-request lifecycle |
| Composite repos (take other repos) | Factory function | Need Depends chain |

### Mixed Files
When both container-backed and non-container services exist:
- Convert services in container → `_get_*(container: ContainerDep)`
- Keep factory for services not yet in container
- Comment section: `# ---- Services not yet in container ----`

## When to Use
- Adding a new domain module with `dependencies.py`
- Converting existing `dependencies.py` files during DI refactoring
- When a service factory duplicates wiring already in `ServiceContainer.create()`
