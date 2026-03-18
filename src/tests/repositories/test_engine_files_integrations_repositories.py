from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.content.media.models import MediaTemplate
from ii_agent.core.db.repository import BaseRepository
from ii_agent.agent.runs.models import RunStatus
from ii_agent.agent.runs.repository import AgentRunTaskRepository
from ii_agent.agent.sandboxes.models import AgentSandbox
from ii_agent.agent.sandboxes.repository import SandboxRepository
from ii_agent.files.repository import FileRepository
from ii_agent.integrations.connectors.models import ComposioProfile, Connector
from ii_agent.integrations.connectors.repository import ConnectorRepository
from ii_agent.integrations.connectors.composio.repository import ComposioProfileRepository
from ii_agent.integrations.mobile.apple.models import AppleAuthStateEnum, AppleCredential
from ii_agent.integrations.mobile.apple.repository import AppleCredentialRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _MediaBaseRepository(BaseRepository[MediaTemplate]):
    model = MediaTemplate


async def test_base_repository_create_get_update_roundtrip(
    db_session: AsyncSession,
) -> None:
    repo = _MediaBaseRepository()
    template = MediaTemplate(
        id="base-template-1",
        name="Base Template",
        prompt="Base prompt",
        type="image",
    )

    created = await repo.create(db_session, template)
    fetched = await repo.get_by_id(db_session, created.id)
    assert fetched is not None
    assert fetched.name == "Base Template"

    fetched.name = "Updated Template"
    updated = await repo.update(db_session, fetched)
    assert updated.name == "Updated Template"


async def test_agent_run_task_repository_status_queries(
    db_session: AsyncSession,
    session_factory,
) -> None:
    session = await session_factory()
    repo = AgentRunTaskRepository()
    session_uuid = uuid.UUID(session.id)

    first = await repo.create(db_session, session_id=session_uuid, status=RunStatus.RUNNING)
    second = await repo.create(
        db_session,
        session_id=session_uuid,
        status=RunStatus.COMPLETED,
    )

    by_id = await repo.get_by_id(db_session, first.id)
    by_session = await repo.get_by_session_id(db_session, session_uuid)
    last_any = await repo.find_last_by_session_id(db_session, session_uuid)
    last_completed = await repo.find_last_by_session_id_and_status(
        db_session, session_uuid, RunStatus.COMPLETED
    )
    running = await repo.get_running_by_session(db_session, session.id)
    running_session_ids = await repo.get_all_running_session_ids(db_session)

    assert by_id is not None
    assert len(by_session) == 2
    assert last_any is not None
    assert last_completed is not None
    assert running is not None
    assert session.id in running_session_ids

    updated = await repo.update_status(db_session, first.id, RunStatus.PAUSED.value)
    assert updated is not None
    assert updated.status == RunStatus.PAUSED.value
    assert second.status == RunStatus.COMPLETED
    assert await repo.update_status(db_session, uuid.uuid4(), RunStatus.FAILED.value) is None


async def test_sandbox_repository_lookup_paths(
    db_session: AsyncSession,
    session_factory,
) -> None:
    session = await session_factory()
    repo = SandboxRepository()

    sandbox = AgentSandbox(
        id=uuid.uuid4(),
        provider="e2b",
        provider_sandbox_id="provider-123",
        session_id=session.id,
        status="running",
    )
    db_session.add(sandbox)
    await db_session.flush()

    by_id = await repo.get_by_id(db_session, sandbox.id)
    by_session = await repo.get_by_session_id(db_session, session.id)
    by_provider = await repo.get_by_provider_id(db_session, "provider-123")

    assert by_id is not None
    assert by_session is not None
    assert by_provider is not None
    assert by_provider.id == sandbox.id


async def test_file_repository_filters_pagination_and_update(
    db_session: AsyncSession,
    user_factory,
    session_factory,
) -> None:
    repo = FileRepository()
    user = await user_factory()
    session = await session_factory(user_id=user.id)

    image_file = await repo.create(
        db_session,
        file_id="file-img",
        user_id=user.id,
        file_name="a.png",
        file_size=10,
        storage_path="/files/a.png",
        content_type="image/png",
        session_id=session.id,
    )
    await repo.create(
        db_session,
        file_id="file-no-type",
        user_id=user.id,
        file_name="b.bin",
        file_size=20,
        storage_path="/files/b.bin",
        content_type=None,
    )
    await repo.create(
        db_session,
        file_id="file-text",
        user_id=user.id,
        file_name="c.txt",
        file_size=30,
        storage_path="/files/c.txt",
        content_type="text/plain",
    )

    assert await repo.get_by_id_and_user(db_session, "file-img", user.id) is not None
    assert await repo.get_by_session_and_id(db_session, session.id, "file-img") is not None

    by_paths = await repo.get_by_user_and_paths(
        db_session, user.id, ["/files/a.png", "/files/none.txt"]
    )
    assert len(by_paths) == 1
    assert by_paths[0].id == image_file.id

    images = await repo.get_user_images(db_session, user.id, limit=10, offset=0)
    image_count = await repo.count_user_images(db_session, user.id)
    assert len(images) == 2
    assert image_count == 2

    by_ids = await repo.get_by_ids(db_session, ["file-img", "file-text"])
    empty_ids = await repo.get_by_ids(db_session, [])
    assert len(by_ids) == 2
    assert empty_ids == []

    updated = await repo.update_session_id(db_session, "file-text", session.id)
    assert updated is True
    assert await repo.get_by_session_and_id(db_session, session.id, "file-text") is not None
    assert await repo.update_session_id(db_session, "missing-file", session.id) is False

    in_session = await repo.get_by_session_id(db_session, session.id)
    assert {upload.id for upload in in_session} == {"file-img", "file-text"}


