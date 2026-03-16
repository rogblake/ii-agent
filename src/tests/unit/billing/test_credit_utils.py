from decimal import Decimal

from ii_agent.billing.credits.utils import credits_to_usd, usd_to_credits


def test_usd_to_credits_contract():
    assert usd_to_credits(1.5) == Decimal("100")


def test_credits_to_usd_contract():
    assert credits_to_usd(100) == Decimal("1.5")


def test_credit_usd_roundtrip():
    credits = usd_to_credits(Decimal("0.33"))
    assert credits_to_usd(credits) == Decimal("0.33")


def test_usd_to_credits_accepts_float():
    """Float inputs are converted to Decimal internally."""
    result = usd_to_credits(1.5)
    assert isinstance(result, Decimal)
    assert result == Decimal("100")


def test_credits_to_usd_accepts_float():
    result = credits_to_usd(100.0)
    assert isinstance(result, Decimal)
    assert result == Decimal("1.5")
