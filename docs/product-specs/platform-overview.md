# Platform Overview

## What II-Agent Is

II-Agent is an AI agent platform that autonomously executes complex tasks — building web applications, creating presentations, and conducting deep research. Users describe intent; the agent executes across real tools, sandboxes, and deployments.

**Live at:** [agent.ii.inc](https://agent.ii.inc/)

## Product Pillars

### Full-Stack Development
Users describe a web application. The agent scaffolds code in an E2B sandbox, iterates on user feedback, provisions databases, manages secrets, deploys to Google Cloud Run, and assigns custom subdomains.

### Slide & Storybook Creation
Users provide a brief. The agent generates HTML slides with design templates, handles image generation, supports version chains for iterative editing, and exports to PDF.

### Deep Research
Integration with II-Researcher. The agent searches the web, analyzes sources, and produces structured reports. Research sessions can be forked into website projects via `ForkType.RESEARCH_TO_WEBSITE`.

## Interaction Modes

### Agent Mode (`app_kind="agent"`)
- **Transport:** Socket.IO (real-time bidirectional streaming)
- **Capabilities:** Multi-step execution, tool use, sandbox, deployment, planning
- **Billing:** Per-call inside the agent loop (reserve before each LLM call)
- **Commands:** QUERY (run task), PLAN (generate/modify plan), CANCEL (stop execution)

### Chat Mode (`app_kind="chat"`)
- **Transport:** REST + Server-Sent Events
- **Capabilities:** Single-turn conversations, multi-model switching within a thread
- **Billing:** Per-call via LLMExecutionService
- **Providers:** Anthropic (Claude), OpenAI (GPT-4o, o1, o3), Google (Gemini)

## Key Entities

| Entity | Description |
|--------|-------------|
| **User** | Authenticated via OAuth (II/Google) or API key. Has credit balance. |
| **Session** | A conversation/task context. Either agent or chat type. Soft-deletable, forkable. |
| **AgentRunTask** | A single agent execution within a session. Tracks status, events, billing. |
| **ChatRun** | A single chat turn within a session. Tracks model, tokens, status. |
| **Project** | A deployable web application tied to a session. Has deployments, secrets, subdomain. |
| **CreditBalance** | One row per user. Regular + bonus credits. Locked for mutations. |
| **CreditReservation** | A billing hold. Reserve → Settle → Release lifecycle. |

## User Journey: Agent Development Session

1. User logs in via OAuth
2. User sends a message describing what to build
3. System creates a Session + AgentRunTask
4. Agent validates billing status (BillingStatus == OK)
5. Agent reserves credits for first LLM call
6. Agent streams: THINKING → TOOL_CALL → TOOL_RESULT → RESPONSE
7. Agent may create E2B sandbox, write files, run code
8. Each LLM call and tool use is independently billed (reserve → settle)
9. User iterates with follow-up messages
10. User triggers deployment → Cloud Run + subdomain
11. User can publish session as public (shareable URL)

## User Journey: Chat Session

1. User sends a message with a model selection
2. System creates Session (app_kind="chat") + ChatRun
3. LLMExecutionService reserves credits, calls provider
4. Response streamed via SSE
5. User can switch models mid-conversation
6. User can use tools (code interpreter) if enabled