async def test_connector_repository_queries_and_uniqueness(
    db_session: AsyncSession,
    user_factory,
) -> None:
    repo = ConnectorRepository()
    user = await user_factory()

    connector = Connector(
        id=str(uuid.uuid4()),
        user_id=user.id,
        connector_type="github",
        access_token="token-1",
        refresh_token="refresh-1",
    )
    await repo.create(db_session, connector)

    by_user = await repo.get_by_user(db_session, user.id)
    by_type = await repo.get_by_user_and_type(db_session, user.id, "github")
    by_token = await repo.get_by_token_and_type(db_session, "token-1", "github")

    assert len(by_user) == 1
    assert by_type is not None
    assert by_token is not None

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await repo.create(
                db_session,
                Connector(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    connector_type="github",
                    access_token="token-2",
                ),
            )


async def test_composio_profile_repository_full_lifecycle(
    db_session: AsyncSession,
    user_factory,
) -> None:
    repo = ComposioProfileRepository()
    user = await user_factory()

    pending = ComposioProfile(
        id=str(uuid.uuid4()),
        user_id=user.id,
        profile_name="Slack",
        toolkit_slug="slack",
        toolkit_name="Slack",
        auth_config_id="auth-1",
        connected_account_id="acct-1",
        mcp_server_id="mcp-1",
        composio_user_id="comp-user",
        encrypted_mcp_url="enc://1",
        status="pending",
        enabled_tools=[],
    )
    enabled = ComposioProfile(
        id=str(uuid.uuid4()),
        user_id=user.id,
        profile_name="Slack Team",
        toolkit_slug="slack",
        toolkit_name="Slack",
        auth_config_id="auth-2",
        connected_account_id="acct-2",
        mcp_server_id="mcp-1",
        composio_user_id="comp-user",
        encrypted_mcp_url="enc://2",
        status="enable",
        enabled_tools=["messages.read"],
    )
    await repo.create(db_session, pending)
    await repo.create(db_session, enabled)

    assert await repo.get_by_id_and_user(db_session, pending.id, user.id) is not None
    assert len(await repo.get_profiles_by_user(db_session, user.id)) == 2
    assert len(await repo.get_profiles_by_user(db_session, user.id, "slack")) == 2
    assert len(await repo.get_enabled_profiles_by_user(db_session, user.id)) == 1
    assert await repo.get_user_mcp_server_id(db_session, user.id) == "mcp-1"
    assert len(await repo.get_profiles_by_mcp_server(db_session, user.id, "mcp-1")) == 2
    assert await repo.count_profiles_with_name_prefix(db_session, user.id, "Slack") == 2
    assert await repo.profile_name_exists(db_session, user.id, "Slack") is True
    assert await repo.find_pending_profile(db_session, user.id, "slack") is not None
    assert (
        await repo.find_profile_by_connected_account(db_session, user.id, "slack", "acct-2")
    ) is not None
    assert await repo.check_existing_auth_config(db_session, "slack") in {"auth-1", "auth-2"}

    assert await repo.update_status(db_session, pending.id, user.id, "enable") is True
    assert await repo.update_enabled_tools(db_session, pending.id, ["channels.read"]) is True
    assert await repo.delete(db_session, pending.id, user.id) is True
    assert await repo.delete_by_id(db_session, enabled.id) is True


async def test_apple_credential_repository_latest_and_authenticated(
    db_session: AsyncSession,
    user_factory,
) -> None:
    repo = AppleCredentialRepository()
    user = await user_factory()

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            AppleCredential(
                id=str(uuid.uuid4()),
                user_id=user.id,
                apple_id="pending",
                auth_state=AppleAuthStateEnum.PENDING_LOGIN.value,
                updated_at=now + timedelta(minutes=1),
            ),
            AppleCredential(
                id=str(uuid.uuid4()),
                user_id=user.id,
                apple_id="real@apple.com",
                auth_state=AppleAuthStateEnum.AUTHENTICATED.value,
                updated_at=now,
            ),
            AppleCredential(
                id=str(uuid.uuid4()),
                user_id=user.id,
                apple_id="real2@apple.com",
                auth_state=AppleAuthStateEnum.AUTHENTICATED.value,
                updated_at=now + timedelta(minutes=2),
            ),
        ]
    )
    await db_session.flush()

    exact = await repo.get_by_user_and_apple_id(db_session, user.id, "real@apple.com")
    latest = await repo.get_latest_by_user(db_session, user.id)
    latest_auth = await repo.get_latest_authenticated_by_user(db_session, user.id)

    assert exact is not None
    assert latest is not None
    assert latest.apple_id != "pending"
    assert latest_auth is not None
    assert latest_auth.apple_id == "real2@apple.com"
