# II-Agent Project Guide

## Project Overview

II-Agent is an AI agent platform built with FastAPI and SQLAlchemy 2.0. The codebase follows a domain-driven architecture where business logic is organized into domain modules.

## Architecture

### Domain Structure

```
src/ii_agent/
├── app.py                      # FastAPI application factory & lifespan
│
├── core/                       # Shared infrastructure & configuration
│   ├── config/                 # Pydantic settings (database, redis, storage, oauth, stripe)
│   ├── db/                     # SQLAlchemy base, session management
│   ├── llm/                    # LLM base client utilities
│   ├── redis/                  # Redis client, cache, pubsub, lock, cancel management
│   ├── secrets/                # Secrets management (GCP)
│   └── storage/                # File storage abstraction (GCS, local)
│
├── auth/                       # Authentication & authorization (OAuth, JWT, API keys)
│   └── users/                  # User profiles, waitlist, user CRUD
│
├── billing/                    # Stripe integration (subscriptions, checkout, webhooks)
│   ├── credits/                # Credit balance & usage tracking
│   └── usage/                  # Usage tracking & reporting
│
├── sessions/                   # Chat sessions management (CRUD, state, fork, validation)
│   └── wishlist/               # Session wishlist/bookmarks
│
├── chat/                       # Chat API & LLM providers
│   ├── llm/                    # LLM provider implementations
│   │   └── anthropic/          # Anthropic provider (client, tool handler)
│   ├── media/                  # Media processing in chat
│   │   ├── handlers/           # Media type handlers (image, video, text, default)
│   │   ├── modes/              # Processing modes (conversation, image gen, video gen, web)
│   │   ├── services/           # Media services (image gen, video gen, web search)
│   │   └── utils/              # Media utilities
│   ├── tools/                  # Chat tools (code interpreter, tool registry)
│   └── vectorstore/            # Vector store integration (OpenAI)
│
├── engine/                     # Agent execution framework
│   ├── agents/                 # Agent run management & execution
│   │   └── parser/             # Response parsers (Claude)
│   ├── prompts/                # System prompts & templates
│   ├── sandboxes/              # Sandbox environment management (E2B)
│   └── v1/                     # V1 agent architecture
│       ├── agent_sessions/     # V1 session management
│       ├── agents/             # V1 agent implementations
│       ├── api/                # V1 API endpoints
│       ├── db/                 # V1 database utilities
│       ├── factory/            # V1 agent factory
│       ├── hooks/              # V1 lifecycle hooks
│       ├── media/              # V1 media handling
│       ├── models/             # V1 LLM provider models
│       │   ├── anthropic/      # Anthropic provider
│       │   ├── cerebras/       # Cerebras provider
│       │   ├── custom/         # Custom provider
│       │   ├── google/         # Google provider
│       │   ├── openai/         # OpenAI provider
│       │   └── vertexai/       # Vertex AI provider
│       ├── run/                # V1 run management
│       ├── skills/             # V1 skills framework
│       │   ├── builtin/        # Built-in skills (docx, pdf, pptx, xlsx, research-to-website)
│       │   └── skills_ref/     # Skill reference data
│       ├── tools/              # V1 tool implementations
│       │   ├── a2a/            # Agent-to-Agent tools
│       │   ├── agent/          # Agent tools
│       │   ├── browser/        # Browser tools
│       │   ├── connectors/     # Connector tools
│       │   ├── dev/            # Dev tools
│       │   ├── file_system/    # File system tools
│       │   ├── mcp/            # MCP tools
│       │   ├── media/          # Media tools
│       │   ├── plan/           # Planning tools
│       │   ├── productivity/   # Productivity tools
│       │   ├── sandbox/        # Sandbox tools
│       │   ├── shell/          # Shell tools
│       │   ├── slide_system/   # Slide tools
│       │   └── web/            # Web tools
│       └── utils/              # V1 utilities
│
├── content/                    # Content generation
│   ├── media/                  # Media templates & tools (reference images)
│   │   └── config/             # Media configuration
│   ├── skills/                 # Custom skills management
│   ├── slides/                 # Slide/presentation generation
│   │   └── templates/          # Slide templates
│   └── storybook/              # Storybook generation
│
├── files/                      # File upload/download service
│
├── integrations/               # External integrations
│   ├── a2a/                    # Agent-to-Agent protocol support
│   ├── connectors/             # External connectors (GitHub, Google Drive)
│   │   └── composio/           # Composio integration
│   └── mcp_sse/                # MCP SSE server for ChatGPT integration
│
├── projects/                   # Project & deployment management
│   ├── cloud_run/              # Google Cloud Run deployment
│   │   └── assets/             # Deployment assets
│   ├── databases/              # Database provisioning
│   ├── deployments/            # Deployment management
│   ├── secrets/                # Project secrets management
│   └── subdomains/             # Subdomain management
│
├── realtime/                   # Real-time communication
│   ├── events/                 # Event handling & logging
│   ├── socket/                 # WebSocket/Socket.IO handlers
│   │   └── command/            # Socket command handlers (query, cancel, plan)
│   └── subscribers/            # Event subscribers (metrics, database)
│
├── settings/                   # User settings
│   ├── llm/                    # User LLM model configuration
│   │   └── store/              # Settings persistence (file store)
│   └── mcp/                    # MCP server configuration
│
├── utils/                      # Shared utilities
└── scripts/                    # Admin scripts (credit refresh, waitlist import)
```

### Import Patterns

#### From Domain Module (Preferred)

```python
# Import from domain __init__.py - exports models, services, router, schemas
from ii_agent.sessions import Session, session_service, router, SessionInfo
from ii_agent.auth import CurrentUser, DBSession, get_current_user, router
from ii_agent.billing import BillingTransaction, router
from ii_agent.files import FileUpload, file_service
from ii_agent.projects import Project, project_service
```

