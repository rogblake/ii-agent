from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Dict

import socketio

from ii_agent.auth.jwt_handler import jwt_handler
from ii_agent.billing.exceptions import InsufficientCreditsError
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.agent.events.models import EventType
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.socket.command.handler_factory import CommandHandlerFactory
from ii_agent.agent.socket.session_store import session_store

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class SocketIOManager:
    """Manages Socket.IO connections and their associated chat sessions.

    Session tracking uses Socket.IO's built-in per-connection session
    (sio.save_session / sio.get_session) instead of a custom dict.
    This is safe in distributed (multi-pod) deployments because WebSocket
    connections are sticky — all lifecycle events for a given socket ID
    are always handled by the same server instance.

    Cross-pod event broadcasting is handled by the AsyncRedisManager
    configured as the client_manager on the AsyncServer.
    """

    def __init__(self, sio: socketio.AsyncServer):
        self.sio = sio

    def set_container(self, container: ServiceContainer) -> None:
        """Set the service container. Must be called before init()."""
        self._container = container
        self.command_factory = CommandHandlerFactory(sio=self.sio, container=container)

    async def shutdown(self):
        await self.sio.shutdown()

    async def init(self):
        await self.command_factory.initialize()
        self.sio.event(self.connect)
        self.sio.event(self.disconnect)
        self.sio.on("join_session")(self.join_session)
        self.sio.on("chat_message")(self.chat_message)
        self.sio.on("leave_session")(self.leave_session)

    async def _emit_chat_event(self, room: str, event_type: str, content: Dict[str, Any]) -> None:
        """Helper method to emit chat events."""
        await self.sio.emit(
            "chat_event",
            {"type": event_type, "content": content},
            room=room,
        )

    async def _emit_error(self, room: str, message: str) -> None:
        """Helper method to emit error events."""
        await self._emit_chat_event(room, "error", {"message": message})

    async def _emit_system_event(self, room: str, message: str, **kwargs) -> None:
        """Helper method to emit system events."""
        await self._emit_chat_event(room, EventType.SYSTEM, {"message": message, **kwargs})

    def _is_session_owner(self, user_id: str, session: SessionInfo) -> bool:
        """Check if the authenticated user owns the session."""
        return str(session.user_id) == str(user_id)

    async def _leave_current_session(self, sid: str, session_id: str) -> None:
        """Leave a session room and remove from session store."""
        try:
            await self.sio.leave_room(sid, session_id)
        except Exception:
            # Room may already be cleaned up by the transport layer
            pass
        await session_store.remove_sid_from_session(session_id, sid)

    async def _require_session(self, data: Dict[str, Any]) -> SessionInfo | None:
        session_uuid_str = data.get("session_uuid")
        if not session_uuid_str:
            return None
        try:
            session_uuid = uuid.UUID(session_uuid_str)
            async with get_db_session_local() as db:
                session_info = await self._container.session_service.find_session_by_id_info(
                    db, session_uuid
                )
            return session_info
        except ValueError:
            return None

    async def chat_message(self, sid: str, data: Dict[str, Any]):
        """Handle incoming chat messages."""
        session_data = await self.sio.get_session(sid)
        user_id = session_data.get("user_id") if session_data else None

        session = await self._require_session(data)
        session_id = str(session.id) if session else None

        message_type = data.get("type")

        ctx = {
            "sio_event": "chat_message",
            "socket_id": sid,
            "message_type": message_type,
        }
        if user_id:
            ctx["user_id"] = user_id
        if session_id:
            ctx["session_id"] = session_id

        with logger.contextualize(**ctx):
            logger.info("Received chat message")

            if not session:
                logger.error("Chat session is required but empty")
                await self._emit_error(sid, "Chat Session is required!")
                return

            if not user_id or not self._is_session_owner(user_id, session):
                logger.warning("Access denied: user does not own session")
                await self._emit_error(sid, "Access denied")
                return

            content = data.get("content", {})

            try:
                logger.debug("Processing message")
                handler = self.command_factory.get_handler_by_string(message_type)

                if handler:
                    await handler.handle(content, session)
                else:
                    await self._emit_chat_event(
                        sid,
                        EventType.ERROR,
                        {"message": f"Unknown message type: {message_type}"},
                    )
            except InsufficientCreditsError:
                pass  # Already handled by command handlers via _send_error_event
            except Exception as e:
                logger.bind(error=str(e)).exception("Error handling chat message")
                await self._emit_error(sid, "Error processing message")

    async def connect(self, sid: str, environ: Dict, auth: Dict | None):
        """Handle Socket.IO client connection (authentication gate).

        Only validates the JWT and stores user identity in the per-connection
        session. The actual session binding happens in join_session.
        """
        with logger.contextualize(sio_event="connect", socket_id=sid):
            logger.info("Client connecting")

            if not auth or "token" not in auth:
                logger.warning("Connection rejected: No authentication token")
                return False

            auth_token = auth["token"]
            session_uuid_str = auth.get("session_uuid")

            try:
                payload = jwt_handler.verify_access_token(auth_token)
                if payload:
                    user_id = payload.get("user_id")
                    logger.bind(user_id=user_id).info("Authenticated")

                    await self.sio.save_session(
                        sid,
                        {
                            "user_id": user_id,
                            "session_uuid": session_uuid_str,
                            "authenticated": True,
                        },
                    )
                    return True
                else:
                    logger.warning("Connection rejected: Invalid or expired token")
                    return False
            except Exception as e:
                logger.bind(error=str(e)).exception("Connection rejected: Error verifying token")
                return False

    async def join_session(self, sid: str, data: Dict[str, Any]):
        """Join the session after connection is fully established."""
        session_data = await self.sio.get_session(sid)

        if not session_data or not session_data.get("authenticated"):
            with logger.contextualize(sio_event="join_session", socket_id=sid):
                logger.error("No valid session data found")
            await self.sio.disconnect(sid)
            return

        user_id = session_data.get("user_id")
        session_uuid_str = data.get("session_uuid") if data else None

        ctx = {"sio_event": "join_session", "socket_id": sid}
        if user_id:
            ctx["user_id"] = user_id
        if session_uuid_str:
            ctx["session_id"] = session_uuid_str

        with logger.contextualize(**ctx):
            # Validate session_uuid format before passing to service
            if session_uuid_str:
                try:
                    uuid.UUID(session_uuid_str)
                except ValueError:
                    logger.warning("Invalid session UUID format")
                    await self._emit_error(sid, "Invalid session UUID format")
                    return

            try:
                logger.info("Joining session")

                async with get_db_session_local() as db:
                    session_info = await self._container.session_service.get_or_create_session(
                        db, session_uuid=session_uuid_str, user_id=user_id, api_version="v1"
                    )

                if not self._is_session_owner(user_id, session_info):
                    logger.warning("Access denied: user does not own session")
                    await self._emit_error(sid, "Access denied")
                    return

                await self._emit_system_event(
                    sid, "Session created", session_id=str(session_info.id)
                )

                session_id_str = str(session_info.id)

                # Leave any previous session for this sid (handles re-join)
                old_session_id = session_data.get("session_id")
                if old_session_id and old_session_id != session_id_str:
                    await self._leave_current_session(sid, old_session_id)
                    logger.debug("Left previous session")

                # Join the new session room
                logger.info("Chat session created, joining room")
                await self.sio.enter_room(sid, session_id_str)
                await session_store.add_sid_to_session(session_id_str, sid)

                # Persist the joined session_id in the sio session
                session_data["session_id"] = session_id_str
                await self.sio.save_session(sid, session_data)

            except Exception as e:
                logger.bind(error=str(e)).exception("Error initializing session")
                await self._emit_error(sid, "Session initialization failed")
                await self.sio.disconnect(sid)

    async def leave_session(self, sid: str, data: Dict[str, Any]):
        """Handle leave_session event — client voluntarily leaving a session."""
        session_data = await self.sio.get_session(sid)
        session_id = session_data.get("session_id") if session_data else None

        ctx = {"sio_event": "leave_session", "socket_id": sid}
        if session_id:
            ctx["session_id"] = session_id

        with logger.contextualize(**ctx):
            logger.info("Client leaving session")

            if session_id:
                await self._leave_current_session(sid, session_id)

    async def disconnect(self, sid: str):
        """Handle Socket.IO disconnection and cleanup.

        Fires AFTER the client has already disconnected.
        Socket.IO auto-removes sid from all rooms — only our Redis store needs cleanup.
        No need to clear session_data — Socket.IO discards it with the connection.
        """
        session_data = await self.sio.get_session(sid)
        session_id = session_data.get("session_id") if session_data else None

        ctx = {"sio_event": "disconnect", "socket_id": sid}
        if session_id:
            ctx["session_id"] = session_id

        with logger.contextualize(**ctx):
            logger.info("Client disconnected")

            if session_id:
                await self._leave_current_session(sid, session_id)
