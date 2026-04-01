"""Chat session context — lightweight container for agent session state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatSessionContext:
    """Holds the runtime context for a chat session (agent + sandbox + config)."""

    workspace_manager: Any
    file_store: Any
    config: Any
    llm_config: Any
    session_info: Any
    agent_controller: Any
    sandbox: Any
    event_stream: Any