#### Direct Imports (When Needed)

```python
# Models
from ii_agent.auth.users.models import User, LLMSetting, MCPSetting, APIKey
from ii_agent.sessions.models import Session, SessionStateEnum
from ii_agent.core.db.base import Base, TimestampColumn

# Services
from ii_agent.sessions.service import SessionService
from ii_agent.auth.users.service import UserService
from ii_agent.realtime.events.service import EventService

# Database utilities
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.engine.agents.models import AgentRunTask
```

### Service Pattern

Services take `db: AsyncSession` as first parameter. Singleton initialized at module level:

```python
# In sessions/service.py:
class SessionService:
    def __init__(self, file_store: BaseStorage, config: Settings) -> None:
        self._file_store = file_store
        self._config = config

    async def get_session(self, db: AsyncSession, session_id: str) -> Session | None:
        result = await db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

# Initialize singleton at end of file
session_service = SessionService(file_store=storage, config=get_settings())
```

### Dependency Injection Pattern (`dependencies.py`)

Each domain has a `dependencies.py` that defines factory functions and `Dep` type aliases using `Annotated`. **Always use Dep aliases** — both in routers and in other factory functions that compose dependencies.

#### Structure rules

1. **Define Dep aliases immediately after** the factory they wrap (before any factory that uses them).
2. **Use Dep aliases everywhere** — never use bare `= Depends(get_x)` in function signatures (exception: `credentials: HTTPAuthorizationCredentials = Depends(security)` in auth, which is a FastAPI security scheme).
3. **Import Dep aliases** from other domains instead of importing their factory functions.

```python
# In sessions/dependencies.py:
from typing import Annotated
from fastapi import Depends

from ii_agent.engine.agents.dependencies import AgentRunServiceDep      # Cross-domain Dep alias
from ii_agent.engine.sandboxes.dependencies import SandboxRepositoryDep
from ii_agent.realtime.events.dependencies import EventRepositoryDep
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.service import SessionService

# 1. Factory function
def get_session_repository() -> SessionRepository:
    return SessionRepository()

# 2. Dep alias defined IMMEDIATELY after its factory
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]

# 3. Downstream factories use Dep aliases, not Depends(get_x)
def get_session_service(
    session_repo: SessionRepositoryDep,          # <-- Dep alias (local)
    event_repo: EventRepositoryDep,              # <-- Dep alias (cross-domain)
    sandbox_repo: SandboxRepositoryDep,          # <-- Dep alias (cross-domain)
    agent_run_service: AgentRunServiceDep,        # <-- Dep alias (cross-domain)
) -> SessionService:
    return SessionService(...)

SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
```

#### Anti-patterns (DO NOT)

```python
# BAD: bare Depends(get_x) — use the Dep alias instead
def get_session_service(
    session_repo: SessionRepository = Depends(get_session_repository),
) -> SessionService: ...

# BAD: importing factory functions from other domains for Depends()
from ii_agent.engine.agents.dependencies import get_agent_run_service
# GOOD: import the Dep alias
from ii_agent.engine.agents.dependencies import AgentRunServiceDep

# BAD: defining Dep aliases at the bottom of the file, after factories that need them
def get_session_service(session_repo: SessionRepositoryDep): ...  # NameError!
SessionRepositoryDep = Annotated[...]  # Too late

# BAD: creating local Dep aliases that duplicate core ones
DefaultStorageDep = Annotated[BaseStorage, Depends(get_storage)]  # Use StorageDep from core.storage.dependencies
```

### Router Pattern

Use Dep aliases for auth, database, and all service dependencies:

```python
# In sessions/router.py:
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

### Domain `__init__.py` Pattern

Export all public APIs from domain module:

```python
# In sessions/__init__.py:
from .models import Session, SessionStateEnum, ConversationSummary
from .service import SessionService, session_service, Sessions
from .router import router
from .schemas import SessionCreate, SessionInfo, SessionList

__all__ = [
    "Session", "SessionStateEnum", "ConversationSummary",
    "SessionService", "session_service", "Sessions",
    "router",
    "SessionCreate", "SessionInfo", "SessionList",
]
```

### SQLAlchemy 2.0 Models

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

## Development Guidelines

### Adding a New Domain

1. Create domain folder: `src/ii_agent/{domain_name}/`
2. Create files:
   - `__init__.py` - Export all public APIs
   - `models.py` - SQLAlchemy models
   - `repository.py` - Data access layer
   - `service.py` - Business logic
   - `dependencies.py` - Factory functions & Dep aliases
   - `router.py` - FastAPI endpoints
   - `schemas.py` - Pydantic request/response DTOs
   - `exceptions.py` - Domain-specific exceptions
3. Register router in `app.py`

### Verification

```bash
# Verify imports
python -c "from ii_agent.sessions import Session, session_service; print('OK')"

# Start server
./start.sh

# Health check
curl http://localhost:8000/health
```

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app factory, router registration, lifespan |
| `core/config/settings.py` | Pydantic settings (get_settings singleton) |
| `core/db/base.py` | SQLAlchemy Base, TimestampColumn |
| `core/db/manager.py` | get_db_session_local, SessionLocal |
| `core/redis/` | Redis client, cache, pubsub, lock, cancel management |
| `core/storage/` | File storage abstraction (GCS, local) |
| `core/secrets/` | Secrets management (GCP Secret Manager) |
| `auth/dependencies.py` | CurrentUser, DBSession, get_current_user |
| `engine/v1/` | V1 agent architecture with tools, skills, and multi-provider LLM support |
