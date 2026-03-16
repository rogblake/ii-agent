from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ii_agent.workers.cron import refresh_annual_subscription_credits as annual_refresh


def test_parse_iso_date_handles_timezone_and_invalid_values():
    parsed = annual_refresh._parse_iso_date("2026-01-01T00:00:00+00:00")

    assert parsed.tzinfo is not None
    assert annual_refresh._parse_iso_date("not-a-date") is None


def test_should_refresh_skips_if_already_refreshed_this_month(settings_factory, monkeypatch):
    monkeypatch.setattr(annual_refresh, "get_settings", lambda: settings_factory())
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    user = SimpleNamespace(
        id="u1",
        user_metadata={"last_annual_credit_refresh": now.isoformat()},
        credits=0.0,
    )

    should, monthly = annual_refresh._should_refresh(
        user,
        now=now,
        plan_id="plus",
        period_end=now,
    )

    assert should is False
    assert monthly is None


def test_should_refresh_returns_true_when_eligible(settings_factory, monkeypatch):
    monkeypatch.setattr(annual_refresh, "get_settings", lambda: settings_factory())
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    user = SimpleNamespace(
        id="u1",
        user_metadata={},
        credits=0.0,
    )

    should, monthly = annual_refresh._should_refresh(
        user,
        now=now,
        plan_id="plus",
        period_end=now,
    )

    assert should is True
    assert monthly == 100.0
