"""Registry for command handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict

import socketio

from ii_agent.realtime.events.stream import AsyncEventStream
from ii_agent.realtime.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.realtime.socket.command.query_handler import UserQueryHandler
from ii_agent.realtime.socket.command.plan_handler import PlanHandler
from ii_agent.realtime.socket.command.publish_handler import PublishProjectHandler
from ii_agent.realtime.socket.command.cloud_run_publish_handler import (
    CloudRunPublishHandler,
)
from ii_agent.realtime.socket.command.sandbox_status_handler import (
    SandboxStatusHandler,
)
from ii_agent.realtime.socket.command.awake_sandbox_handler import AwakeSandboxHandler
from ii_agent.realtime.socket.command.workspace_info_handler import (
    WorkspaceInfoHandler,
)
from ii_agent.realtime.socket.command.ping_handler import PingHandler
from ii_agent.realtime.socket.command.cancel_handler import CancelHandler
from ii_agent.realtime.socket.command.continue_run_handler import ContinueRunHandler
from ii_agent.realtime.socket.command.enhance_prompt_handler import (
    EnhancePromptHandler,
)
from ii_agent.realtime.socket.command.start_fork_handler import StartForkHandler
from ii_agent.realtime.socket.command.submit_testflight_handler import (
    SubmitTestflightHandler,
)
from ii_agent.realtime.socket.command.apple_auth_handler import (
    AppleAuthLoginHandler,
    AppleAuth2FAHandler,
    AppleAuthSelectTeamHandler,
    AppleCheckAuthHandler,
    SaveExpoTokenHandler,
)
from ii_agent.realtime.socket.command.apple_app_setup_handler import (
    AppleAppSetupHandler,
    AppleListAppsHandler,
)
from ii_agent.realtime.subscribers.database_subscriber import DatabaseSubscriber
from ii_agent.realtime.subscribers.metrics_subscriber import MetricsSubscriber
from ii_agent.realtime.subscribers.socketio_subscriber import SocketIOSubscriber

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class CommandHandlerFactory:
    """Registry for managing command handlers."""

    def __init__(
        self,
        sio: socketio.AsyncServer,
        container: ServiceContainer,
    ) -> None:
        self._sio = sio
        self._container = container
        self._handlers: Dict[UserCommandType, CommandHandler] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize handlers asynchronously. Must be called before using the factory."""
        if not self._initialized:
            await self._initialize_handlers()
            self._initialized = True

    async def _initialize_handlers(self) -> None:
        """Initialize all command handlers with their dependencies."""
        event_stream = AsyncEventStream()

        await event_stream.subscribe(SocketIOSubscriber(self._sio))
        await event_stream.subscribe(DatabaseSubscriber(self._container))
        await event_stream.subscribe(MetricsSubscriber())

        # Create query handler first as it's used by other handlers
        query_handler = UserQueryHandler(
            event_stream=event_stream, container=self._container
        )

        self._handlers = {
            UserCommandType.QUERY: query_handler,
            UserCommandType.PLAN: PlanHandler(
                event_stream=event_stream, container=self._container
            ),
            UserCommandType.SANDBOX_STATUS: SandboxStatusHandler(
                event_stream=event_stream, container=self._container
            ),
            UserCommandType.AWAKE_SANDBOX: AwakeSandboxHandler(
                event_stream=event_stream, container=self._container
            ),
            UserCommandType.WORKSPACE_INFO: WorkspaceInfoHandler(
                event_stream=event_stream, container=self._container
            ),
            UserCommandType.PING: PingHandler(
                event_stream=event_stream, container=self._container
            ),
            UserCommandType.CANCEL: CancelHandler(
                event_stream=event_stream, container=self._container
            ),
            UserCommandType.CONTINUE_RUN: ContinueRunHandler(
                event_stream=event_stream, container=self._container
            ),
            UserCommandType.ENHANCE_PROMPT: EnhancePromptHandler(
                event_stream=event_stream, container=self._container
            ),
            UserCommandType.PUBLISH_PROJECT: PublishProjectHandler(
                event_stream=event_stream, container=self._container
            ),
            UserCommandType.PUBLISH_CLOUD_RUN: CloudRunPublishHandler(
                event_stream=event_stream, container=self._container
            ),
            UserCommandType.START_FORK: StartForkHandler(
                event_stream=event_stream,
                container=self._container,
                query_handler=query_handler,
            ),
            UserCommandType.SUBMIT_TESTFLIGHT: SubmitTestflightHandler(
                event_stream=event_stream,
                container=self._container,
            ),
            UserCommandType.APPLE_AUTH_LOGIN: AppleAuthLoginHandler(
                event_stream=event_stream,
                container=self._container,
            ),
            UserCommandType.APPLE_AUTH_2FA: AppleAuth2FAHandler(
                event_stream=event_stream,
                container=self._container,
            ),
            UserCommandType.APPLE_AUTH_SELECT_TEAM: AppleAuthSelectTeamHandler(
                event_stream=event_stream,
                container=self._container,
            ),
            UserCommandType.APPLE_APP_SETUP: AppleAppSetupHandler(
                event_stream=event_stream,
                container=self._container,
            ),
            UserCommandType.APPLE_LIST_APPS: AppleListAppsHandler(
                event_stream=event_stream,
                container=self._container,
            ),
            UserCommandType.APPLE_CHECK_AUTH: AppleCheckAuthHandler(
                event_stream=event_stream,
                container=self._container,
            ),
            UserCommandType.SAVE_EXPO_TOKEN: SaveExpoTokenHandler(
                event_stream=event_stream,
                container=self._container,
            ),
        }

    def get_handler(self, command_type: UserCommandType) -> CommandHandler | None:
        """Get handler for a specific command type."""
        return self._handlers.get(command_type)

    def get_handler_by_string(self, command_type_str: str) -> CommandHandler | None:
        """Get handler by command type string."""
        try:
            command_type = UserCommandType(command_type_str)
            return self.get_handler(command_type)
        except ValueError:
            return None
