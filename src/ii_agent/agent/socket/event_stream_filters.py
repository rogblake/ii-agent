"""Event stream filters and wrappers for controlling event propagation."""

from typing import Any

from ii_agent.core.events.models import EventType, RealtimeEvent
from ii_agent.core.events.stream import EventStream


class SilentEventStream:
    """Event stream wrapper that filters out agent response events.

    Useful for internal operations where we don't want to expose the agent's
    thinking process or intermediate responses to the user. Only the final
    result should be sent via a custom event.

    Args:
        inner_stream: The underlying EventStream to wrap and filter
    """

    def __init__(self, inner_stream: EventStream) -> None:
        self.inner_stream = inner_stream

    async def publish(self, event: RealtimeEvent) -> None:
        """Publish event only if it's not an agent response.

        Args:
            event: The event to potentially publish
        """
        # Suppress AGENT_RESPONSE events to hide thinking process
        if event.type != EventType.AGENT_RESPONSE:
            await self.inner_stream.publish(event)

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to the inner stream.

        Args:
            name: The attribute name to retrieve

        Returns:
            The attribute from the inner stream
        """
        return getattr(self.inner_stream, name)
