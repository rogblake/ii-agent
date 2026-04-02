import asyncio

from ii_agent.celery import tasks


def test_get_celery_loop_reuses_single_loop(monkeypatch):
    tasks._celery_loop = None

    loop1 = tasks._get_celery_loop()
    loop2 = tasks._get_celery_loop()

    assert loop1 is loop2
    assert isinstance(loop1, asyncio.AbstractEventLoop)


def test_page_mapping_helpers():
    assert tasks._scene_base_page_number(0, separate_page=False) == 1
    assert tasks._scene_base_page_number(2, separate_page=True) == 4

    assert tasks._db_page_to_display_page(1, separate_page_mode=True) == 1
    assert tasks._db_page_to_display_page(4, separate_page_mode=True) == 3
    assert tasks._db_page_to_display_page(4, separate_page_mode=False) == 4


def test_credit_estimation_math_is_deterministic():
    value = tasks._estimate_page_credits(image_cost_usd=0.03, audio_cost_usd=0.02)

    assert round(value, 4) == round((0.05 * tasks.USD_TO_CREDITS_MULTIPLIER), 4)
