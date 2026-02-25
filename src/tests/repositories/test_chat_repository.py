from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.models import ChatMessage
from ii_agent.chat.repository import ChatMessageRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_chat_message_repository_crud_pagination_and_mark_incomplete(
    db_session: AsyncSession,
    session_factory,
) -> None:
    repo = ChatMessageRepository()
    session = await session_factory()
    now = datetime.now(timezone.utc)

    msg1 = ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="user",
        content={"text": "hello"},
        created_at=now,
        updated_at=now,
    )
    msg2 = ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="assistant",
        content={"text": "hi"},
        parent_message_id=msg1.id,
        is_finished=True,
        created_at=now + timedelta(seconds=1),
        updated_at=now + timedelta(seconds=1),
    )
    msg3 = ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="assistant",
        content={"text": "how can I help"},
        created_at=now + timedelta(seconds=2),
        updated_at=now + timedelta(seconds=2),
    )

    await repo.create(db_session, msg1)
    await repo.create(db_session, msg2)
    await repo.create(db_session, msg3)

    listed = await repo.list_by_session(db_session, session.id, limit=10)
    after_id = await repo.list_after_id(db_session, session.id, msg1.id, limit=10)
    after_timestamp = await repo.list_after_timestamp(
        db_session, session.id, now, limit=10
    )
    assert [m.id for m in listed] == [msg1.id, msg2.id, msg3.id]
    assert [m.id for m in after_id] == [msg2.id, msg3.id]
    assert [m.id for m in after_timestamp] == [msg2.id, msg3.id]

    await repo.mark_incomplete(db_session, msg1.id)
    reloaded = await db_session.get(ChatMessage, msg2.id)
    assert reloaded is not None
    assert reloaded.is_finished is False

    history, has_more = await repo.get_history(db_session, session.id, limit=2)
    assert has_more is True
    assert [m.id for m in history] == [msg2.id, msg3.id]

    last = await repo.get_last_by_session(db_session, session.id)
    recent = await repo.get_recent(db_session, session.id, limit=2)
    assert last is not None
    assert last.id == msg3.id
    assert [m.id for m in recent] == [msg2.id, msg3.id]

    deleted_count = await repo.delete_by_session(db_session, session.id)
    assert deleted_count == 3
    assert await repo.list_by_session(db_session, session.id, limit=10) == []


async def test_chat_message_repository_not_found_and_error_branches(
    db_session: AsyncSession,
    session_factory,
) -> None:
    repo = ChatMessageRepository()
    session = await session_factory()
    now = datetime.now(timezone.utc)

    first = ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="user",
        content={"text": "first"},
        created_at=now,
        updated_at=now,
    )
    second = ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="assistant",
        content={"text": "second"},
        created_at=now + timedelta(seconds=1),
        updated_at=now + timedelta(seconds=1),
    )
    await repo.create(db_session, first)
    await repo.create(db_session, second)

    fallback_after_missing_id = await repo.list_after_id(
        db_session,
        session.id,
        uuid.uuid4(),
        limit=10,
    )
    assert [m.id for m in fallback_after_missing_id] == [first.id, second.id]

    history_before_missing, has_more_missing = await repo.get_history(
        db_session,
        session.id,
        limit=10,
        before=uuid.uuid4(),
    )
    assert has_more_missing is False
    assert [m.id for m in history_before_missing] == [first.id, second.id]

    history_before_second, has_more_before_second = await repo.get_history(
        db_session,
        session.id,
        limit=10,
        before=second.id,
    )
    assert has_more_before_second is False
    assert [m.id for m in history_before_second] == [first.id]

    empty_session = await session_factory()
    assert await repo.get_last_by_session(db_session, empty_session.id) is None
    assert await repo.get_recent(db_session, empty_session.id, limit=5) == []

    with patch.object(db_session, "execute", side_effect=RuntimeError("boom")):
        await repo.mark_incomplete(db_session, first.id)
