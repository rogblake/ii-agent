"""Subscriber that tracks LLM metrics per session."""

import logging

from ii_agent.core.events.models import RealtimeEvent, EventType
from ii_agent.agent.subscribers.subscriber import EventSubscriber

logger = logging.getLogger(__name__)


class MetricsSubscriber(EventSubscriber):
    """Subscriber that handles metrics updates for sessions.

    Billing is now handled directly in the socket command handlers
    via ``LLMBillingService``.  This subscriber only logs events
    and forwards non-billing data (tool results, etc.).
    """

    async def handle_event(self, event: RealtimeEvent) -> None:
        """Handle an event, specifically looking for METRICS_UPDATE and TOOL_RESULT events."""
        if event.session_id is None:
            return

        if not await self.should_handle(event):
            return

        try:
            if event.type == EventType.METRICS_UPDATE:
                logger.debug(
                    "METRICS_UPDATE for session %s (billing handled in handler)",
                    event.session_id,
                )
            elif event.type == EventType.TOOL_RESULT:
                await self._handle_tool_result(event)

        except Exception as e:
            logger.error(f"Error processing event {event.type}: {e}", exc_info=True)

    async def _handle_tool_result(self, event: RealtimeEvent) -> None:
        """Handle TOOL_RESULT events for tool usage tracking."""
        pass
