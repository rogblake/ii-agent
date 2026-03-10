import logging

import socketio

from ii_agent.core.events.models import RealtimeEvent
from ii_agent.agent.subscribers.subscriber import EventSubscriber

logger = logging.getLogger(__name__)


class SocketIOSubscriber(EventSubscriber):
    """Subscriber that broadcasts events to a Socket.IO room."""

    def __init__(self, sio: socketio.AsyncServer):
        self.sio = sio

    async def handle_event(self, event: RealtimeEvent) -> None:
        """
        Handle a realtime event by broadcasting it to the Socket.IO room.

        Args:
            event: The realtime event to broadcast
        """
        if not await self.should_handle(event):
            return

        try:
            if event.session_id is None:
                logger.debug(
                    f"Event session_id is None, ignore broadcasting event: {event}"
                )
                return

            room = str(event.session_id)

            # Convert event to dict for JSON serialization
            # Include session_id in content for backward compatibility
            content_with_session = {
                **(event.content or {}),
                "session_id": str(event.session_id),
            }
            # Add run_id at top level for HITL continue_run
            event_data = {
                "type": event.type,
                "content": content_with_session,
                "session_id": str(event.session_id),
                "run_id": str(event.run_id) if event.run_id else None,
                "run_status": event.run_status,
            }

            # Broadcast to all clients in the room
            logger.debug(f"Broadcast event {event.content} to room {room}")
            room_size = self.sio.manager.get_participants("/", room)
            logger.debug(f"Room size: {len(list(room_size))}")
            await self.sio.emit("chat_event", event_data, room=room)

        except Exception as e:
            logger.error(f"Error broadcasting event to room {room}: {e}")
