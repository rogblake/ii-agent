from types import SimpleNamespace

import pytest

from ii_agent.content.slides.schemas import SlideWriteRequest
from ii_agent.content.slides.service import SlideService


class FakeSlideRepo:
    def __init__(self):
        self.upserts = []
        self.existing_slide = None

    async def upsert_slide(self, db, **kwargs):
        self.upserts.append(kwargs)
        return "slide-id"

    async def get_by_session_and_presentation_and_number(
        self, db, session_id, presentation_name, slide_number
    ):
        return self.existing_slide


class FakeSessionRepo:
    def __init__(self, session_exists=True):
        self.session_exists = session_exists

    async def get_by_id_and_user(self, db, session_id, user_id):
        return object() if self.session_exists else None

    async def get_public_by_id(self, db, session_id):
        return object() if self.session_exists else None


@pytest.mark.asyncio
async def test_execute_slide_write_denies_unauthorized_session(settings_factory):
    service = SlideService(
        slide_repo=FakeSlideRepo(),
        session_repo=FakeSessionRepo(session_exists=False),
        config=settings_factory(),
    )

    response = await service.execute_slide_write(
        db=None,
        write_request=SlideWriteRequest(
            presentation_name="Deck",
            slide_number=1,
            title="Intro",
            content="Hello",
        ),
        session_id="s1",
        user_id="u1",
    )

    assert response.success is False
    assert response.error_code == "SESSION_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_execute_slide_write_success_path(settings_factory):
    slide_repo = FakeSlideRepo()
    service = SlideService(
        slide_repo=slide_repo,
        session_repo=FakeSessionRepo(session_exists=True),
        config=settings_factory(),
    )

    response = await service.execute_slide_write(
        db=None,
        write_request=SlideWriteRequest(
            presentation_name="Deck",
            slide_number=2,
            title="Agenda",
            content="Items",
        ),
        session_id="s1",
        user_id="u1",
    )

    assert response.success is True
    assert len(slide_repo.upserts) == 1
    assert slide_repo.upserts[0]["slide_number"] == 2


@pytest.mark.asyncio
async def test_persist_tool_slide_result_preserves_existing_title(settings_factory):
    slide_repo = FakeSlideRepo()
    slide_repo.existing_slide = SimpleNamespace(slide_title="Existing Title")
    service = SlideService(
        slide_repo=slide_repo,
        session_repo=FakeSessionRepo(session_exists=True),
        config=settings_factory(),
    )

    slide_id = await service.persist_tool_slide_result(
        db=None,
        session_id="s1",
        presentation_name="Deck",
        slide_number=4,
        slide_title=None,
        slide_content="<html>Updated</html>",
        tool_name="SlideEdit",
    )

    assert slide_id == "slide-id"
    assert slide_repo.upserts[0]["slide_title"] == "Existing Title"


@pytest.mark.asyncio
async def test_persist_tool_slide_result_uses_fallback_title(settings_factory):
    slide_repo = FakeSlideRepo()
    service = SlideService(
        slide_repo=slide_repo,
        session_repo=FakeSessionRepo(session_exists=True),
        config=settings_factory(),
    )

    await service.persist_tool_slide_result(
        db=None,
        session_id="s1",
        presentation_name="Deck",
        slide_number=7,
        slide_title=None,
        slide_content="<html>New</html>",
        tool_name="SlideGenerate",
    )

    assert slide_repo.upserts[0]["slide_title"] == "Slide 7"
