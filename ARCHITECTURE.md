# II-Agent Architecture

## Domain Map

II-Agent is organized into domain modules under `src/ii_agent/`. Each domain owns its models, repository, service, dependencies, router, and schemas.

```
src/ii_agent/
├── app/                    # FastAPI bootstrap package, middleware, lifespan, router wiring
│
├── core/                   # Shared infrastructure (no business logic)
│   ├── config/             # Pydantic settings (database, redis, storage, oauth, stripe)
│   ├── db/                 # SQLAlchemy 2.0 base, async session management, migrations
│   ├── llm/                # LLM billing service, execution service, base client
│   ├── redis/              # Redis client, cache, pubsub, lock, cancel management
│   ├── secrets/            # GCP Secret Manager integration
│   ├── storage/            # File storage abstraction (GCS, local)
│   ├── container.py        # ServiceContainer for complex dependency graphs
│   └── dependencies.py     # DBSession, SettingsDep (shared Dep aliases)
│
├── auth/                   # Authentication & authorization
│   ├── jwt_handler.py      # JWT creation/verification (HS256)
│   ├── oidc_verify.py      # OIDC token verification (RS/ES families)
│   ├── api_key_utils.py    # API key generation
│   └── users/              # User profiles, CRUD, waitlist
│
├── billing/                # Credit ledger & billing
│   ├── credits/            # Balance, ledger, pricing, service
│   ├── reservations/       # Reserve -> settle -> release state machine
│   ├── outbox/             # Durable billing usage facts
│   ├── usage/              # Usage records, LLM/tool invocation telemetry
│   ├── customers/          # Stripe customer management
│   └── webhook_handler.py  # Stripe webhook processing
│
├── sessions/               # Chat session management
│   ├── models.py           # Session model, SessionStateEnum, AppKind
│   ├── service.py          # Session CRUD, state transitions
│   ├── fork_service.py     # Session forking
│   ├── title_service.py    # Auto-title generation
│   ├── wishlist/           # Session bookmarks
│   └── pin/                # Pinned sessions
│
├── agent/                  # Agent execution framework
│   ├── application/        # Validation, execution orchestration
│   ├── runtime/            # Agent runtime models, streaming
│   ├── runs/               # Agent run task management
│   ├── events/             # Event handling & logging
│   ├── prompts/            # System prompts & templates
│   ├── sandboxes/          # E2B sandbox management
│   ├── socket/             # Socket.IO command handlers (query, cancel, plan)
│   └── subscribers/        # Event subscribers (metrics, database)
│
├── chat/                   # Chat API & LLM providers
│   ├── api/                # Chat REST endpoints
│   ├── llm/                # LLM provider implementations (Anthropic)
│   ├── media/              # Media processing (image gen, video gen, web search)
│   ├── runs/               # Chat run management
│   ├── tools/              # Chat tools (code interpreter, tool registry)
│   └── vectorstore/        # Vector store integration (OpenAI)
│
├── content/                # Content generation
│   ├── media/              # Media templates, tools, config
│   ├── skills/             # Custom skills management
│   ├── slides/             # Slide/presentation generation + templates + design
│   └── storybook/          # Storybook generation
│
├── files/                  # File upload/download service
│
├── integrations/           # External integrations
│   ├── a2a/                # Agent-to-Agent protocol
│   ├── connectors/         # External connectors (GitHub, Google Drive via Composio)
│   ├── enhance_prompt/     # Prompt enhancement
│   ├── mcp_sse/            # MCP SSE server for ChatGPT integration
│   └── mobile/             # Mobile platform integrations (Apple, future Android)
│
├── projects/               # Project & deployment management
│   ├── cloud_run/          # Google Cloud Run deployment
│   ├── databases/          # Database provisioning
│   ├── deployments/        # Deployment orchestration
│   ├── design/             # Project design
│   ├── secrets/            # Project-level secrets
│   └── subdomains/         # Subdomain management
│
├── settings/               # User settings
│   ├── llm/                # User LLM model preferences
│   └── mcp/                # MCP server configuration
│
├── utils/                  # Shared utilities
├── workers/                # Background jobs (Celery cron)
├── scripts/                # Admin scripts
└── ws_server.py            # WebSocket server entry point
```

## Layer Architecture

Within each domain, code follows a fixed layer hierarchy. Dependencies flow downward only.

