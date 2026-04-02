# A2A Metadata and Context Conventions

This document describes how ii-agent interprets context, tool configuration, and sandbox reuse directives in A2A protocol requests. Unless noted otherwise, examples use Simplified Chinese in the original reference but are expressed here in English.

## Architecture Roles

- **IIAgentA2AClient** (`ii_agent.a2a.as_client`): wraps the A2A SDK so ii-agent can call downstream/third-party A2A agents while negotiating extensions.
- **IIAgentA2AServer** (`ii_agent.a2a.as_server`): adapts inbound A2A requests so other agents can invoke ii-agent; it powers the `IIAgentExecutor`.

Both layers share the conventions described below, ensuring metadata/extension handling stays consistent regardless of call direction.

## Top-Level Structure

When the A2A SDK sends a request it includes `MessageSendParams`. ii-agent inspects dictionaries found in `metadata`, `message.metadata`, `message.parts[].metadata`, and `message.content`. We recommend placing the following structure at any level:

```json
{
  "ii-agent": {
    "tool_args": { ... },
    "sandbox": { ... },
    "user": { ... }
  }
}
```

> Tip: The key can also be `ii_agent` or `iiAgent`; the parser normalizes these variants automatically.

## Tool Configuration `tool_args`

Use this field to enable or customize ii-agent's toolchain. Example:

```json
"tool_args": {
  "browser": true,
  "deep_research": true
}
```

A2A agents are configured via environment variable:

```bash
export A2A_THIRD_PARTY_AGENTS='{"pubmed": {"url": "https://commons-dev.ii.inc/a2a/pubmed", "description": "PubMed biomedical literature search"}}'
```

Notes:

- Boolean flags (such as `browser`, `deep_research`) map directly to toggles in `AgentService.create_agent`.
- A2A agents are now configured via the `A2A_THIRD_PARTY_AGENTS` environment variable instead of tool_args.
- All key-value pairs are deep-merged with historical configuration. In multi-turn sessions later entries override earlier ones.

## Sandbox Policy `sandbox`

Controls how an A2A request interacts with the II Sandbox:

| Field          | Type     | Description |
|----------------|----------|-------------|
| `reuse`        | bool/str | Whether to reuse the sandbox for the same `context_id`; defaults to `false` |
| `timeout`      | int/str  | Seconds before the sandbox is destroyed when idle; defaults to 15 minutes if omitted |
| `template_id`  | str      | Template ID used when creating a sandbox; overrides the system default |
| `sandbox_id`   | str      | Force binding to a specific sandbox, often combined with `reuse` |
| Other keys     | any      | Preserved in `extra` for future extensions |

Example:

```json
"sandbox": {
  "reuse": true,
  "timeout": 1800,
  "templateId": "code-template"
}
```

> Note: If reusing a specific `sandbox_id` fails, the system automatically provisions a new sandbox and records the latest ID.

## User Credentials `user`

Attach external credentials (such as sandbox API keys) with this section:

| Field    | Description |
|----------|-------------|
| `apiKey` | API key required by the sandbox or tool |
| `id`     | User ID associated with the credential |
| Other keys | Preserved in `extra` for extensible authentication data |

If `apiKey` is missing, the system falls back to the configured `A2A_SANDBOX_API_KEY`.

## Request Example

```json
{
  "ii-agent": {
    "toolArgs": {
      "browser": false,
      "deep_research": true
    },
    "sandbox": {
      "reuse": true,
      "timeout": 1200
    },
    "user": {
      "id": "a2a-service-user",
      "apiKey": "****"
    }
  }
}
```

## Parsing Priority

The parser inspects metadata in the following order, with later entries overriding earlier fields:

1. `RequestContext.metadata`
2. `Message.metadata`
3. `Message.parts[].metadata`
4. `Message.content` (if it is a dictionary)

## Frequently Asked Questions

- **Does metadata omission cause errors?** No. The parser returns an empty configuration and falls back to defaults.
- **How is multi-turn reuse handled?** If `reuse` is `true` and `context_id` matches, ii-agent attempts to reuse the sandbox and `tool_args`. On failure it provisions a new sandbox and updates the cache.
- **How do I debug?** When requests are processed, server logs show the resolved `payload.tool_args`, `sandbox`, and related fields.

## Status and Error Reporting

Starting in October 2025 the ii-agent A2A service emits standardized `TaskStatusUpdateEvent` metadata so downstream agents can track progress and failures:

- **Processing start**: Immediately after receiving a request, the service emits a status event with `state=working` and `metadata.code="processing"` so callers can record acceptance time.
- **In-flight updates**: Internal streaming events include `metadata.code` values (such as `working` or `input_required`) and retain the original `metadata` dictionary, making it easier to display progress consistently.
- **Successful completion**: Upon completion the service first sends `state=completed`, `metadata.code="completed"`, and includes `metadata.result` with a summary. A traditional `message` event is still emitted for backward compatibility.
- **Failure alerts**: When an error occurs the service emits `state=failed`, `metadata.code="agent_error"`; `metadata.detail` carries the raw error description, and `status.message` mirrors the text so downstream agents can relay it.

