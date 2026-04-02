from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.core.config.llm_config import APITypes
from ii_agent.files.exceptions import FileSizeLimitExceededError
from ii_agent.files.service import FileService
from ii_agent.sessions.service import SessionService
from ii_agent.settings.llm.schemas import ModelSettingCreate
from ii_agent.settings.llm.service import LLMSettingService

pytestmark = pytest.mark.smoke


class SessionRepo:
    def __init__(self):
        self.sessions = {}

    async def create(self, db, session):
        from datetime import datetime, timezone

        if session.created_at is None:
            session.created_at = datetime.now(timezone.utc)
        if session.updated_at is None:
            session.updated_at = datetime.now(timezone.utc)
        if session.is_public is None:
            session.is_public = False
        self.sessions[session.id] = session
        return session

    async def get_by_id(self, db, session_id):
        return self.sessions.get(session_id)


class FileRepo:
    async def create(self, db, **kwargs):
        return SimpleNamespace(**kwargs)


class LLMRepo:
    def __init__(self):
        self.by_model = {}

    async def get_by_model_and_user(self, db, model, user_id):
        return self.by_model.get((model, user_id))

    async def create(self, db, setting):
        self.by_model[(setting.model, setting.user_id)] = setting
        return setting

    async def update(self, db, setting):
        self.by_model[(setting.model, setting.user_id)] = setting
        return setting


@pytest.mark.asyncio
async def test_session_and_file_sanity(settings_factory, in_memory_storage):
    session_service = SessionService(
        session_repo=SessionRepo(),
        event_repo=SimpleNamespace(),
        agent_run_service=SimpleNamespace(),
        file_store=SimpleNamespace(get_download_signed_url=lambda path: f"signed:{path}"),
        sandbox_repo=SimpleNamespace(),
        config=settings_factory(),
    )

    session = await session_service.create_new_session(
        db=None,
        session_uuid=uuid4(),
        user_id="u1",
        api_version="v1",
    )

    file_service = FileService(
        file_repo=FileRepo(),
        session_repo=SimpleNamespace(),
        file_store=in_memory_storage,
        media_store=None,
        config=settings_factory(),
    )

    upload = await file_service.generate_upload_url(
        db=None,
        user_id="u1",
        file_name="a.txt",
        content_type="text/plain",
        file_size=3,
        upload_storage=in_memory_storage,
        max_file_size=10,
    )

    assert upload.id

    with pytest.raises(FileSizeLimitExceededError):
        await file_service.generate_upload_url(
            db=None,
            user_id="u1",
            file_name="big.txt",
            content_type="text/plain",
            file_size=100,
            upload_storage=in_memory_storage,
            max_file_size=10,
        )

    assert str(session.id)


@pytest.mark.asyncio
async def test_llm_setting_create_and_read_sanity(settings_factory, monkeypatch):
    monkeypatch.setattr("ii_agent.settings.llm.service.encryption_manager.encrypt", lambda value: f"enc:{value}")

    service = LLMSettingService(
        repo=LLMRepo(),
        config=settings_factory(),
        session_repo=SimpleNamespace(get_by_id=lambda *args, **kwargs: None),
    )

    created = await service.create_model_settings(
        db=None,
        user_id="u1",
        setting_model_in=ModelSettingCreate(
            model="gpt-4o",
            api_type=APITypes.OPENAI,
            api_key="secret",
        ),
    )

    assert created.model == "gpt-4o"
    assert created.has_api_key is True
