"""Deep unit tests for ii_agent.sessions.service covering remaining branches."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.schemas import SessionEventDetail, SessionInfo
from ii_agent.sessions.service import SessionService


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def _make_session_ns(**kwargs):
    """Create a SimpleNamespace that mimics a Session ORM model."""
    defaults = dict(
        id=str(uuid.uuid4()),
        user_id="u-1",
        name="Test Session",
        status="active",
        sandbox_id=None,
        agent_type=None,
        app_kind="agent",
        is_public=False,
        public_url=None,
        api_version="v0",
        session_metadata={},
        last_message_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_deleted=False,
        project=None,
        model_setting_id=None,
    )
    defaults.update(kwargs)
    ns = SimpleNamespace(**defaults)
    ns.get_workspace_dir = lambda: f"/workspace/{ns.id}"
    return ns


class FakeSessionRepo:
    def __init__(self):
        self.sessions: dict = {}
        self.updates = []

    async def get_by_id(self, db, session_id):
        return self.sessions.get(str(session_id))

    async def get_by_id_with_project(self, db, session_id):
        return self.sessions.get(str(session_id))

    async def get_by_id_and_user(self, db, session_id, user_id):
        s = self.sessions.get(str(session_id))
        if s and s.user_id == user_id and not s.is_deleted:
            return s
        return None

    async def get_public_by_id(self, db, session_id):
        s = self.sessions.get(str(session_id))
        if s and s.is_public:
            return s
        return None

    async def create(self, db, session):
        self.sessions[str(session.id)] = session
        return session

    async def update(self, db, session):
        self.updates.append(session)
        return session

    async def get_by_workspace(self, db, workspace_dir):
        return None

    async def get_user_id(self, db, session_id):
        s = self.sessions.get(str(session_id))
        return s.user_id if s else None

    async def get_llm_setting_id(self, db, session_id):
        return None

    async def get_user_sessions(
        self, db, user_id, search_term, page, per_page, public_only, session_type
    ):
        matching = [s for s in self.sessions.values() if s.user_id == user_id and not s.is_deleted]
        return matching, len(matching)

    async def get_non_deleted_by_ids_and_user(self, db, session_ids, user_id):
        result = []
        for sid in session_ids:
            s = self.sessions.get(str(sid))
            if s and s.user_id == user_id and not s.is_deleted:
                result.append(s)
        return result

    async def get_non_deleted_by_ids(self, db, session_ids):
        return [s for sid in session_ids for s in [self.sessions.get(str(sid))] if s]


class FakeEventRepo:
    def __init__(self):
        self.events = []
        self.latest_by_type = {}
        self.created_events = []

    async def get_by_session_filtered(self, db, session_id, excluded_types):
        return [
            e for e in self.events if e.session_id == session_id and e.type not in excluded_types
        ]

    async def get_latest_by_type(self, db, session_id, event_type):
        return self.latest_by_type.get((session_id, event_type))

    async def create(self, db, event):
        self.created_events.append(event)
        self.events.append(event)
        return event


class FakeRunTaskService:
    def __init__(self):
        self.running_session_ids = []

    async def get_all_running_session_ids(self, db):
        return self.running_session_ids

    async def find_active_by_session(self, db, session_id):
        return None


class FakeFileStore:
    async def signed_download_url(self, path: str) -> str:
        return f"signed://{path}"


class FakeCache:
    def __init__(self) -> None:
        self.evicted_keys: list[str] = []

    async def evict(self, key: str) -> None:
        self.evicted_keys.append(key)


def _make_service(**kwargs) -> SessionService:
    config = SimpleNamespace(
        workspace_path="/tmp/workspace",
        workspace_upload_subpath="uploads",
    )
    defaults = dict(
        session_repo=FakeSessionRepo(),
        event_repo=FakeEventRepo(),
        run_task_service=FakeRunTaskService(),
        file_store=FakeFileStore(),
        sandbox_repo=SimpleNamespace(),
        cache=FakeCache(),
        config=config,
    )
    defaults.update(kwargs)
    return SessionService(**defaults)


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_creates_session_with_given_id(self):
        svc = _make_service()
        session_uuid = uuid.uuid4()
        # Patch Session model import to avoid SQLAlchemy model initialization
        with patch("ii_agent.sessions.service.Session") as MockSession:
            mock_session = _make_session_ns(id=str(session_uuid))
            MockSession.return_value = mock_session
            session = await svc.create_session(None, session_uuid, "u-1", "/path/state")
        assert str(session.id) == str(session_uuid)
        assert session.user_id == "u-1"

    @pytest.mark.asyncio
    async def test_creates_session_with_name(self):
        svc = _make_service()
        session_uuid = uuid.uuid4()
        with patch("ii_agent.sessions.service.Session") as MockSession:
            mock_session = _make_session_ns(id=str(session_uuid), name="My Session")
            MockSession.return_value = mock_session
            session = await svc.create_session(
                None, session_uuid, "u-1", "/path/state", name="My Session"
            )
        assert session.name == "My Session"


# ---------------------------------------------------------------------------
# get_session_by_id
# ---------------------------------------------------------------------------


class TestGetSessionById:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        svc = _make_service()
        result = await svc.get_session_by_id(None, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_session_when_found(self):
        svc = _make_service()
        session_uuid = uuid.uuid4()
        session = _make_session_ns(id=str(session_uuid))
        svc._session_repo.sessions[str(session_uuid)] = session
        result = await svc.get_session_by_id(None, session_uuid)
        assert result is session


# ---------------------------------------------------------------------------
# get_session_details
# ---------------------------------------------------------------------------


class TestGetSessionDetails:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        svc = _make_service()
        result = await svc.get_session_details(None, "unknown-id", "u-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_session_info_when_found(self):
        svc = _make_service()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid)
        svc._session_repo.sessions[sid] = session

        with patch("ii_agent.sessions.service.sa_inspect") as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = {"project"}
            mock_inspect.return_value = mock_state
            result = await svc.get_session_details(None, sid, "u-1")

        assert result is not None
        assert isinstance(result, SessionInfo)
        assert str(result.id) == sid
        assert result.user_id == "u-1"


# ---------------------------------------------------------------------------
# get_public_session_details
# ---------------------------------------------------------------------------


class TestGetPublicSessionDetails:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_public(self):
        svc = _make_service()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid, is_public=False)
        svc._session_repo.sessions[sid] = session
        result = await svc.get_public_session_details(None, sid)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_session_info_for_public_session(self):
        svc = _make_service()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid, is_public=True)
        svc._session_repo.sessions[sid] = session
        result = await svc.get_public_session_details(None, sid)
        assert result is not None
        assert isinstance(result, SessionInfo)
        assert str(result.id) == sid


# ---------------------------------------------------------------------------
# soft_delete_session
# ---------------------------------------------------------------------------


class TestSoftDeleteSession:
    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        svc = _make_service()
        with pytest.raises(SessionNotFoundError):
            await svc.soft_delete_session(None, "no-session", "u-1")

    @pytest.mark.asyncio
    async def test_sets_is_deleted(self):
        svc = _make_service()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid)
        svc._session_repo.sessions[sid] = session
        await svc.soft_delete_session(None, sid, "u-1")
        assert session.is_deleted is True


# ---------------------------------------------------------------------------
# bulk_soft_delete_sessions
# ---------------------------------------------------------------------------


class TestBulkSoftDeleteSessions:
    @pytest.mark.asyncio
    async def test_returns_deleted_and_failed_ids(self):
        svc = _make_service()
        sid1 = str(uuid.uuid4())
        sid2 = str(uuid.uuid4())
        session1 = _make_session_ns(id=sid1)
        svc._session_repo.sessions[sid1] = session1
        # sid2 doesn't exist

        db = AsyncMock()
        deleted, failed = await svc.bulk_soft_delete_sessions(db, [sid1, sid2], "u-1")
        assert sid1 in deleted
        assert sid2 in failed
        assert session1.is_deleted is True

    @pytest.mark.asyncio
    async def test_all_found_marks_all_deleted(self):
        svc = _make_service()
        ids = [str(uuid.uuid4()) for _ in range(3)]
        for sid in ids:
            svc._session_repo.sessions[sid] = _make_session_ns(id=sid)

        db = AsyncMock()
        deleted, failed = await svc.bulk_soft_delete_sessions(db, ids, "u-1")
        assert len(deleted) == 3
        assert len(failed) == 0


# ---------------------------------------------------------------------------
# set_session_public
# ---------------------------------------------------------------------------


class TestSetSessionPublic:
    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        svc = _make_service()
        result = await svc.set_session_public(None, "no-session", "u-1", True)
        assert result is False

    @pytest.mark.asyncio
    async def test_sets_public_true(self):
        svc = _make_service()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid, is_public=False)
        svc._session_repo.sessions[sid] = session
        result = await svc.set_session_public(None, sid, "u-1", True)
        assert result is True
        assert session.is_public is True

    @pytest.mark.asyncio
    async def test_sets_public_false(self):
        svc = _make_service()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid, is_public=True)
        svc._session_repo.sessions[sid] = session
        result = await svc.set_session_public(None, sid, "u-1", False)
        assert result is True
        assert session.is_public is False


# ---------------------------------------------------------------------------
# get_sessions_with_running_status
# ---------------------------------------------------------------------------


class TestGetSessionsWithRunningStatus:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_running_sessions(self):
        svc = _make_service()
        result = await svc.get_sessions_with_running_status(None)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_sessions_for_running_ids(self):
        svc = _make_service()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid)
        svc._session_repo.sessions[sid] = session
        svc._run_task_service.running_session_ids = [sid]
        result = await svc.get_sessions_with_running_status(None)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_session_running_status(self):
        svc = _make_service()
        result = await svc.get_session_running_status(None, "s-1")
        assert result is None


# ---------------------------------------------------------------------------
# get_user_sessions
# ---------------------------------------------------------------------------


class TestGetUserSessions:
    @pytest.mark.asyncio
    async def test_returns_sessions_and_count(self):
        svc = _make_service()
        for _ in range(3):
            sid = str(uuid.uuid4())
            svc._session_repo.sessions[sid] = _make_session_ns(id=sid)

        with patch("ii_agent.sessions.service.sa_inspect") as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = {"project"}
            mock_inspect.return_value = mock_state
            sessions, total = await svc.get_user_sessions(None, "u-1")

        assert total == 3
        assert len(sessions) == 3
        assert isinstance(sessions[0], SessionInfo)


# ---------------------------------------------------------------------------
# get_session_events_with_details
# ---------------------------------------------------------------------------


class TestGetSessionEventsWithDetails:
    @pytest.mark.asyncio
    async def test_enriches_file_url_events(self):
        event_repo = FakeEventRepo()
        event_repo.events = [
            SimpleNamespace(
                id="e1",
                session_id="s-1",
                created_at=datetime.now(timezone.utc),
                event_type="agent.tool.result",
                content={
                    "result": {
                        "type": "file_url",
                        "file_storage_path": "users/u1/file.txt",
                        "url": "old-url",
                    }
                },
                run_id=None,
            )
        ]
        svc = _make_service(event_repo=event_repo)
        events = await svc.get_session_events_with_details(None, "s-1")
        assert len(events) == 1
        assert isinstance(events[0], SessionEventDetail)
        assert events[0].content["result"]["url"] == "signed://users/u1/file.txt"

    @pytest.mark.asyncio
    async def test_non_file_url_events_not_modified(self):
        event_repo = FakeEventRepo()
        event_repo.events = [
            SimpleNamespace(
                id="e2",
                session_id="s-1",
                created_at=datetime.now(timezone.utc),
                event_type="agent.tool.result",
                content={"result": {"type": "text", "value": "hello"}},
                run_id=None,
            )
        ]
        svc = _make_service(event_repo=event_repo)
        events = await svc.get_session_events_with_details(None, "s-1")
        assert isinstance(events[0], SessionEventDetail)
        assert events[0].content["result"]["value"] == "hello"


# ---------------------------------------------------------------------------
# update_session_plan
# ---------------------------------------------------------------------------


class TestUpdateSessionPlan:
    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        svc = _make_service()
        with pytest.raises(SessionNotFoundError):
            await svc.update_session_plan(None, "no-id", "u-1", "summary", [])

    @pytest.mark.asyncio
    async def test_creates_plan_event_when_none_exists(self):
        svc = _make_service()
        db = AsyncMock()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid)
        svc._session_repo.sessions[sid] = session

        mock_event = SimpleNamespace(session_id=sid, type="plan_generated", content={})
        with patch("ii_agent.sessions.service.AgentUIEvent", return_value=mock_event):
            await svc.update_session_plan(
                db, sid, "u-1", "Summary", [{"title": "M1", "status": "pending"}]
            )
        assert "plan" in session.session_metadata
        assert len(svc._event_repo.created_events) == 1

    @pytest.mark.asyncio
    async def test_updates_existing_plan_event(self):
        svc = _make_service()
        db = AsyncMock()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid)
        svc._session_repo.sessions[sid] = session

        existing_event = SimpleNamespace(content={}, session_id=sid)
        svc._event_repo.latest_by_type[(sid, "plan_generated")] = existing_event

        with patch("ii_agent.sessions.service.AgentUIEvent"):
            await svc.update_session_plan(db, sid, "u-1", "New Summary", [])
        assert "summary" in existing_event.content
        # No new event should be created since one existed
        assert len(svc._event_repo.created_events) == 0

    @pytest.mark.asyncio
    async def test_fills_missing_milestone_fields(self):
        svc = _make_service()
        db = AsyncMock()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid)
        svc._session_repo.sessions[sid] = session

        milestones = [{"title": "M1", "status": "pending"}]
        mock_event = SimpleNamespace(session_id=sid, type="plan_generated", content={})
        with patch("ii_agent.sessions.service.AgentUIEvent", return_value=mock_event):
            await svc.update_session_plan(db, sid, "u-1", "Summary", milestones)
        plan = session.session_metadata.get("plan", {})
        assert plan["milestones"][0]["details"] == ""
        assert plan["milestones"][0]["dependencies"] == []

    @pytest.mark.asyncio
    async def test_merges_with_existing_metadata(self):
        svc = _make_service()
        db = AsyncMock()
        sid = str(uuid.uuid4())
        session = _make_session_ns(id=sid, session_metadata={"other_key": "other_val"})
        svc._session_repo.sessions[sid] = session

        mock_event = SimpleNamespace(session_id=sid, type="plan_generated", content={})
        with patch("ii_agent.sessions.service.AgentUIEvent", return_value=mock_event):
            await svc.update_session_plan(db, sid, "u-1", "Summary", [])
        assert session.session_metadata.get("other_key") == "other_val"
        assert "plan" in session.session_metadata


# ---------------------------------------------------------------------------
# ensure_session_exists
# ---------------------------------------------------------------------------


class TestEnsureSessionExists:
    @pytest.mark.asyncio
    async def test_returns_existing_user_id_when_session_exists(self):
        svc = _make_service()
        sid = uuid.uuid4()
        session = _make_session_ns(id=str(sid), user_id="u-existing")
        svc._session_repo.sessions[str(sid)] = session
        user_id = await svc.ensure_session_exists(None, sid)
        assert user_id == "u-existing"

    @pytest.mark.asyncio
    async def test_creates_session_when_not_exists(self):
        svc = _make_service()
        sid = uuid.uuid4()
        with patch("ii_agent.sessions.service.Session") as MockSession:
            mock_session = _make_session_ns(id=str(sid), user_id="u-new")
            MockSession.return_value = mock_session
            user_id = await svc.ensure_session_exists(None, sid, user_id="u-new")
        assert user_id == "u-new"

    @pytest.mark.asyncio
    async def test_raises_when_no_user_id_and_session_missing(self):
        svc = _make_service()
        sid = uuid.uuid4()
        from ii_agent.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            await svc.ensure_session_exists(None, sid, user_id=None)


# ---------------------------------------------------------------------------
# get_or_create_session
# ---------------------------------------------------------------------------


class TestGetOrCreateSession:
    @pytest.mark.asyncio
    async def test_raises_when_session_id_not_found(self):
        svc = _make_service()
        with pytest.raises(SessionNotFoundError):
            await svc.get_or_create_session(None, str(uuid.uuid4()), "u-1")

    @pytest.mark.asyncio
    async def test_returns_existing_session(self):
        svc = _make_service()
        sid = uuid.uuid4()
        session = _make_session_ns(id=str(sid))
        svc._session_repo.sessions[str(sid)] = session

        mock_info = SimpleNamespace(id=str(sid), user_id="u-1")

        with patch.object(svc, "get_session_by_id", return_value=mock_info):
            info = await svc.get_or_create_session(None, str(sid), "u-1")
        assert info.id == str(sid)


# ---------------------------------------------------------------------------
# _build_session_info  (replaces the deleted _session_to_dict)
# ---------------------------------------------------------------------------


class TestBuildSessionInfo:
    def test_returns_session_response(self):
        session = _make_session_ns()
        with patch("ii_agent.sessions.service.sa_inspect") as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = {"project"}
            mock_inspect.return_value = mock_state
            result = SessionService._build_session_info(session)

        assert result.user_id is not None
        assert result.is_public is not None
        assert result.token_usage is None

    def test_includes_project_id_when_loaded(self):
        session = _make_session_ns()
        with patch("ii_agent.sessions.service.sa_inspect") as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = set()  # project is loaded (not in unloaded)
            mock_inspect.return_value = mock_state
            session.project = None
            result = SessionService._build_session_info(session)
        assert result.project_id is None

    def test_null_timestamps_handled(self):
        session = _make_session_ns(
            user_id=str(uuid.uuid4()),
            created_at=None,
            updated_at=None,
            last_message_at=None,
        )
        with patch("ii_agent.sessions.service.sa_inspect") as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = {"project"}
            mock_inspect.return_value = mock_state
            result = SessionService._build_session_info(session)
        assert result.created_at == ""
        assert result.updated_at is None
        assert result.last_message_at is None

    def test_includes_workspace_dir(self):
        session = _make_session_ns(user_id=str(uuid.uuid4()))
        with patch("ii_agent.sessions.service.sa_inspect") as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = {"project"}
            mock_inspect.return_value = mock_state
            result = SessionService._build_session_info(session)
        assert session.id in result.workspace_dir

    def test_preserves_legacy_agent_type_values(self):
        session = _make_session_ns(user_id=str(uuid.uuid4()), agent_type="chat")
        with patch("ii_agent.sessions.service.sa_inspect") as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = {"project"}
            mock_inspect.return_value = mock_state
            result = SessionService._build_session_info(session)
        assert result.agent_type == "chat"
