<!-- Generated: 2026-03-29 | Tables: 38 | Token estimate: ~800 -->
# Data

## Database: PostgreSQL + SQLAlchemy 2.0

Base: `core/db/base.py::Base` — provides `id: uuid.UUID`, `created_at`, `updated_at`
Timestamps: `TimestampColumn = DateTime(timezone=True)`
Engine: `core/db/base.py::get_engine()` (lazy singleton with asyncpg)
Session dep: `core/db/deps.py::get_db` → `DBSession`

## ID Convention

All entity PKs: `Mapped[uuid.UUID]` with `UUID(as_uuid=True)`, `server_default=gen_random_uuid()`
All FK columns: `Mapped[uuid.UUID]` with `UUID(as_uuid=True)`
Exception: `TaskLog.id` = `BigInteger` autoincrement, `AgentRunMessage.id` = `BigInteger`

## Tables by Domain

### User & Auth
| Table | Model | PK | File |
|-------|-------|----|------|
| `users` | User | UUID (from Base) | `users/models.py` |
| `api_keys` | APIKey | UUID (from Base) | `users/models.py` |

### Sessions & Chat
| Table | Model | PK | File |
|-------|-------|----|------|
| `sessions` | Session | UUID | `sessions/models.py` |
| `session_pins` | SessionPin | UUID (from Base) | `sessions/pin/models.py` |
| `session_wishlists` | SessionWishlist | UUID (from Base) | `sessions/wishlist/models.py` |
| `chat_messages` | ChatMessage | UUID | `chat/messages/models.py` |
| `chat_summaries` | ChatSummary | UUID (from Base) | `chat/messages/models.py` |
| `chat_runs` | ChatRun | UUID | `chat/runs/models.py` |
| `chat_provider_containers` | ChatProviderContainer | UUID | `chat/providers/models.py` |
| `chat_provider_files` | ChatProviderFile | UUID | `chat/providers/models.py` |
| `chat_provider_vector_stores` | ChatProviderVectorStore | UUID | `chat/providers/models.py` |

### Tasks (Canonical Domain)
| Table | Model | PK | File |
|-------|-------|----|------|
| `run_tasks` | RunTask | UUID | `tasks/models.py` |
| `task_logs` | TaskLog | **BigInteger** | `tasks/models.py` |

### Settings
| Table | Model | PK | File |
|-------|-------|----|------|
| `llm_settings` | LLMSetting | UUID (from Base) | `settings/llm/models.py` |
| `mcp_settings` | MCPSetting | UUID (from Base) | `settings/mcp/models.py` |
| `skills` | Skill | UUID (from Base) | `settings/skills/models.py` |

### Agent Execution
| Table | Model | PK | File |
|-------|-------|----|------|
| `agent_run_tasks` | AgentRunTask | UUID | `agents/runs/models.py` |
| `agent_run_messages` | AgentRunMessage | **BigInteger** | `agents/runs/models.py` |

### Billing & Credits
| Table | Model | PK | File |
|-------|-------|----|------|
| `billing_transactions` | BillingTransaction | UUID (from Base) | `billing/models.py` |
| `credit_balances` | CreditBalance | UUID (from Base) | `credits/models.py` |
| `credit_transactions` | CreditTransaction | UUID (from Base) | `credits/models.py` |

### Files & Assets
| Table | Model | PK | File |
|-------|-------|----|------|
| `user_assets` | FileAsset | UUID (from Base) | `files/models.py` |
| `session_assets` | SessionAsset | UUID (from Base) | `files/models.py` |

### Projects & Deployments
| Table | Model | PK | File |
|-------|-------|----|------|
| `projects` | Project | UUID (from Base) | `projects/models.py` |
| `project_deployments` | ProjectDeployment | UUID (from Base) | `projects/deployments/models.py` |
| `project_databases` | ProjectDatabase | UUID (from Base) | `projects/databases/models.py` |
| `project_custom_domains` | ProjectCustomDomain | UUID (from Base) | `projects/subdomains/models.py` |

### Content
| Table | Model | PK | File |
|-------|-------|----|------|
| `slide_contents` | SlideContent | UUID (from Base) | `content/slides/models.py` |
| `slide_versions` | SlideVersion | UUID (from Base) | `content/slides/models.py` |
| `slide_templates` | SlideTemplate | UUID (from Base) | `content/slides/models.py` |
| `media_templates` | MediaTemplate | UUID (from Base) | `content/media/models.py` |
| `storybooks` | Storybook | UUID (from Base) | `content/storybook/models.py` |
| `storybook_pages` | StorybookPage | UUID (from Base) | `content/storybook/models.py` |
| `storybook_page_links` | StorybookPageLink | composite | `content/storybook/models.py` |

### Integrations
| Table | Model | PK | File |
|-------|-------|----|------|
| `connectors` | Connector | UUID (from Base) | `integrations/connectors/models.py` |
| `composio_profiles` | ComposioProfile | UUID (from Base) | `integrations/connectors/models.py` |
| `apple_credentials` | AppleCredential | UUID (from Base) | `integrations/mobile/apple/models.py` |

### Events
| Table | Model | PK | File |
|-------|-------|----|------|
| `application_events` | ApplicationEventModel | UUID (from Base) | `realtime/events/models.py` |

## Key Relationships

```
User 1──N Session 1──N ChatMessage
User 1──N APIKey
User 1──N CreditBalance (1 per user)
User 1──N CreditTransaction
User 1──N BillingTransaction
User 1──N FileAsset
Session 1──N SessionAsset
Session 1──N RunTask
Session 1──N ChatRun 1──N AgentRunTask
Session 1──N SessionPin
Session 1──N SessionWishlist
Session 1──N ApplicationEventModel
Project 1──N ProjectDeployment
Project 1──N ProjectDatabase
Project 1──N ProjectCustomDomain
Storybook 1──N StorybookPage 1──N StorybookPageLink
SlideContent 1──N SlideVersion
RunTask 1──N TaskLog
```

## Migrations

Alembic managed. Run at startup unless `II_AGENT_SKIP_MIGRATIONS=true`.
Config: `alembic/` directory at project root.
