from ii_agent.billing.credits.utils import credits_to_usd, usd_to_credits


def test_usd_to_credits_contract():
    assert usd_to_credits(1.5) == 100.0


def test_credits_to_usd_contract():
    assert credits_to_usd(100) == 1.5


def test_credit_usd_roundtrip():
    credits = usd_to_credits(0.33)
    assert round(credits_to_usd(credits), 6) == 0.33