Success example:

```jsonc
{
  "kind": "status-update",
  "contextId": "ctx-123",
  "taskId": "task-123",
  "final": true,
  "metadata": {
    "code": "completed",
    "progress": 100,
    "result": {
      "task_id": "task-123",
      "output": "Code refactoring finished"
    }
  },
  "status": {
    "state": "completed",
    "message": {
      "role": "agent",
      "parts": [
        {
          "kind": "text",
          "text": "Code refactoring finished"
        }
      ]
    }
  }
}
```

Failure example:

```jsonc
{
  "kind": "status-update",
  "contextId": "ctx-123",
  "taskId": "task-123",
  "final": true,
  "metadata": {
    "code": "agent_error",
    "detail": "Sandbox connection timeout",
    "origin": "ii-agent"
  },
  "status": {
    "state": "failed",
    "message": {
      "role": "agent",
      "parts": [
        {
          "kind": "text",
          "text": "Sandbox connection timeout"
        }
      ]
    }
  }
}
```

> Tip: Each status event is followed by a traditional `message` event for backward compatibility. If you only care about the standardized A2A flow, handle `TaskStatusUpdateEvent` exclusively.

## Streaming Output

- **Enablement**: Set `{"streaming": true}` in the request `context` (default). If the caller explicitly sends `false`, the service runs in blocking mode.
- **Event mapping**: When the downstream agent supports streaming, ii-agent maps real-time events to native `EventType` values, for example:
  - `working` → `EventType.PROCESSING` plus `TaskStatusUpdateEvent(final=false)`
  - Incremental text (thoughts or partial chunks) → `EventType.AGENT_RESPONSE` with `{"text": "..."}`
  - Completion/failure → `EventType.COMPLETE` / `EventType.ERROR`, with `final=true` only on the terminal event
- **Fallback strategy**: If the streaming pipeline fails (e.g., SSE disconnects), ii-agent automatically falls back to blocking invocation, logs the reason, and still sends the final event.
- **Session context**: Streaming sessions reuse `context_id`, `task_id`, and `tool_args`. To replay externally, reuse the same `context_id` and keep `context.streaming=true`.
- **Upstream/downstream compatibility**:
  - If the caller uses `message/stream`, it receives real-time status and artifact events. Ignoring streaming events still yields the final response without errors.
  - If the downstream A2A agent lacks streaming support, ii-agent automatically switches to blocking mode transparently. Likewise, callers can disable streaming explicitly via `context.streaming=false`.

## Third-Party Agent Configuration and Hot Reloads

- **Configuration source**: `A2A_THIRD_PARTY_AGENTS` environment variable accepts a JSON string describing multiple external agents. The service loads it at startup and validates URLs and descriptions.
- **Runtime reload**: Restart the service or use the application's built-in reload mechanism to pick up configuration changes from the environment variable.
- **Configuration validation**: The service validates agent configurations at startup, rejecting invalid input such as missing URLs or malformed JSON with clear error messages.

### Extension Negotiation and Graceful Degradation

- **Requesting extensions**: Add `"requested_extensions": ["a2a-ext-commonground-v1"]` in `tool_args` or tool-call `context`, and the A2A integration will negotiate automatically against the target AgentCard.
- **Negotiation result**: The invocation appends an `"a2a_negotiation"` object containing `requested_extensions`, `active_extensions`, and `missing_extensions` for downstream handling.
- **Enhanced mode**: When the counterpart AgentCard advertises the requested extensions, ii-agent preserves the original context so both sides can exchange data under the extended protocol (e.g., sharing `team_state_handle`).
- **Graceful fallback**: If the extension is unsupported, ii-agent generates a fallback briefing (or a serialized payload) and attaches it to the query text while storing `fallback_payload` in the context. Standard A2A flow continues with the essential background.
- **Usage guidance**: Downstream agents should check `a2a_negotiation.active_extensions` first. If empty, consult `fallback_payload` or parse the message text directly.

## Authentication for Inbound Requests

- **API key support**: Since October 2025 the A2A service accepts `Authorization: Bearer <token>` or `X-A2A-API-Key`. Configure the key list via the `A2A_ALLOWED_API_KEYS` environment variable using comma-separated values.
- **Behavior when unset**: If `A2A_ALLOWED_API_KEYS` is empty, the service skips authentication and logs a warning—useful for development environments.
- **Caller requirements**: Requests without a valid key receive `401 Unauthorized` with `{"error": "Unauthorized"}` for programmatic handling.
- **Best practices**: Assign dedicated keys per consumer to simplify auditing and rate control.

Feel free to extend the `ii-agent` section with additional fields. The parser preserves unknown keys inside `extra`, ensuring no information is lost.
