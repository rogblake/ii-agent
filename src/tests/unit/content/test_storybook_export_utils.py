from datetime import datetime, timezone

import ii_agent.content.storybook.html_generator as html_generator_module
from ii_agent.content.storybook.export_utils import (
    find_page_by_number,
    prepare_pages_for_export,
    prepare_single_page_for_export,
)
from ii_agent.content.storybook.schemas import StorybookPageInfo


def _page(
    page_number: int,
    *,
    html_content: str | None = "<div>page</div>",
    metadata: dict | None = None,
) -> StorybookPageInfo:
    now = datetime.now(timezone.utc)
    return StorybookPageInfo(
        id=f"p{page_number}",
        storybook_id="sb-1",
        page_number=page_number,
        image_url=f"https://img/{page_number}.png",
        image_prompt=None,
        text_content=f"text-{page_number}",
        text_position="none",
        text_percentage=30,
        html_content=html_content,
        audio_link=None,
        metadata=metadata or {},
        created_at=now,
        updated_at=now,
    )


def test_find_page_by_number_returns_match_or_none():
    pages = [_page(1), _page(2)]

    assert find_page_by_number(pages, 2).id == "p2"
    assert find_page_by_number(pages, 3) is None


def test_prepare_pages_for_export_combines_separate_page_pairs(monkeypatch):
    monkeypatch.setattr(
        html_generator_module, "_calculate_dimensions", lambda *_: (100, 200)
    )
    monkeypatch.setattr(
        html_generator_module,
        "combine_html_pages_for_export",
        lambda **kwargs: (f"combined-{kwargs['page_number']}", 300, 200),
    )

    pages = [
        _page(1, html_content="<img-1>", metadata={"is_separate_page_image": True}),
        _page(2, html_content="<text-2>", metadata={"is_text_only_page": True}),
        _page(3, html_content="<normal-3>"),
    ]

    export_pages = prepare_pages_for_export(
        pages=pages,
        aspect_ratio="1:1",
        resolution="1K",
    )

    assert export_pages == [
        (1, "combined-1", 300, 200),
        (2, "<normal-3>", 100, 200),
    ]


def test_prepare_single_page_for_export_returns_none_for_missing_page():
    assert (
        prepare_single_page_for_export(
            pages=[_page(1)],
            page_number=99,
            aspect_ratio="1:1",
            resolution="1K",
        )
        is None
    )


def test_prepare_single_page_for_export_combines_image_and_text_page(monkeypatch):
    monkeypatch.setattr(
        html_generator_module, "_calculate_dimensions", lambda *_: (120, 240)
    )
    monkeypatch.setattr(
        html_generator_module,
        "combine_html_pages_for_export",
        lambda **kwargs: ("combined", 400, 240),
    )

    pages = [
        _page(1, html_content="<img-1>", metadata={"is_separate_page_image": True}),
        _page(2, html_content="<text-2>", metadata={"is_text_only_page": True}),
    ]

    export_data = prepare_single_page_for_export(
        pages=pages,
        page_number=1,
        aspect_ratio="1:1",
        resolution="1K",
    )

    assert export_data == ("combined", 400, 240)


def test_prepare_single_page_for_export_combines_from_text_side(monkeypatch):
    monkeypatch.setattr(
        html_generator_module, "_calculate_dimensions", lambda *_: (120, 240)
    )
    monkeypatch.setattr(
        html_generator_module,
        "combine_html_pages_for_export",
        lambda **kwargs: ("combined-from-text", 400, 240),
    )

    pages = [
        _page(1, html_content="<img-1>", metadata={"is_separate_page_image": True}),
        _page(2, html_content="<text-2>", metadata={"is_text_only_page": True}),
    ]

    export_data = prepare_single_page_for_export(
        pages=pages,
        page_number=2,
        aspect_ratio="1:1",
        resolution="1K",
    )

    assert export_data == ("combined-from-text", 400, 240)


def test_prepare_single_page_for_export_returns_none_when_html_missing(monkeypatch):
    monkeypatch.setattr(
        html_generator_module, "_calculate_dimensions", lambda *_: (120, 240)
    )

    export_data = prepare_single_page_for_export(
        pages=[_page(1, html_content=None)],
        page_number=1,
        aspect_ratio="1:1",
        resolution="1K",
    )

    assert export_data is None


def test_prepare_single_page_for_export_returns_page_with_base_dimensions(monkeypatch):
    monkeypatch.setattr(
        html_generator_module, "_calculate_dimensions", lambda *_: (150, 250)
    )

    export_data = prepare_single_page_for_export(
        pages=[_page(1, html_content="<standalone>")],
        page_number=1,
        aspect_ratio="1:1",
        resolution="1K",
    )

    assert export_data == ("<standalone>", 150, 250)
