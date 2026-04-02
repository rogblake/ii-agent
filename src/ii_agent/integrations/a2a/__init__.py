"""
A2A (Agent-to-Agent) Protocol Integration for II Agent.

This module provides A2A protocol support for the II Agent platform,
allowing other agents to interact with the system through standardized A2A interfaces.

Two primary adaptation layers are exposed:

- ``IIAgentA2AClient`` (ii-agent acting as an A2A client calling third-party agents)
- ``IIAgentA2AServer`` (ii-agent acting as an A2A server handling inbound requests)
"""

__version__ = "1.0.0"

from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
from ii_agent.integrations.a2a.as_server import IIAgentA2AServer
from ii_agent.integrations.a2a.event_stream_adapter import EventStreamAdapter

__all__ = [
    "IIAgentA2AClient",
    "IIAgentA2AServer",
    "EventStreamAdapter",
]