```
    Router (FastAPI endpoints)
      |
    Dependencies (Dep aliases, factory functions)
      |
    Service (business logic, takes db: AsyncSession)
      |
    Repository (data access, SQLAlchemy queries)
      |
    Models (SQLAlchemy 2.0 declarative models)
      |
    Schemas (Pydantic DTOs for request/response)
```

### Layer Rules

- **Models** may only import from `core.db` and standard library.
- **Repository** imports models and core utilities. Never imports services.
- **Service** imports repository and models. May import other services' Dep aliases for cross-domain work.
- **Dependencies** defines factory functions and Dep aliases. Imports services and repositories.
- **Router** imports Dep aliases from dependencies. Never imports repositories directly.
- **Schemas** are pure Pydantic models. No database or service imports.

## Cross-Cutting Concerns

These `core/` modules are available to all domains:

| Module | Purpose | Key exports |
|--------|---------|-------------|
| `core/config/` | Application settings | `Settings`, `get_settings()` |
| `core/db/` | Database connection | `Base`, `TimestampColumn`, `get_db_session_local()` |
| `core/redis/` | Caching, pubsub, locks | `redis_client`, `EntityCache`, `AsyncIOPubSub` |
| `core/storage/` | File storage (GCS) | `BaseStorage`, `storage`, `media_storage` |
| `core/llm/` | LLM billing & execution | `LLMBillingService`, `LLMExecutionService` |
| `core/secrets/` | Secret management | GCP Secret Manager integration |
| `core/dependencies.py` | Shared Dep aliases | `DBSession`, `SettingsDep` |
| `core/container.py` | Service container | `ServiceContainer` |

## Request Flow

```
HTTP Request
  -> FastAPI middleware (CORS, trusted hosts)
    -> Auth dependency (get_current_user -> JWT/OIDC/API key verification)
      -> Router endpoint
        -> Service (business logic + billing reservation if needed)
          -> Repository (SQLAlchemy queries)
            -> PostgreSQL
          -> External APIs (LLM providers, GCS, Stripe, E2B)
        -> Response schema (Pydantic serialization)
  -> HTTP Response

WebSocket (Socket.IO)
  -> Socket.IO server (app/)
    -> Auth via handshake token
      -> Command handler (agent/socket/)
        -> Agent runtime (agent/runtime/)
          -> LLM provider (streaming)
          -> Tool execution (sandboxes, file system, web)
        -> Event subscribers (metrics, database persistence)
      -> Real-time events back to client
```

## API Surface

| Router | Prefix | Domain |
|--------|--------|--------|
| auth | `/auth` | Authentication |
| users | `/auth/me` | User profiles |
| sessions | `/sessions` | Chat sessions |
| credits | `/credits` | Credit balance |
| billing | `/billing` | Stripe billing |
| chat | `/chat` | Chat API |
| files | `/files` | File uploads |
| project | `/project` | Projects |
| subdomains | `/subdomains` | Subdomain management |
| llm_settings | `/user-settings/models` | LLM preferences |
| mcp_settings | `/user-settings/mcp` | MCP config |
| skills_settings | `/user-settings/skills` | Custom skills |
| slides | `/slides` | Slide generation |
| slide_templates | `/slide-templates` | Slide templates |
| storybook | `/storybooks` | Storybook generation |
| media | `/media` | Media generation |
| media_templates | `/media-templates` | Media templates |
| media_tools | `/media-tools` | Media tools |
| connectors | `/connectors` | External connectors |
| enhance_prompt | `/enhance-prompt` | Prompt enhancement |
| wishlist | `/wishlist` | Session bookmarks |
| pin | `/pin` | Pinned sessions |
| project_design | `/projects/design` | Project design |
| slide_design | `/slides/design` | Slide design |
| nano_banana | `/slides/nano-banana` | Nano banana slides |
| health | `/health` | Health check |

## Key Design Decisions

- **SQLAlchemy 2.0 async** — All database access uses `AsyncSession` with `mapped_column` style.
- **Dep aliases everywhere** — FastAPI dependency injection uses `Annotated[T, Depends(factory)]` pattern exclusively.
- **Redis optional** — All Redis usage has in-memory fallbacks for single-worker deployments.
- **Billing via reservations** — All billable work uses reserve -> settle -> release, never direct deductions.
- **GCS for storage** — File uploads, media, and slides use Google Cloud Storage with signed URLs.
- **E2B for sandboxes** — Code execution happens in isolated E2B sandbox environments.
