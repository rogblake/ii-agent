# Frontend Integration

## Two Runtime Paths

II-Agent has two distinct client-facing runtime paths:

### 1. Agent Runtime (WebSocket / Socket.IO)

Used for agent sessions (`app_kind="agent"`). The agent executes multi-step tasks with tool use, streaming events in real-time.

**Connection:** Socket.IO via `app.py` with optional Redis session manager for multi-worker.

**Command Types:**

| Command | Handler | What it does |
|---------|---------|-------------|
| QUERY | `agent/socket/command/query_handler.py` | Execute agent task — validates session, creates AgentRunTask, runs agent with streaming |
| PLAN | `agent/socket/command/plan_handler.py` | Generate/modify execution plans — routes by `build_mode` (plan, modify_plan, modify_plan_suggestions) |
| CANCEL | `agent/socket/command/cancel_handler.py` | Cancel running agent — marks ABORTING, signals via Redis cancellation |

**Event Types** (streamed to client via `agent/events/models.py`):

| Event | Description |
|-------|-------------|
| `CONNECTION_ESTABLISHED` | Socket connected |
| `STATUS_UPDATE` | Run status change |
| `AGENT_THINKING_START/DELTA` | LLM reasoning in progress |
| `TOOL_CALL` | Agent invoking a tool |
| `TOOL_RESULT` | Tool execution result |
| `AGENT_RESPONSE/DELTA` | Agent text output (streaming) |
| `STREAM_COMPLETE` | Agent run finished |
| `ERROR` | Error occurred |
| `PLAN_GENERATED` | Execution plan created |
| `MILESTONE_UPDATE` | Plan milestone status change |
| `METRICS_UPDATE` | Token usage metrics |
| `FILE_EDIT` | File modification in sandbox |
| `BROWSER_USE` | Browser automation event |
| `SANDBOX_STATUS` | Sandbox state change |
| `TOOL_CONFIRMATION` | Tool requires user approval |
| `WAITING_FOR_USER_INPUT` | Agent paused for input |

**Event Schema** (`RealtimeEvent`):
```
id: UUID
type: EventType
session_id: UUID | null
run_id: UUID | null
run_status: str | null
content: dict
timestamp: float
```

**Persistence:** Events saved to `agent_ui_events` table by `DatabaseSubscriber`. Transient events (deltas, streaming) are skipped.

### 2. Chat Runtime (REST / SSE)

Used for chat sessions (`app_kind="chat"`). Single LLM calls with optional tool use, streamed via Server-Sent Events.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/conversations` | Send message — creates session if needed, streams SSE response |
| GET | `/v1/chat/conversations/{id}/advanced-mode` | Get advanced mode state |
| POST | `/v1/chat/conversations/{id}/advanced-mode` | Toggle advanced mode |

**Chat Message Content Parts:**
- `TextContent` — Plain text
- `ReasoningContent` — Model reasoning/thinking
- `ToolCall` — Tool invocation (id, name, input)
- `ToolResult` — Tool output
- `BinaryContent` — Base64 media (images)
- `JsonResultContent` — Structured JSON output

## REST API Surface

### Authentication
| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/oauth/ii/login` | II OAuth redirect |
| GET | `/auth/oauth/ii/callback` | II OAuth callback |
| GET | `/auth/oauth/google/login` | Google OAuth redirect |
| GET | `/auth/oauth/google/callback` | Google OAuth callback |
| GET | `/auth/me` | Current user profile (UserPublic) |
| PATCH | `/auth/me/language` | Update language (en, vi, hi, ja) |
| DELETE | `/auth/me` | Soft-delete account |

### Sessions
| Method | Path | Description |
|--------|------|-------------|
| GET | `/sessions` | List sessions (paginated, filterable by query/type/public) |
| GET | `/sessions/{id}` | Session details |
| GET | `/sessions/{id}/events` | Session events with run_status |
| GET | `/sessions/{id}/files` | Session files |
| POST | `/sessions/{id}/publish` | Make session public |
| POST | `/sessions/{id}/unpublish` | Make session private |
| POST | `/sessions/bulk-delete` | Bulk soft-delete (max 50) |

### Files
| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat/generate-upload-url` | Signed upload URL |
| POST | `/chat/upload-complete` | Complete upload, get download URL |
| GET | `/chat/files/{id}` | Download file (streaming) |
| GET | `/public/chat/{session_id}/files/{id}` | Public file download |
| POST | `/chat/files/download-urls` | Batch download URLs |
| GET | `/chat/user-media-library` | Image library (paginated) |
| POST | `/avatar` | Upload avatar |
| GET | `/avatar` | Get avatar URL |

### Billing
| Method | Path | Description |
|--------|------|-------------|
| GET | `/credits` | Credit balance |
| GET | `/billing` | Billing info / Stripe portal |

### Settings
| Method | Path | Description |
|--------|------|-------------|
| GET/POST/PUT/DELETE | `/user-settings/models` | LLM model preferences |
| GET/POST | `/user-settings/mcp` | MCP server configuration |
| GET/POST | `/user-settings/mcp/codex` | Codex MCP settings |
| GET/POST | `/user-settings/mcp/claude-code` | Claude Code MCP settings |
| GET/POST | `/user-settings/skills` | Custom skills |

### Projects
| Method | Path | Description |
|--------|------|-------------|
| GET | `/project/{session_id}` | Project details |
| POST | `/project/secrets` | Update project secrets |
| POST | `/subdomains` | Claim subdomain |

### Content
| Method | Path | Description |
|--------|------|-------------|
| Various | `/slides/*` | Slide generation and management |
| Various | `/slide-templates/*` | Slide templates |
| Various | `/storybooks/*` | Storybook generation |
| Various | `/media/*` | Media generation |
| Various | `/media-templates/*` | Media templates |
| Various | `/connectors/*` | External connectors |

### Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
