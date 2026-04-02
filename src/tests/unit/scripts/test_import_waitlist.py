from datetime import timezone

import pytest

from ii_agent.scripts.import_waitlist import _normalise_email, _normalise_tz_suffix, _parse_created_at


def test_normalise_tz_suffix_adds_minutes_when_missing():
    assert _normalise_tz_suffix("2026-02-01T10:00:00+07") == "2026-02-01T10:00:00+0700"


def test_parse_created_at_returns_utc_datetime():
    parsed = _parse_created_at("2026-02-01 10:00:00+07")

    assert parsed.tzinfo == timezone.utc


def test_normalise_email_rejects_missing_values():
    with pytest.raises(ValueError):
        _normalise_email("")

    assert _normalise_email("  USER@EXAMPLE.COM ") == "user@example.com"
