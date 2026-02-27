from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ii_agent.workers.cron import refresh_annual_subscription_credits as annual_refresh


def test_parse_iso_date_handles_timezone_and_invalid_values():
    parsed = annual_refresh._parse_iso_date("2026-01-01T00:00:00+00:00")

    assert parsed.tzinfo is not None
    assert annual_refresh._parse_iso_date("not-a-date") is None


@pytest.mark.asyncio
async def test_refresh_user_credits_skips_if_already_refreshed_this_month(settings_factory, monkeypatch):
    monkeypatch.setattr(annual_refresh, "get_settings", lambda: settings_factory())
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    user = SimpleNamespace(
        id="u1",
        subscription_plan="plus",
        subscription_current_period_end=now,
        user_metadata={"last_annual_credit_refresh": now.isoformat()},
        credits=0.0,
    )

    refreshed = await annual_refresh._refresh_user_credits(user, now=now)

    assert refreshed is False


@pytest.mark.asyncio
async def test_refresh_user_credits_updates_when_eligible(settings_factory, monkeypatch):
    monkeypatch.setattr(annual_refresh, "get_settings", lambda: settings_factory())
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    user = SimpleNamespace(
        id="u1",
        subscription_plan="plus",
        subscription_current_period_end=now,
        user_metadata={},
        credits=0.0,
    )

    refreshed = await annual_refresh._refresh_user_credits(user, now=now)

    assert refreshed is True
    assert user.credits == 100.0
    assert annual_refresh.REFRESH_METADATA_KEY in user.user_metadata
