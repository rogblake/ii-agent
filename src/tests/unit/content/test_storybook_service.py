from datetime import datetime, timezone

from ii_agent.content.storybook.schemas import StorybookDetail, StorybookPageInfo
from ii_agent.content.storybook.service import StorybookService


def _storybook_detail(style_json, pages):
    now = datetime.now(timezone.utc)
    return StorybookDetail(
        id="sb1",
        session_id="s1",
        name="Story",
        version=1,
        style_json=style_json,
        aspect_ratio="1:1",
        resolution="1K",
        page_count=len(pages),
        created_at=now,
        updated_at=now,
        pages=pages,
    )


def _page(page_number, image_url):
    now = datetime.now(timezone.utc)
    return StorybookPageInfo(
        id=f"p{page_number}",
        storybook_id="sb1",
        page_number=page_number,
        image_url=image_url,
        image_prompt=None,
        text_content=None,
        audio_link=None,
        text_position="none",
        text_percentage=30,
        html_content=None,
        metadata={},
        created_at=now,
        updated_at=now,
    )


def test_build_generation_response_returns_progress_for_generating(settings_factory):
    service = StorybookService(repo=None, config=settings_factory())
    storybook = _storybook_detail(
        style_json={"generation": {"status": "generating", "total_pages": 3, "completed_pages": 1}},
        pages=[_page(1, "https://img/1.png")],
    )

    response = service.build_generation_response(storybook)

    assert response.status == "generating"
    assert response.total_pages == 3
    assert response.completed_pages == 1


def test_build_generation_response_returns_result_when_completed(settings_factory):
    service = StorybookService(repo=None, config=settings_factory())
    storybook = _storybook_detail(
        style_json={"generation": {"status": "completed", "total_pages": 1, "completed_pages": 1}},
        pages=[_page(1, "https://img/1.png")],
    )

    response = service.build_generation_response(storybook)

    assert response.pages[0].image_url == "https://img/1.png"
    assert response.storybook_id == "sb1"


def test_build_generation_response_handles_separate_page_numbering(settings_factory):
    service = StorybookService(repo=None, config=settings_factory())
    storybook = _storybook_detail(
        style_json={
            "user_text_position": "separate_page",
            "generation": {"status": "completed", "total_pages": 2, "completed_pages": 2},
        },
        pages=[_page(1, "https://img/1.png"), _page(2, "https://img/2.png")],
    )

    response = service.build_generation_response(storybook)

    assert response.pages[0].page_number == 1
    assert response.pages[1].page_number == 2
