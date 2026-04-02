"""Centralized constants shared across the A2A integration layer."""

# Extension URIs registered for ii-agent's A2A integration.
SESSION_CONTEXT_EXTENSION_URI = "https://ii-agent.dev/a2a/extensions/session-context"
SANDBOX_REUSE_EXTENSION_URI = "https://ii-agent.dev/a2a/extensions/sandbox-reuse"
USER_AUTH_HANDOFF_EXTENSION_URI = (
    "https://ii-agent.dev/a2a/extensions/user-auth-handoff"
)
RUNTIME_TRACE_EXTENSION_URI = "https://ii-agent.dev/a2a/extensions/runtime-trace"

SUPPORTED_EXTENSION_URIS = frozenset(
    {
        SESSION_CONTEXT_EXTENSION_URI,
        SANDBOX_REUSE_EXTENSION_URI,
        USER_AUTH_HANDOFF_EXTENSION_URI,
        RUNTIME_TRACE_EXTENSION_URI,
    }
)

# Runtime trace metadata constants.
RUNTIME_TRACE_ARTIFACT_NAMES = [
    "a2a-AGENT_THINKING",
    "a2a-TOOL_CALL",
    "a2a-TOOL_RESULT",
    "a2a-TOOL_CONFIRMATION",
    "a2a-AGENT_RESPONSE",
    "a2a-METRICS_UPDATE",
    "a2a-PROMPT_GENERATED",
    "a2a-USER_MESSAGE",
    "a2a-FILE_EDIT",
    "a2a-UPLOAD_SUCCESS",
    "a2a-BROWSER_USE",
]

RUNTIME_TRACE_EVENT_TYPES = [
    "AGENT_THINKING",
    "TOOL_CALL",
    "TOOL_RESULT",
    "TOOL_CONFIRMATION",
    "AGENT_RESPONSE",
    "METRICS_UPDATE",
    "PROMPT_GENERATED",
    "USER_MESSAGE",
    "FILE_EDIT",
    "UPLOAD_SUCCESS",
    "BROWSER_USE",
]

# Request metadata parsing keys.
METADATA_ROOT_KEYS = ("ii-agent", "ii_agent", "iiAgent")
TOOL_ARGS_KEYS = ("tool_args", "toolArgs", "tool-args")
SANDBOX_KEYS = ("sandbox", "sandbox_options", "sandboxOptions")
USER_KEYS = ("user", "user_info", "userInfo")

# Session registry defaults.
DEFAULT_SESSION_TTL_SECONDS = 60 * 60  # one hour default TTL
