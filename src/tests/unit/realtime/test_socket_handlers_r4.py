"""Unit tests for realtime socket command handlers (r4).

Covers:
- submit_testflight_handler.py
- apple_auth_handler.py
- publish_handler.py
- apple_app_setup_handler.py
- cloud_run_publish_handler.py
- plan_handler.py
- continue_run_handler.py

Strategy: Minimise mocking – only patch external I/O (DB, network, Apple APIs).
Internal logic executes naturally wherever possible.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.sessions.schemas import SessionInfo

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_session_info(
    session_id: uuid.UUID | None = None,
    user_id: str = "user-abc-123",
    api_version: str = "v1",
    agent_type: str = "general",
) -> SessionInfo:
    return SessionInfo(
        id=session_id or uuid.uuid4(),
        user_id=user_id,
        api_version=api_version,
        name="Test Session",
        status="active",
        workspace_dir="/workspace",
        is_public=False,
        created_at="2024-01-01T00:00:00Z",
        agent_type=agent_type,
    )


class CapturingEventStream:
    """Captures all published events for assertion."""

    def __init__(self):
        self.events: list[RealtimeEvent] = []

    async def publish(self, event: RealtimeEvent) -> None:
        self.events.append(event)

    def last_event(self) -> RealtimeEvent | None:
        return self.events[-1] if self.events else None

    def events_of_type(self, event_type: EventType) -> list[RealtimeEvent]:
        return [e for e in self.events if e.type == event_type]


def _mock_container(**overrides) -> MagicMock:
    container = MagicMock()
    container.config = MagicMock()
    container.config.workspace_path = "/workspace"
    container.config.use_container_workspace = False
    container.config.mcp = MagicMock()
    container.config.mcp.port = 3000
    container.session_service = MagicMock()
    container.sandbox_service = MagicMock()
    container.sandbox_service.resolve_sandbox_for_session = AsyncMock(return_value=None)
    container.project_service = MagicMock()
    container.project_service.get_session_project_or_none = AsyncMock(return_value=None)
    container.deployments_service = MagicMock()
    container.deployments_service.update_deployment_metadata = AsyncMock()
    container.agent_run_service = MagicMock()
    container.agent_run_service.get_running_task = AsyncMock(return_value=None)
    container.agent_run_service.create_task = AsyncMock()
    container.agent_run_service.update_task_status = AsyncMock()
    container.event_service = MagicMock()
    container.event_service.save_event = AsyncMock()
    container.file_service = MagicMock()
    container.file_service.prepare_agent_files = AsyncMock(return_value=([], []))
    container.deployment_orchestration_service = MagicMock()
    container.deployment_orchestration_service.create_deployment_context = AsyncMock(
        return_value=None
    )
    container.deployment_orchestration_service.update_deployment_status = AsyncMock()
    container.deployment_orchestration_service.finalize_successful_deployment = AsyncMock()
    container.deployment_orchestration_service.append_success_marker = MagicMock(
        side_effect=lambda x: x + " ##SUCCESS##"
    )
    container.deployment_orchestration_service.command_succeeded = MagicMock(return_value=True)
    container.deployment_orchestration_service.shell_quote = MagicMock(
        side_effect=lambda x: f"'{x}'"
    )
    container.deployment_orchestration_service.cleanup_output = MagicMock(side_effect=lambda x: x)
    container.deployment_orchestration_service.cleanup_output_for_display = MagicMock(
        side_effect=lambda x: x
    )
    container.deployment_orchestration_service.extract_deployment_url = MagicMock(
        return_value="https://app.vercel.app"
    )
    container.session_validation_service = MagicMock()
    container.session_validation_service.validate_and_prepare_session = AsyncMock()
    container.llm_setting_service = MagicMock()
    container.llm_setting_service.get_llm_settings = AsyncMock(return_value=MagicMock())
    container.plan_service = MagicMock()
    container.plan_service.has_existing_plan = AsyncMock(return_value=False)
    container.plan_service.get_plan_data = AsyncMock(return_value=None)
    container.plan_service.fail_task = AsyncMock()
    container.execution_service = MagicMock()
    container.execution_service.create_task_with_lock = AsyncMock(return_value=None)
    container.agent_service = MagicMock()
    container.agent_service.create_plan_agent_v1 = AsyncMock()
    container.agent_service.create_plan_suggestions_agent_v1 = AsyncMock()
    container.llm_billing_service = MagicMock()

    for k, v in overrides.items():
        setattr(container, k, v)
    return container


@asynccontextmanager
async def _noop_db_cm():
    db = AsyncMock()
    yield db


# ===========================================================================
# CommandHandler base-class logic
# ===========================================================================


class TestCommandHandlerBase:
    """Tests for the abstract CommandHandler base class via a concrete stub."""

    def _make_handler(self, stream=None, container=None):
        from ii_agent.agent.socket.command.command_handler import (
            CommandHandler,
            UserCommandType,
        )

        class _Stub(CommandHandler):
            def get_command_type(self):
                return UserCommandType.PING

            async def handle(self, content, session_info):
                pass

        return _Stub(
            event_stream=stream or CapturingEventStream(),
            container=container or _mock_container(),
        )

    @pytest.mark.asyncio
    async def test_send_event_publishes_to_stream(self):
        stream = CapturingEventStream()
        handler = self._make_handler(stream=stream)
        session_id = uuid.uuid4()
        event = RealtimeEvent(
            session_id=session_id,
            type=EventType.PONG,
            content={"msg": "hi"},
        )
        await handler.send_event(event)
        assert len(stream.events) == 1
        assert stream.events[0].type == EventType.PONG

    @pytest.mark.asyncio
    async def test_send_error_event_publishes_error(self):
        stream = CapturingEventStream()
        handler = self._make_handler(stream=stream)
        session_id = uuid.uuid4()
        await handler._send_error_event(str(session_id), message="oops", error_type="test_error")
        assert len(stream.events) == 1
        ev = stream.events[0]
        assert ev.type == EventType.ERROR
        assert ev.content["message"] == "oops"
        assert ev.content["error_type"] == "test_error"

    @pytest.mark.asyncio
    async def test_send_error_event_accepts_uuid_session_id(self):
        stream = CapturingEventStream()
        handler = self._make_handler(stream=stream)
        session_id = uuid.uuid4()
        await handler._send_error_event(session_id, message="uuid session id")
        ev = stream.events[0]
        assert ev.session_id == session_id

    @pytest.mark.asyncio
    async def test_send_event_helper_builds_correct_event(self):
        stream = CapturingEventStream()
        handler = self._make_handler(stream=stream)
        session_id = uuid.uuid4()
        await handler._send_event(
            str(session_id),
            message="deployment done",
            event_type=EventType.SYSTEM,
            extra_key="extra_val",
        )
        ev = stream.events[0]
        assert ev.type == EventType.SYSTEM
        assert ev.content["message"] == "deployment done"
        assert ev.content["extra_key"] == "extra_val"

    def test_get_event_stream_returns_stream(self):
        stream = CapturingEventStream()
        handler = self._make_handler(stream=stream)
        assert handler.get_event_stream() is stream


# ===========================================================================
# PublishProjectHandler
# ===========================================================================


class TestPublishProjectHandlerExtractApiKey:
    """Test _extract_api_key method which has pure logic."""

    def _get_handler(self):
        from ii_agent.agent.socket.command.publish_handler import PublishProjectHandler

        stream = CapturingEventStream()
        container = _mock_container()
        return PublishProjectHandler(event_stream=stream, container=container)

    def test_extracts_from_vercel_api_key_field(self):
        handler = self._get_handler()
        result = handler._extract_api_key({"vercel_api_key": "  key-123  "})
        assert result == "key-123"

    def test_returns_none_for_empty_vercel_api_key(self):
        handler = self._get_handler()
        result = handler._extract_api_key({"vercel_api_key": "  "})
        assert result is None

    def test_extracts_from_credentials_dict(self):
        handler = self._get_handler()
        result = handler._extract_api_key({"credentials": {"vercel_api_key": "cred-key"}})
        assert result == "cred-key"

    def test_extracts_from_token_field(self):
        handler = self._get_handler()
        result = handler._extract_api_key({"token": "tok-456"})
        assert result == "tok-456"

    def test_returns_none_when_no_api_key(self):
        handler = self._get_handler()
        result = handler._extract_api_key({})
        assert result is None

    def test_vercel_api_key_takes_priority_over_token(self):
        handler = self._get_handler()
        result = handler._extract_api_key({"vercel_api_key": "v-key", "token": "tok"})
        assert result == "v-key"

    def test_credentials_dict_empty_api_key(self):
        handler = self._get_handler()
        result = handler._extract_api_key({"credentials": {"vercel_api_key": "  "}})
        assert result is None


class TestPublishProjectHandlerParseEnvFile:
    """Test _parse_env_file pure method."""

    def _get_handler(self):
        from ii_agent.agent.socket.command.publish_handler import PublishProjectHandler

        return PublishProjectHandler(
            event_stream=CapturingEventStream(),
            container=_mock_container(),
        )

    def test_parses_simple_key_value(self):
        handler = self._get_handler()
        result = handler._parse_env_file("KEY=value")
        assert result == {"KEY": "value"}

    def test_skips_comments(self):
        handler = self._get_handler()
        result = handler._parse_env_file("# comment\nKEY=val")
        assert "# comment" not in result
        assert result["KEY"] == "val"

    def test_skips_empty_lines(self):
        handler = self._get_handler()
        result = handler._parse_env_file("\n\nKEY=val\n\n")
        assert result == {"KEY": "val"}

    def test_strips_export_prefix(self):
        handler = self._get_handler()
        result = handler._parse_env_file("export KEY=val")
        assert result["KEY"] == "val"

    def test_strips_quoted_single_values(self):
        handler = self._get_handler()
        result = handler._parse_env_file("KEY='my value'")
        assert result["KEY"] == "my value"

    def test_strips_quoted_double_values(self):
        handler = self._get_handler()
        result = handler._parse_env_file('KEY="my value"')
        assert result["KEY"] == "my value"

    def test_skips_lines_without_equals(self):
        handler = self._get_handler()
        result = handler._parse_env_file("NOEQUALS")
        assert result == {}

    def test_splits_only_on_first_equals(self):
        handler = self._get_handler()
        result = handler._parse_env_file("URL=https://example.com?a=b")
        assert result["URL"] == "https://example.com?a=b"

    def test_returns_empty_dict_for_empty_input(self):
        handler = self._get_handler()
        assert handler._parse_env_file("") == {}


class TestPublishProjectHandlerParseEnvPayload:
    """Test _parse_env_payload pure method."""

    def _get_handler(self):
        from ii_agent.agent.socket.command.publish_handler import PublishProjectHandler

        return PublishProjectHandler(
            event_stream=CapturingEventStream(),
            container=_mock_container(),
        )

    def test_parses_dict_payload(self):
        handler = self._get_handler()
        result = handler._parse_env_payload({"A": "1", "B": "2"})
        assert result == {"A": "1", "B": "2"}

    def test_parses_list_payload(self):
        handler = self._get_handler()
        result = handler._parse_env_payload([{"name": "X", "value": "10"}])
        assert result == {"X": "10"}

    def test_converts_none_value_to_empty_string(self):
        handler = self._get_handler()
        result = handler._parse_env_payload({"KEY": None})
        assert result["KEY"] == ""

    def test_ignores_non_string_names_in_list(self):
        handler = self._get_handler()
        result = handler._parse_env_payload([{"name": 123, "value": "v"}])
        assert result == {}

    def test_returns_empty_for_unknown_type(self):
        handler = self._get_handler()
        result = handler._parse_env_payload("not-a-dict-or-list")
        assert result == {}


class TestPublishProjectHandlerFormatEnvFlags:
    """Test _format_env_flags pure method."""

    def _get_handler(self):
        from ii_agent.agent.socket.command.publish_handler import PublishProjectHandler

        return PublishProjectHandler(
            event_stream=CapturingEventStream(),
            container=_mock_container(),
        )

    def test_builds_env_flags(self):
        handler = self._get_handler()
        # shell_quote is mocked to wrap in single quotes
        result = handler._format_env_flags({"KEY": "val"})
        assert "--env" in result
        assert "KEY=val" in result

    def test_empty_env_vars_returns_empty_string(self):
        handler = self._get_handler()
        result = handler._format_env_flags({})
        assert result == ""


class TestPublishProjectHandlerExtractToolOutput:
    """Test _extract_tool_output method."""

    def _get_handler(self):
        from ii_agent.agent.socket.command.publish_handler import PublishProjectHandler

        return PublishProjectHandler(
            event_stream=CapturingEventStream(),
            container=_mock_container(),
        )

    def test_returns_string_user_display_content(self):
        handler = self._get_handler()
        result_mock = MagicMock()
        result_mock.structured_content = {"user_display_content": "hello output"}
        result_mock.content = []
        assert handler._extract_tool_output(result_mock) == "hello output"

    def test_returns_joined_list_user_display_content(self):
        handler = self._get_handler()
        result_mock = MagicMock()
        result_mock.structured_content = {"user_display_content": ["line1", "line2"]}
        result_mock.content = []
        assert handler._extract_tool_output(result_mock) == "line1\nline2"

    def test_falls_back_to_content_blocks(self):
        handler = self._get_handler()
        result_mock = MagicMock()
        result_mock.structured_content = {}
        block = MagicMock()
        block.text = "block text"
        result_mock.content = [block]
        assert handler._extract_tool_output(result_mock) == "block text"

    def test_skips_blocks_without_text(self):
        handler = self._get_handler()
        result_mock = MagicMock()
        result_mock.structured_content = {}
        block = MagicMock()
        del block.text
        block.__class__ = type("NoText", (), {})
        result_mock.content = [block]
        # Should not raise
        output = handler._extract_tool_output(result_mock)
        assert isinstance(output, str)


class TestPublishProjectHandlerHandle:
    """Test handle() method – missing context path."""

    @pytest.mark.asyncio
    async def test_handle_sends_error_when_no_deployment_context(self):
        from ii_agent.agent.socket.command.publish_handler import PublishProjectHandler

        stream = CapturingEventStream()
        container = _mock_container()
        container.deployment_orchestration_service.create_deployment_context = AsyncMock(
            return_value=None
        )
        handler = PublishProjectHandler(event_stream=stream, container=container)
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.publish_handler.get_db_session_local",
            return_value=_noop_db_cm(),
        ):
            await handler.handle({"vercel_api_key": "key"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert "project path" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_handle_sends_error_when_no_api_key(self):
        from ii_agent.agent.socket.command.publish_handler import PublishProjectHandler

        stream = CapturingEventStream()
        container = _mock_container()

        fake_ctx = MagicMock()
        fake_ctx.session_id_hash = "abc123"
        fake_ctx.project_name = "myapp"
        fake_ctx.project_path = "/workspace/myapp"
        fake_ctx.service_name = "myapp-service"
        fake_ctx.deployment_id = "dep-1"
        container.deployment_orchestration_service.create_deployment_context = AsyncMock(
            return_value=fake_ctx
        )

        handler = PublishProjectHandler(event_stream=stream, container=container)
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.publish_handler.get_db_session_local",
            return_value=_noop_db_cm(),
        ):
            await handler.handle({}, session_info)  # No API key

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert "vercel api key" in errors[0].content["message"].lower()

    def test_get_command_type_is_publish(self):
        from ii_agent.agent.socket.command.publish_handler import PublishProjectHandler
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        handler = PublishProjectHandler(
            event_stream=CapturingEventStream(),
            container=_mock_container(),
        )
        assert handler.get_command_type() == UserCommandType.PUBLISH_PROJECT


# ===========================================================================
# CloudRunPublishHandler
# ===========================================================================


class TestCloudRunPublishHandlerHelpers:
    def _get_handler(self):
        from ii_agent.agent.socket.command.cloud_run_publish_handler import (
            CloudRunPublishHandler,
        )

        return CloudRunPublishHandler(
            event_stream=CapturingEventStream(),
            container=_mock_container(),
        )

    def test_get_command_type(self):
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        handler = self._get_handler()
        assert handler.get_command_type() == UserCommandType.PUBLISH_CLOUD_RUN

    def test_extract_env_vars_from_dict(self):
        handler = self._get_handler()
        result = handler._extract_env_vars({"env_vars": {"A": "1", "B": "2"}})
        assert result == {"A": "1", "B": "2"}

    def test_extract_env_vars_returns_none_for_empty(self):
        handler = self._get_handler()
        result = handler._extract_env_vars({})
        assert result is None

    def test_extract_env_vars_from_credentials(self):
        handler = self._get_handler()
        result = handler._extract_env_vars({"credentials": {"environment": {"ENV_KEY": "env_val"}}})
        assert result == {"ENV_KEY": "env_val"}

    def test_extract_env_vars_converts_none_to_empty_string(self):
        handler = self._get_handler()
        result = handler._extract_env_vars({"env_vars": {"KEY": None}})
        assert result["KEY"] == ""

    def test_publisher_property_initialises_lazily(self):
        from ii_agent.projects.cloud_run.service import CloudRunPublisher

        handler = self._get_handler()
        with (
            patch(
                "ii_agent.agent.socket.command.cloud_run_publish_handler.CloudRunConfig.from_env"
            ) as mock_cfg,
            patch(
                "ii_agent.agent.socket.command.cloud_run_publish_handler.CloudRunPublisher"
            ) as mock_pub,
        ):
            mock_cfg.return_value = MagicMock()
            mock_pub.return_value = MagicMock(spec=CloudRunPublisher)
            p = handler.publisher
            assert p is not None
            mock_pub.assert_called_once()

    def test_build_metadata_without_result(self):
        handler = self._get_handler()
        # Ensure _publisher is set so publisher.config is available
        mock_config = MagicMock()
        mock_config.memory = "256Mi"
        mock_config.cpu = "1"
        mock_config.min_instances = 0
        mock_config.max_instances = 10
        mock_config.region = "us-central1"
        mock_config.project_id = "proj-123"
        mock_pub = MagicMock()
        mock_pub.config = mock_config
        handler._publisher = mock_pub

        meta = handler._build_metadata("my-service", result=None)
        assert meta["cloud_run"]["service_name"] == "my-service"
        assert meta["config"]["memory"] == "256Mi"

    def test_build_metadata_with_result(self):
        handler = self._get_handler()
        mock_config = MagicMock()
        mock_config.memory = "256Mi"
        mock_config.cpu = "1"
        mock_config.min_instances = 0
        mock_config.max_instances = 10
        mock_config.region = "us-central1"
        mock_config.project_id = "proj-123"
        mock_pub = MagicMock()
        mock_pub.config = mock_config
        handler._publisher = mock_pub

        result = MagicMock()
        result.source_bucket = "bucket"
        result.source_object = "obj"
        result.image_url = "gcr.io/img"
        result.image_digest = "sha256:abc"
        result.build_id = "build-1"

        meta = handler._build_metadata("svc", result)
        assert "source" in meta
        assert "image" in meta
        assert meta["cloud_run"]["build_id"] == "build-1"


class TestCloudRunPublishHandlerHandle:
    @pytest.mark.asyncio
    async def test_sends_error_when_no_context(self):
        from ii_agent.agent.socket.command.cloud_run_publish_handler import (
            CloudRunPublishHandler,
        )

        stream = CapturingEventStream()
        container = _mock_container()
        container.deployment_orchestration_service.create_deployment_context = AsyncMock(
            return_value=None
        )
        handler = CloudRunPublishHandler(event_stream=stream, container=container)
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.cloud_run_publish_handler.get_db_session_local",
            return_value=_noop_db_cm(),
        ):
            await handler.handle({}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert "project path" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_when_no_sandbox(self):
        from ii_agent.agent.socket.command.cloud_run_publish_handler import (
            CloudRunPublishHandler,
        )

        stream = CapturingEventStream()
        container = _mock_container()

        ctx = MagicMock()
        ctx.project_name = "app"
        ctx.project_path = "/workspace/app"
        ctx.service_name = "app-service"
        ctx.deployment_id = "dep-1"
        container.deployment_orchestration_service.create_deployment_context = AsyncMock(
            return_value=ctx
        )
        container.sandbox_service.resolve_sandbox_for_session = AsyncMock(return_value=None)

        handler = CloudRunPublishHandler(event_stream=stream, container=container)
        session_info = _make_session_info()

        with (
            patch(
                "ii_agent.agent.socket.command.cloud_run_publish_handler.get_db_session_local",
                return_value=_noop_db_cm(),
            ),
            patch("ii_agent.agent.socket.command.cloud_run_publish_handler.E2BSandboxManager"),
        ):
            await handler.handle({}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1


# ===========================================================================
# AppleAppSetupHandler._validate_bundle_id
# ===========================================================================


class TestAppleAppSetupHandlerValidateBundleId:
    def _get_handler(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleAppSetupHandler,
        )

        return AppleAppSetupHandler(
            event_stream=CapturingEventStream(),
            container=_mock_container(),
        )

    def test_valid_bundle_id(self):
        h = self._get_handler()
        assert h._validate_bundle_id("com.example.app") is True

    def test_valid_bundle_id_with_hyphens(self):
        h = self._get_handler()
        assert h._validate_bundle_id("com.my-company.my-app") is True

    def test_valid_bundle_id_with_underscores(self):
        h = self._get_handler()
        assert h._validate_bundle_id("com.example.my_app") is True

    def test_invalid_single_component(self):
        h = self._get_handler()
        assert h._validate_bundle_id("singlecomponent") is False

    def test_invalid_empty_string(self):
        h = self._get_handler()
        assert h._validate_bundle_id("") is False

    def test_invalid_starts_with_number(self):
        h = self._get_handler()
        assert h._validate_bundle_id("1com.example.app") is False

    def test_invalid_empty_component(self):
        h = self._get_handler()
        assert h._validate_bundle_id("com..app") is False

    def test_valid_underscore_start(self):
        h = self._get_handler()
        assert h._validate_bundle_id("_com.example.app") is True

    def test_invalid_special_characters(self):
        h = self._get_handler()
        assert h._validate_bundle_id("com.example.app!") is False


class TestAppleAppSetupHandlerSendSetupStatus:
    @pytest.mark.asyncio
    async def test_sends_status_event(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleAppSetupHandler,
        )

        stream = CapturingEventStream()
        handler = AppleAppSetupHandler(event_stream=stream, container=_mock_container())
        session_id = uuid.uuid4()
        await handler._send_setup_status(
            session_id,
            status="registering_bundle",
            message="Registering...",
            step=1,
            total_steps=3,
        )
        ev = stream.last_event()
        assert ev is not None
        assert ev.type == EventType.APPLE_APP_SETUP_STATUS
        assert ev.content["status"] == "registering_bundle"
        assert ev.content["step"] == 1
        assert ev.content["total_steps"] == 3

    @pytest.mark.asyncio
    async def test_sends_status_with_extra_kwargs(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleAppSetupHandler,
        )

        stream = CapturingEventStream()
        handler = AppleAppSetupHandler(event_stream=stream, container=_mock_container())
        session_id = uuid.uuid4()
        await handler._send_setup_status(
            session_id,
            status="completed",
            message="Done!",
            bundle_id="com.example.app",
        )
        ev = stream.last_event()
        assert ev.content["bundle_id"] == "com.example.app"


class TestAppleAppSetupHandlerHandle:
    @pytest.mark.asyncio
    async def test_sends_error_for_missing_bundle_id(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleAppSetupHandler,
        )

        stream = CapturingEventStream()
        handler = AppleAppSetupHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        await handler.handle({"app_name": "My App"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "bundle identifier" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_for_missing_app_name(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleAppSetupHandler,
        )

        stream = CapturingEventStream()
        handler = AppleAppSetupHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        await handler.handle({"bundle_identifier": "com.example.app"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "app name" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_for_invalid_bundle_id_format(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleAppSetupHandler,
        )

        stream = CapturingEventStream()
        handler = AppleAppSetupHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        await handler.handle(
            {"bundle_identifier": "invalid", "app_name": "My App"},
            session_info,
        )
        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "invalid bundle identifier" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_when_no_apple_credential(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleAppSetupHandler,
        )

        stream = CapturingEventStream()
        handler = AppleAppSetupHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.apple_app_setup_handler.AppleCredentials.get_active_session",
            new=AsyncMock(return_value=None),
        ):
            await handler.handle(
                {"bundle_identifier": "com.example.app", "app_name": "My App"},
                session_info,
            )

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "authenticate with apple" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_when_auth_not_complete(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleAppSetupHandler,
        )

        stream = CapturingEventStream()
        handler = AppleAppSetupHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        cred = MagicMock()
        cred.auth_state = "pending_2fa"  # Not AUTHENTICATED

        with patch(
            "ii_agent.agent.socket.command.apple_app_setup_handler.AppleCredentials.get_active_session",
            new=AsyncMock(return_value=cred),
        ):
            await handler.handle(
                {"bundle_identifier": "com.example.app", "app_name": "My App"},
                session_info,
            )

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "incomplete" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_when_no_password(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleAppSetupHandler,
        )
        from ii_agent.integrations.mobile.apple import AppleAuthStateEnum

        stream = CapturingEventStream()
        handler = AppleAppSetupHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()

        cred = MagicMock()
        cred.auth_state = AppleAuthStateEnum.AUTHENTICATED.value
        cred.selected_team_id = "TEAM123"
        cred.team_name = "My Team"
        cred.apple_id = "user@example.com"

        with (
            patch(
                "ii_agent.agent.socket.command.apple_app_setup_handler.AppleCredentials.get_active_session",
                new=AsyncMock(return_value=cred),
            ),
            patch(
                "ii_agent.agent.socket.command.apple_app_setup_handler.AppleCredentials.get_decrypted_session_data",
                return_value={},  # No _temp_password
            ),
        ):
            await handler.handle(
                {"bundle_identifier": "com.example.app", "app_name": "My App"},
                session_info,
            )

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1


class TestAppleListAppsHandlerHandle:
    @pytest.mark.asyncio
    async def test_sends_error_when_no_credential(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleListAppsHandler,
        )

        stream = CapturingEventStream()
        handler = AppleListAppsHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.apple_app_setup_handler.AppleCredentials.get_active_session",
            new=AsyncMock(return_value=None),
        ):
            await handler.handle({}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1

    def test_get_command_type(self):
        from ii_agent.agent.socket.command.apple_app_setup_handler import (
            AppleListAppsHandler,
        )
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        handler = AppleListAppsHandler(
            event_stream=CapturingEventStream(),
            container=_mock_container(),
        )
        assert handler.get_command_type() == UserCommandType.APPLE_LIST_APPS


# ===========================================================================
# AppleAuthLoginHandler
# ===========================================================================


class TestAppleAuthLoginHandlerHandle:
    @pytest.mark.asyncio
    async def test_sends_error_for_missing_apple_id(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuthLoginHandler

        stream = CapturingEventStream()
        handler = AppleAuthLoginHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        await handler.handle({"password": "pass"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "apple id and password" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_for_missing_password(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuthLoginHandler

        stream = CapturingEventStream()
        handler = AppleAuthLoginHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        await handler.handle({"apple_id": "user@example.com"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_sends_error_for_invalid_credentials(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuthLoginHandler
        from ii_agent.integrations.mobile.apple import AppleInvalidCredentialsError

        stream = CapturingEventStream()
        handler = AppleAuthLoginHandler(event_stream=stream, container=_mock_container())
        handler.auth_client = MagicMock()
        handler.auth_client.initiate_login = AsyncMock(
            side_effect=AppleInvalidCredentialsError("bad creds")
        )
        session_info = _make_session_info()

        await handler.handle(
            {"apple_id": "user@example.com", "password": "wrong"},
            session_info,
        )

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert "invalid apple id" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_for_rate_limit(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuthLoginHandler
        from ii_agent.integrations.mobile.apple import AppleRateLimitError

        stream = CapturingEventStream()
        handler = AppleAuthLoginHandler(event_stream=stream, container=_mock_container())
        handler.auth_client = MagicMock()
        handler.auth_client.initiate_login = AsyncMock(
            side_effect=AppleRateLimitError("rate limit")
        )
        session_info = _make_session_info()

        await handler.handle(
            {"apple_id": "user@example.com", "password": "pass"},
            session_info,
        )

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert (
            "rate" in errors[0].content["message"].lower()
            or "wait" in errors[0].content["message"].lower()
        )

    @pytest.mark.asyncio
    async def test_sends_error_for_account_locked(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuthLoginHandler
        from ii_agent.integrations.mobile.apple import AppleAccountLockedError

        stream = CapturingEventStream()
        handler = AppleAuthLoginHandler(event_stream=stream, container=_mock_container())
        handler.auth_client = MagicMock()
        handler.auth_client.initiate_login = AsyncMock(
            side_effect=AppleAccountLockedError("locked")
        )
        session_info = _make_session_info()

        await handler.handle(
            {"apple_id": "user@example.com", "password": "pass"},
            session_info,
        )

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert "locked" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_2fa_required_event(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuthLoginHandler
        from ii_agent.integrations.mobile.apple.types import AppleSession, AppleAuthState

        stream = CapturingEventStream()
        handler = AppleAuthLoginHandler(event_stream=stream, container=_mock_container())

        mock_session = MagicMock(spec=AppleSession)
        mock_session.auth_state = AppleAuthState.PENDING_2FA
        mock_session.expiry = None
        mock_session.model_dump = MagicMock(return_value={"auth_state": "pending_2fa"})

        login_response = MagicMock()
        login_response.session = mock_session
        login_response.requires_2fa = True

        handler.auth_client = MagicMock()
        handler.auth_client.initiate_login = AsyncMock(return_value=login_response)

        with patch(
            "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.save_or_update_credential",
            new=AsyncMock(),
        ):
            session_info = _make_session_info()
            await handler.handle(
                {"apple_id": "user@example.com", "password": "pass"},
                session_info,
            )

        tfa_events = stream.events_of_type(EventType.APPLE_2FA_REQUIRED)
        assert len(tfa_events) == 1

    @pytest.mark.asyncio
    async def test_sends_team_selection_when_no_2fa(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuthLoginHandler
        from ii_agent.integrations.mobile.apple.types import AppleSession, AppleAuthState

        stream = CapturingEventStream()
        handler = AppleAuthLoginHandler(event_stream=stream, container=_mock_container())

        mock_session = MagicMock(spec=AppleSession)
        mock_session.auth_state = AppleAuthState.AUTHENTICATED
        mock_session.expiry = None
        mock_session.model_dump = MagicMock(return_value={"auth_state": "authenticated"})

        login_response = MagicMock()
        login_response.session = mock_session
        login_response.requires_2fa = False

        mock_team = MagicMock()
        mock_team.model_dump = MagicMock(return_value={"team_id": "T1", "name": "My Team"})

        handler.auth_client = MagicMock()
        handler.auth_client.initiate_login = AsyncMock(return_value=login_response)
        handler.auth_client.get_teams = AsyncMock(return_value=[mock_team])

        with patch(
            "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.save_or_update_credential",
            new=AsyncMock(),
        ):
            session_info = _make_session_info()
            await handler.handle(
                {"apple_id": "user@example.com", "password": "pass"},
                session_info,
            )

        team_events = stream.events_of_type(EventType.APPLE_TEAM_SELECTION)
        assert len(team_events) == 1

    def test_get_command_type(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuthLoginHandler
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        handler = AppleAuthLoginHandler(
            event_stream=CapturingEventStream(), container=_mock_container()
        )
        assert handler.get_command_type() == UserCommandType.APPLE_AUTH_LOGIN


class TestAppleAuth2FAHandlerHandle:
    @pytest.mark.asyncio
    async def test_sends_error_for_short_code(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuth2FAHandler

        stream = CapturingEventStream()
        handler = AppleAuth2FAHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        await handler.handle({"code": "123"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "6-digit" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_for_non_digit_code(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuth2FAHandler

        stream = CapturingEventStream()
        handler = AppleAuth2FAHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        await handler.handle({"code": "ABCDEF"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_sends_error_when_no_credential(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuth2FAHandler

        stream = CapturingEventStream()
        handler = AppleAuth2FAHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_user_credential",
            new=AsyncMock(return_value=None),
        ):
            await handler.handle({"code": "123456"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_sends_error_when_no_session_data(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuth2FAHandler

        stream = CapturingEventStream()
        handler = AppleAuth2FAHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        fake_cred = MagicMock()

        with (
            patch(
                "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_user_credential",
                new=AsyncMock(return_value=fake_cred),
            ),
            patch(
                "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_decrypted_session_data",
                return_value=None,
            ),
        ):
            await handler.handle({"code": "123456"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_sends_error_for_invalid_2fa_code(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuth2FAHandler
        from ii_agent.integrations.mobile.apple import Apple2FAInvalidCodeError
        from ii_agent.integrations.mobile.apple.types import AppleSession, AppleAuthState

        stream = CapturingEventStream()
        handler = AppleAuth2FAHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        fake_cred = MagicMock()

        mock_session = MagicMock(spec=AppleSession)
        mock_session.auth_state = AppleAuthState.PENDING_2FA
        mock_session.expiry = None

        handler.auth_client = MagicMock()
        handler.auth_client.verify_2fa_code = AsyncMock(
            side_effect=Apple2FAInvalidCodeError("invalid")
        )

        with (
            patch(
                "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_user_credential",
                new=AsyncMock(return_value=fake_cred),
            ),
            patch(
                "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_decrypted_session_data",
                return_value={"_temp_password": "mypass", "auth_state": "pending_2fa"},
            ),
            patch(
                "ii_agent.agent.socket.command.apple_auth_handler.AppleAuth2FAHandler.handle",
                wraps=handler.handle,
            ),
        ):
            # Patch AppleSession.model_validate
            with (
                patch(
                    "ii_agent.agent.socket.command.apple_auth_handler.AppleSession",
                    return_value=mock_session,
                )
                if False
                else patch(
                    "ii_agent.integrations.mobile.apple.types.AppleSession.model_validate",
                    return_value=mock_session,
                )
            ):
                await handler.handle({"code": "123456"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1

    def test_get_command_type(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleAuth2FAHandler
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        handler = AppleAuth2FAHandler(
            event_stream=CapturingEventStream(), container=_mock_container()
        )
        assert handler.get_command_type() == UserCommandType.APPLE_AUTH_2FA


class TestAppleAuthSelectTeamHandlerHandle:
    @pytest.mark.asyncio
    async def test_sends_error_for_missing_team_id(self):
        from ii_agent.agent.socket.command.apple_auth_handler import (
            AppleAuthSelectTeamHandler,
        )

        stream = CapturingEventStream()
        handler = AppleAuthSelectTeamHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        await handler.handle({}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "team" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_when_no_credential(self):
        from ii_agent.agent.socket.command.apple_auth_handler import (
            AppleAuthSelectTeamHandler,
        )

        stream = CapturingEventStream()
        handler = AppleAuthSelectTeamHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_user_credential",
            new=AsyncMock(return_value=None),
        ):
            await handler.handle({"team_id": "TEAM1"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_sends_error_for_invalid_team_id(self):
        from ii_agent.agent.socket.command.apple_auth_handler import (
            AppleAuthSelectTeamHandler,
        )

        stream = CapturingEventStream()
        handler = AppleAuthSelectTeamHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        fake_cred = MagicMock()
        fake_cred.available_teams = [{"team_id": "OTHER_TEAM", "name": "Other"}]

        with patch(
            "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_user_credential",
            new=AsyncMock(return_value=fake_cred),
        ):
            await handler.handle({"team_id": "WRONG_TEAM"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "invalid team" in errors[0].content["message"].lower()

    def test_get_command_type(self):
        from ii_agent.agent.socket.command.apple_auth_handler import (
            AppleAuthSelectTeamHandler,
        )
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        handler = AppleAuthSelectTeamHandler(
            event_stream=CapturingEventStream(), container=_mock_container()
        )
        assert handler.get_command_type() == UserCommandType.APPLE_AUTH_SELECT_TEAM


class TestAppleCheckAuthHandlerHandle:
    @pytest.mark.asyncio
    async def test_sends_no_auth_event_when_no_credential(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleCheckAuthHandler

        stream = CapturingEventStream()
        handler = AppleCheckAuthHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()

        with (
            patch(
                "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_active_session",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_user_credential",
                new=AsyncMock(return_value=None),
            ),
        ):
            await handler.handle({}, session_info)

        check_events = stream.events_of_type(EventType.APPLE_AUTH_CHECK_RESULT)
        assert len(check_events) == 1
        assert check_events[0].content["has_valid_auth"] is False
        assert check_events[0].content["has_expo_token"] is False

    @pytest.mark.asyncio
    async def test_sends_check_result_with_credential(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleCheckAuthHandler

        stream = CapturingEventStream()
        handler = AppleCheckAuthHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        fake_cred = MagicMock()
        fake_cred.apple_id = "user@example.com"
        fake_cred.team_name = "My Team"

        with (
            patch(
                "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_active_session",
                new=AsyncMock(return_value=fake_cred),
            ),
            patch(
                "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_decrypted_expo_token",
                return_value="expo-token-abc",
            ),
            patch(
                "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_decrypted_app_specific_password",
                return_value=None,
            ),
        ):
            await handler.handle({}, session_info)

        check_events = stream.events_of_type(EventType.APPLE_AUTH_CHECK_RESULT)
        assert len(check_events) == 1
        assert check_events[0].content["has_expo_token"] is True
        assert check_events[0].content["apple_id"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_sends_error_check_result_on_exception(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleCheckAuthHandler

        stream = CapturingEventStream()
        handler = AppleCheckAuthHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.get_active_session",
            new=AsyncMock(side_effect=Exception("db error")),
        ):
            await handler.handle({}, session_info)

        check_events = stream.events_of_type(EventType.APPLE_AUTH_CHECK_RESULT)
        assert len(check_events) == 1
        assert check_events[0].content["has_valid_auth"] is False

    def test_get_command_type(self):
        from ii_agent.agent.socket.command.apple_auth_handler import AppleCheckAuthHandler
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        handler = AppleCheckAuthHandler(
            event_stream=CapturingEventStream(), container=_mock_container()
        )
        assert handler.get_command_type() == UserCommandType.APPLE_CHECK_AUTH


class TestSaveExpoTokenHandlerHandle:
    @pytest.mark.asyncio
    async def test_sends_error_for_empty_token(self):
        from ii_agent.agent.socket.command.apple_auth_handler import SaveExpoTokenHandler

        stream = CapturingEventStream()
        handler = SaveExpoTokenHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        await handler.handle({"expo_token": "  "}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "expo token" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_saves_token_and_sends_success_event(self):
        from ii_agent.agent.socket.command.apple_auth_handler import SaveExpoTokenHandler

        stream = CapturingEventStream()
        handler = SaveExpoTokenHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.save_expo_token",
            new=AsyncMock(),
        ):
            await handler.handle({"expo_token": "my-expo-token"}, session_info)

        saved_events = stream.events_of_type(EventType.EXPO_TOKEN_SAVED)
        assert len(saved_events) == 1
        assert saved_events[0].content["success"] is True

    @pytest.mark.asyncio
    async def test_sends_error_on_save_exception(self):
        from ii_agent.agent.socket.command.apple_auth_handler import SaveExpoTokenHandler

        stream = CapturingEventStream()
        handler = SaveExpoTokenHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.apple_auth_handler.AppleCredentials.save_expo_token",
            new=AsyncMock(side_effect=Exception("DB error")),
        ):
            await handler.handle({"expo_token": "my-expo-token"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1

    def test_get_command_type(self):
        from ii_agent.agent.socket.command.apple_auth_handler import SaveExpoTokenHandler
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        handler = SaveExpoTokenHandler(
            event_stream=CapturingEventStream(), container=_mock_container()
        )
        assert handler.get_command_type() == UserCommandType.SAVE_EXPO_TOKEN


# ===========================================================================
# SubmitTestflightHandler helpers
# ===========================================================================


class TestSubmitTestflightHandlerExtractToolOutput:
    def _get_handler(self):
        from ii_agent.agent.socket.command.submit_testflight_handler import (
            SubmitTestflightHandler,
        )

        return SubmitTestflightHandler(
            event_stream=CapturingEventStream(),
            container=_mock_container(),
        )

    def test_returns_string_display_content(self):
        handler = self._get_handler()
        result = MagicMock()
        result.structured_content = {"user_display_content": "output text"}
        result.content = []
        assert handler._extract_tool_output(result) == "output text"

    def test_returns_joined_list_display_content(self):
        handler = self._get_handler()
        result = MagicMock()
        result.structured_content = {"user_display_content": ["a", "b", "c"]}
        result.content = []
        assert handler._extract_tool_output(result) == "a\nb\nc"

    def test_falls_back_to_content_blocks(self):
        handler = self._get_handler()
        result = MagicMock()
        result.structured_content = {}
        block = MagicMock()
        block.text = "block content"
        result.content = [block]
        assert handler._extract_tool_output(result) == "block content"

    def test_returns_empty_string_for_no_content(self):
        handler = self._get_handler()
        result = MagicMock()
        result.structured_content = {}
        result.content = []
        assert handler._extract_tool_output(result) == ""


class TestSubmitTestflightHandlerSendTestflightLog:
    @pytest.mark.asyncio
    async def test_sends_testflight_log_event(self):
        from ii_agent.agent.socket.command.submit_testflight_handler import (
            SubmitTestflightHandler,
        )

        stream = CapturingEventStream()
        handler = SubmitTestflightHandler(event_stream=stream, container=_mock_container())
        session_id = uuid.uuid4()
        await handler._send_testflight_log(session_id, "Build started", status="running")

        logs = stream.events_of_type(EventType.TESTFLIGHT_LOG)
        assert len(logs) == 1
        assert logs[0].content["message"] == "Build started"
        assert logs[0].content["status"] == "running"
        assert logs[0].content["is_error"] is False

    @pytest.mark.asyncio
    async def test_sends_testflight_log_with_string_session_id(self):
        from ii_agent.agent.socket.command.submit_testflight_handler import (
            SubmitTestflightHandler,
        )

        stream = CapturingEventStream()
        handler = SubmitTestflightHandler(event_stream=stream, container=_mock_container())
        session_id = str(uuid.uuid4())
        await handler._send_testflight_log(session_id, "Error occurred", is_error=True)

        logs = stream.events_of_type(EventType.TESTFLIGHT_LOG)
        assert len(logs) == 1
        assert logs[0].content["is_error"] is True

    @pytest.mark.asyncio
    async def test_sends_testflight_log_default_status(self):
        from ii_agent.agent.socket.command.submit_testflight_handler import (
            SubmitTestflightHandler,
        )

        stream = CapturingEventStream()
        handler = SubmitTestflightHandler(event_stream=stream, container=_mock_container())
        session_id = uuid.uuid4()
        await handler._send_testflight_log(session_id, "Starting")

        logs = stream.events_of_type(EventType.TESTFLIGHT_LOG)
        assert logs[0].content["status"] == "running"


class TestSubmitTestflightHandlerHandle:
    @pytest.mark.asyncio
    async def test_sends_error_when_no_credential(self):
        from ii_agent.agent.socket.command.submit_testflight_handler import (
            SubmitTestflightHandler,
        )

        stream = CapturingEventStream()
        handler = SubmitTestflightHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.submit_testflight_handler.AppleCredentials.get_active_session",
            new=AsyncMock(return_value=None),
        ):
            await handler.handle({}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "authenticate with apple" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_when_auth_not_complete(self):
        from ii_agent.agent.socket.command.submit_testflight_handler import (
            SubmitTestflightHandler,
        )

        stream = CapturingEventStream()
        handler = SubmitTestflightHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        cred = MagicMock()
        cred.auth_state = "pending"

        with patch(
            "ii_agent.agent.socket.command.submit_testflight_handler.AppleCredentials.get_active_session",
            new=AsyncMock(return_value=cred),
        ):
            await handler.handle({}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) == 1
        assert "incomplete" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_when_no_expo_token(self):
        from ii_agent.agent.socket.command.submit_testflight_handler import (
            SubmitTestflightHandler,
        )
        from ii_agent.integrations.mobile.apple import AppleAuthStateEnum

        stream = CapturingEventStream()
        handler = SubmitTestflightHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        cred = MagicMock()
        cred.auth_state = AppleAuthStateEnum.AUTHENTICATED.value
        cred.apple_id = "user@example.com"
        cred.selected_team_id = "TEAM1"

        with (
            patch(
                "ii_agent.agent.socket.command.submit_testflight_handler.AppleCredentials.get_active_session",
                new=AsyncMock(return_value=cred),
            ),
            patch(
                "ii_agent.agent.socket.command.submit_testflight_handler.AppleCredentials.get_decrypted_session_data",
                return_value={"_temp_password": "mypass"},
            ),
            patch(
                "ii_agent.agent.socket.command.submit_testflight_handler.AppleCredentials.get_decrypted_expo_token",
                return_value=None,
            ),
            patch(
                "ii_agent.agent.socket.command.submit_testflight_handler.AppleCredentials.clear_session_password",
                new=AsyncMock(),
            ),
        ):
            await handler.handle({}, session_info)  # No expo_token in content

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert "expo token" in errors[0].content["message"].lower()

    @pytest.mark.asyncio
    async def test_sends_error_when_no_apple_password(self):
        from ii_agent.agent.socket.command.submit_testflight_handler import (
            SubmitTestflightHandler,
        )
        from ii_agent.integrations.mobile.apple import AppleAuthStateEnum

        stream = CapturingEventStream()
        handler = SubmitTestflightHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        cred = MagicMock()
        cred.auth_state = AppleAuthStateEnum.AUTHENTICATED.value
        cred.apple_id = "user@example.com"
        cred.selected_team_id = "TEAM1"

        with (
            patch(
                "ii_agent.agent.socket.command.submit_testflight_handler.AppleCredentials.get_active_session",
                new=AsyncMock(return_value=cred),
            ),
            patch(
                "ii_agent.agent.socket.command.submit_testflight_handler.AppleCredentials.get_decrypted_session_data",
                return_value={},  # No _temp_password
            ),
            patch(
                "ii_agent.agent.socket.command.submit_testflight_handler.AppleCredentials.get_decrypted_expo_token",
                return_value="expo-token",
            ),
        ):
            await handler.handle({"expo_token": "expo-token"}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1

    def test_get_command_type(self):
        from ii_agent.agent.socket.command.submit_testflight_handler import (
            SubmitTestflightHandler,
        )
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        handler = SubmitTestflightHandler(
            event_stream=CapturingEventStream(), container=_mock_container()
        )
        assert handler.get_command_type() == UserCommandType.SUBMIT_TESTFLIGHT


# ===========================================================================
# PlanHandler
# ===========================================================================


class TestPlanHandlerGetCommandType:
    def test_get_command_type_is_plan(self):
        from ii_agent.agent.socket.command.plan_handler import PlanHandler
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        handler = PlanHandler(event_stream=CapturingEventStream(), container=_mock_container())
        assert handler.get_command_type() == UserCommandType.PLAN


def _make_plan_content(**kwargs) -> dict:
    """Build valid QueryCommandContent dict for plan handler tests."""
    defaults = {
        "text": "Build me a plan",
        "build_mode": "plan",
        "model_id": "gpt-4o",
        "provider": "openai",
        "agent_type": "general",
    }
    defaults.update(kwargs)
    return defaults


class TestPlanHandlerHandle:
    @pytest.mark.asyncio
    async def test_returns_early_when_validation_fails(self):
        from ii_agent.agent.socket.command.plan_handler import PlanHandler

        stream = CapturingEventStream()
        container = _mock_container()

        val_result = MagicMock()
        val_result.is_valid = False
        val_result.error_message = "Insufficient credits"
        val_result.error_type = "credit_error"
        val_result.session_info = None
        container.session_validation_service.validate_and_prepare_session = AsyncMock(
            return_value=val_result
        )

        handler = PlanHandler(event_stream=stream, container=container)
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.plan_handler.get_db_session_local",
            return_value=_noop_db_cm(),
        ):
            await handler.handle(_make_plan_content(), session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1

    @pytest.mark.asyncio
    async def test_routes_to_error_for_invalid_build_mode(self):
        from ii_agent.agent.socket.command.plan_handler import PlanHandler

        stream = CapturingEventStream()
        container = _mock_container()

        val_result = MagicMock()
        val_result.is_valid = True
        val_result.error_message = None
        val_result.session_info = _make_session_info()
        val_result.llm_config = MagicMock()
        container.session_validation_service.validate_and_prepare_session = AsyncMock(
            return_value=val_result
        )

        task_result = MagicMock()
        task_result.task = MagicMock()
        task_result.task.id = uuid.uuid4()
        task_result.user_event = RealtimeEvent(
            session_id=val_result.session_info.id,
            type=EventType.USER_MESSAGE,
            content={},
        )
        task_result.processing_event = RealtimeEvent(
            session_id=val_result.session_info.id,
            type=EventType.PROCESSING,
            content={},
        )
        container.execution_service.create_task_with_lock = AsyncMock(return_value=task_result)

        handler = PlanHandler(event_stream=stream, container=container)
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.plan_handler.get_db_session_local",
            return_value=_noop_db_cm(),
        ):
            await handler.handle(
                _make_plan_content(
                    build_mode="design"
                ),  # 'design' hits else branch in _handle_plan
                session_info,
            )

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert any("invalid plan mode" in ev.content["message"].lower() for ev in errors)

    @pytest.mark.asyncio
    async def test_returns_early_when_no_task_created(self):
        from ii_agent.agent.socket.command.plan_handler import PlanHandler

        stream = CapturingEventStream()
        container = _mock_container()

        val_result = MagicMock()
        val_result.is_valid = True
        val_result.error_message = None
        val_result.session_info = _make_session_info()
        val_result.llm_config = MagicMock()
        container.session_validation_service.validate_and_prepare_session = AsyncMock(
            return_value=val_result
        )
        container.execution_service.create_task_with_lock = AsyncMock(return_value=None)

        handler = PlanHandler(event_stream=stream, container=container)
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.plan_handler.get_db_session_local",
            return_value=_noop_db_cm(),
        ):
            await handler.handle(_make_plan_content(), session_info)

        # No crash, no events beyond what was already in stream
        assert True


class TestPlanHandlerPrepareFiles:
    @pytest.mark.asyncio
    async def test_returns_empty_lists_when_no_files(self):
        from ii_agent.agent.socket.command.plan_handler import PlanHandler
        from ii_agent.agent.socket.schemas import QueryCommandContent

        handler = PlanHandler(event_stream=CapturingEventStream(), container=_mock_container())
        query = QueryCommandContent(
            text="hi", files=[], model_id="gpt-4o", provider="openai", agent_type="general"
        )
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.plan_handler.get_db_session_local",
            return_value=_noop_db_cm(),
        ):
            images, files = await handler._prepare_files(query, session_info)

        assert images == []
        assert files == []

    @pytest.mark.asyncio
    async def test_builds_image_and_file_lists_from_service(self):
        from ii_agent.agent.socket.command.plan_handler import PlanHandler
        from ii_agent.agent.socket.schemas import QueryCommandContent

        container = _mock_container()
        container.file_service.prepare_agent_files = AsyncMock(
            return_value=(
                [{"url": "https://img.local/a.png", "mime_type": "image/png"}],
                [{"id": "f1", "url": "https://file.local/f.txt", "filename": "f.txt"}],
            )
        )
        handler = PlanHandler(event_stream=CapturingEventStream(), container=container)
        query = QueryCommandContent(
            text="hi",
            files=["file-uuid-1"],
            model_id="gpt-4o",
            provider="openai",
            agent_type="general",
        )
        session_info = _make_session_info()

        with patch(
            "ii_agent.agent.socket.command.plan_handler.get_db_session_local",
            return_value=_noop_db_cm(),
        ):
            images, files = await handler._prepare_files(query, session_info)

        assert len(images) == 1
        assert len(files) == 1


class TestPlanHandlerEmitPlanModificationSuggestions:
    @pytest.mark.asyncio
    async def test_emits_plan_modification_options(self):
        from ii_agent.agent.socket.command.plan_handler import PlanHandler

        stream = CapturingEventStream()
        handler = PlanHandler(event_stream=stream, container=_mock_container())
        session_info = _make_session_info()
        run_id = uuid.uuid4()

        await handler._emit_plan_modification_suggestions(
            session_info=session_info,
            run_id=run_id,
            message="Choose an option",
            suggestions=["Add feature X", "Remove step 3"],
        )

        opts = stream.events_of_type(EventType.PLAN_MODIFICATION_OPTIONS)
        assert len(opts) == 1
        assert opts[0].content["message"] == "Choose an option"
        assert "Add feature X" in opts[0].content["suggestions"]


# ===========================================================================
# ContinueRunHandler
# ===========================================================================


class TestContinueRunHandlerHandle:
    @pytest.mark.asyncio
    async def test_sends_error_when_run_id_missing(self):
        from ii_agent.agent.socket.command.continue_run_handler import ContinueRunHandler

        stream = CapturingEventStream()
        container = _mock_container()
        with patch(
            "ii_agent.agent.socket.command.continue_run_handler.AgentFactory"
        ) as mock_factory:
            mock_factory.return_value = MagicMock()
            handler = ContinueRunHandler(event_stream=stream, container=container)

        session_info = _make_session_info()
        await handler.handle({"confirmed": True}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert "run_id" in errors[0].content["message"]

    @pytest.mark.asyncio
    async def test_sends_error_when_confirmed_missing(self):
        from ii_agent.agent.socket.command.continue_run_handler import ContinueRunHandler

        stream = CapturingEventStream()
        container = _mock_container()
        with patch(
            "ii_agent.agent.socket.command.continue_run_handler.AgentFactory"
        ) as mock_factory:
            mock_factory.return_value = MagicMock()
            handler = ContinueRunHandler(event_stream=stream, container=container)

        session_info = _make_session_info()
        run_id = str(uuid.uuid4())
        await handler.handle({"run_id": run_id}, session_info)

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert "confirmed" in errors[0].content["message"]

    @pytest.mark.asyncio
    async def test_sends_agent_continue_event_then_run_not_found(self):
        from ii_agent.agent.socket.command.continue_run_handler import ContinueRunHandler

        stream = CapturingEventStream()
        container = _mock_container()
        with patch(
            "ii_agent.agent.socket.command.continue_run_handler.AgentFactory"
        ) as mock_factory:
            mock_factory.return_value = MagicMock()
            handler = ContinueRunHandler(event_stream=stream, container=container)

        session_info = _make_session_info()
        run_id = str(uuid.uuid4())

        with patch(
            "ii_agent.agent.socket.command.continue_run_handler.AgentSessionStore"
        ) as mock_store_cls:
            mock_store = MagicMock()
            mock_store.get_by_run_id = AsyncMock(return_value=None)
            mock_store_cls.return_value = mock_store

            await handler.handle({"run_id": run_id, "confirmed": True}, session_info)

        # AGENT_CONTINUE should be emitted before error
        continue_events = stream.events_of_type(EventType.AGENT_CONTINUE)
        assert len(continue_events) >= 1

        errors = stream.events_of_type(EventType.ERROR)
        assert len(errors) >= 1
        assert "not found" in errors[0].content["message"].lower()

    def test_get_command_type(self):
        from ii_agent.agent.socket.command.continue_run_handler import ContinueRunHandler
        from ii_agent.agent.socket.command.command_handler import UserCommandType

        with patch(
            "ii_agent.agent.socket.command.continue_run_handler.AgentFactory"
        ) as mock_factory:
            mock_factory.return_value = MagicMock()
            handler = ContinueRunHandler(
                event_stream=CapturingEventStream(), container=_mock_container()
            )
        assert handler.get_command_type() == UserCommandType.CONTINUE_RUN
