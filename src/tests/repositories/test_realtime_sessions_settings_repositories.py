from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agent.events.models import Event, EventType, RealtimeEvent
from ii_agent.agent.events.repository import EventRepository
from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.wishlist.models import SessionWishlist
from ii_agent.sessions.wishlist.repository import WishlistRepository
from ii_agent.settings.llm.models import LLMSetting
from ii_agent.settings.llm.repository import LLMSettingRepository
from ii_agent.settings.mcp.models import MCPSetting
from ii_agent.settings.mcp.repository import MCPSettingRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_event_repository_save_filter_and_latest(
    db_session: AsyncSession,
    session_factory,
) -> None:
    session = await session_factory()
    repo = EventRepository()
    session_uuid = uuid.UUID(session.id)

    await repo.save(
        db_session,
        session_uuid,
        RealtimeEvent(
            type=EventType.AGENT_RESPONSE,
            session_id=session_uuid,
            content={"text": "one"},
        ),
    )
    await repo.save(
        db_session,
        session_uuid,
        RealtimeEvent(
            type=EventType.SYSTEM,
            session_id=session_uuid,
            content={"text": "two"},
        ),
    )

    by_session = await repo.get_by_session(db_session, session.id)
    filtered = await repo.get_by_session_filtered(
        db_session, session.id, excluded_types=[EventType.SYSTEM.value]
    )
    unfiltered = await repo.get_by_session_filtered(db_session, session.id)
    latest_agent = await repo.get_latest_by_type(
        db_session, session.id, EventType.AGENT_RESPONSE.value
    )

    assert len(by_session) == 2
    assert len(filtered) == 1
    assert len(unfiltered) == 2
    assert latest_agent is not None
    assert latest_agent.type == EventType.AGENT_RESPONSE.value

    raw_event = Event(
        id=str(uuid.uuid4()),
        session_id=session.id,
        type="custom",
        content={"ok": True},
    )
    created = await repo.create(db_session, raw_event)
    assert created.type == "custom"


async def test_session_repository_filters_pagination_and_projections(
    db_session: AsyncSession,
    user_factory,
) -> None:
    repo = SessionRepository()
    user = await user_factory()
    other_user = await user_factory()

    llm_setting = LLMSetting(
        id=str(uuid.uuid4()),
        user_id=user.id,
        model="gpt-5",
        api_type="openai",
    )
    db_session.add(llm_setting)
    await db_session.flush()

    session_chat = Session(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name="Alpha Chat",
        is_public=True,
        agent_type="chat",
        llm_setting_id=llm_setting.id,
        sandbox_id="sandbox-1",
    )
    session_agent = Session(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name="Beta Agent",
        is_public=False,
        agent_type="builder",
    )
    session_deleted = Session(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name="Deleted",
        deleted_at=datetime.now(timezone.utc),
    )
    other_user_session = Session(
        id=str(uuid.uuid4()),
        user_id=other_user.id,
        name="Other User",
        is_public=True,
    )
    db_session.add_all([session_chat, session_agent, session_deleted, other_user_session])
    await db_session.flush()

    assert await repo.get_by_id(db_session, session_chat.id) is not None
    assert await repo.get_by_id_with_project(db_session, session_chat.id) is not None
    assert await repo.get_by_id_and_user(db_session, session_chat.id, user.id) is not None
    assert await repo.get_public_by_id(db_session, session_chat.id) is not None
    assert await repo.get_public_by_id(db_session, session_agent.id) is None
    assert await repo.get_user_id(db_session, session_chat.id) == user.id
    assert await repo.get_llm_setting_id(db_session, session_chat.id) == llm_setting.id
    assert await repo.get_sandbox_id(db_session, session_chat.id) == "sandbox-1"

    filtered_sessions, total = await repo.get_user_sessions(
        db_session,
        user_id=user.id,
        search_term="Alpha",
        page=1,
        per_page=10,
        public_only=True,
        session_type="chat",
    )
    assert total == 1
    assert [s.id for s in filtered_sessions] == [session_chat.id]

    agent_sessions, agent_total = await repo.get_user_sessions(
        db_session,
        user_id=user.id,
        session_type="agent",
    )
    assert agent_total == 1
    assert [s.id for s in agent_sessions] == [session_agent.id]

    all_sessions, all_total = await repo.get_user_sessions(
        db_session,
        user_id=user.id,
        session_type=None,
    )
    assert all_total == 2
    assert {s.id for s in all_sessions} == {session_chat.id, session_agent.id}

    by_ids_user = await repo.get_non_deleted_by_ids_and_user(
        db_session,
        [session_chat.id, session_deleted.id, other_user_session.id],
        user.id,
    )
    by_ids = await repo.get_non_deleted_by_ids(
        db_session, [session_chat.id, session_deleted.id]
    )
    assert [s.id for s in by_ids_user] == [session_chat.id]
    assert [s.id for s in by_ids] == [session_chat.id]
    assert await repo.get_user_id(db_session, "missing-session-id") is None
    assert await repo.get_non_deleted_by_ids(db_session, []) == []


async def test_session_repository_get_by_workspace_query(
    db_session: AsyncSession,
    session_factory,
) -> None:
    repo = SessionRepository()
    session = await session_factory()
    if not hasattr(Session, "workspace_dir"):
        Session.workspace_dir = Session.id  # type: ignore[attr-defined]

    found = await repo.get_by_workspace(db_session, session.id)
    assert found is not None
    assert found.id == session.id
    assert await repo.get_by_workspace(db_session, "missing-workspace-dir") is None


async def test_wishlist_repository_crud_uniqueness_and_delete(
    db_session: AsyncSession,
    user_factory,
    session_factory,
) -> None:
    repo = WishlistRepository()
    user = await user_factory()
    session = await session_factory()

    item = SessionWishlist(
        id=str(uuid.uuid4()),
        user_id=user.id,
        session_id=session.id,
    )
    created = await repo.create(db_session, item)
    assert created.id == item.id

    fetched = await repo.get_by_user_and_session(db_session, user.id, session.id)
    listed = await repo.get_user_wishlists(db_session, user.id)
    assert fetched is not None
    assert len(listed) == 1

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await repo.create(
                db_session,
                SessionWishlist(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    session_id=session.id,
                ),
            )

    deleted = await repo.delete_by_user_and_session(db_session, user.id, session.id)
    assert deleted is True
    assert await repo.get_by_user_and_session(db_session, user.id, session.id) is None


async def test_llm_setting_repository_lookup_filter_and_delete(
    db_session: AsyncSession,
    user_factory,
) -> None:
    repo = LLMSettingRepository()
    user = await user_factory()

    first = LLMSetting(
        id=str(uuid.uuid4()),
        user_id=user.id,
        model="gpt-5",
        api_type="openai",
    )
    second = LLMSetting(
        id=str(uuid.uuid4()),
        user_id=user.id,
        model="gemini-3-pro-preview",
        api_type="google",
    )
    db_session.add_all([first, second])
    await db_session.flush()

    assert await repo.get_by_id_and_user(db_session, first.id, user.id) is not None
    assert await repo.get_by_model_and_user(db_session, "gpt-5", user.id) is not None
    assert len(await repo.list_by_user(db_session, user.id)) == 2
    assert len(await repo.list_by_user(db_session, user.id, api_type="google")) == 1

    await repo.delete(db_session, first)
    assert await repo.get_by_id_and_user(db_session, first.id, user.id) is None


async def test_mcp_setting_repository_list_filters_and_delete(
    db_session: AsyncSession,
    user_factory,
) -> None:
    repo = MCPSettingRepository()
    user = await user_factory()

    active_no_metadata = MCPSetting(
        id=str(uuid.uuid4()),
        user_id=user.id,
        mcp_config={"server": "sse://one"},
        mcp_metadata=None,
        is_active=True,
    )
    inactive_with_metadata = MCPSetting(
        id=str(uuid.uuid4()),
        user_id=user.id,
        mcp_config={"server": "sse://two"},
        mcp_metadata={"tool_type": "codex"},
        is_active=False,
    )
    inactive_empty_metadata = MCPSetting(
        id=str(uuid.uuid4()),
        user_id=user.id,
        mcp_config={"server": "sse://three"},
        mcp_metadata={},
        is_active=False,
    )
    db_session.add_all(
        [active_no_metadata, inactive_with_metadata, inactive_empty_metadata]
    )
    await db_session.flush()

    assert (
        await repo.get_by_id_and_user(db_session, active_no_metadata.id, user.id)
    ) is not None
    assert len(await repo.list_by_user(db_session, user.id)) == 3
    assert len(await repo.list_active_by_user(db_session, user.id)) == 1
    assert (
        await repo.get_by_user_and_tool_type(db_session, user.id, "codex")
        == inactive_with_metadata
    )
    assert await repo.get_by_user_and_tool_type(db_session, user.id, "claude") is None
    no_metadata = await repo.list_by_user(db_session, user.id, no_metadata=True)
    assert {setting.id for setting in no_metadata} == {
        active_no_metadata.id,
        inactive_empty_metadata.id,
    }

    await repo.delete(db_session, inactive_with_metadata)
    assert (
        await repo.get_by_id_and_user(db_session, inactive_with_metadata.id, user.id)
    ) is None
