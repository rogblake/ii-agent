"""Constants for credits domain."""

from decimal import Decimal

# Pricing contract:
# 100 II-Agent credits == $1.5 USD
USD_PER_100_CREDITS = Decimal("1.5")
CREDITS_PER_100_USD = Decimal("100")

# Derived multipliers (kept for backward compat; conversion functions in
# utils.py compute via numerator/denominator to avoid repeating-decimal loss).
USD_TO_CREDITS_MULTIPLIER = CREDITS_PER_100_USD / USD_PER_100_CREDITS  # ~66.666…
CREDITS_TO_USD_MULTIPLIER = USD_PER_100_CREDITS / CREDITS_PER_100_USD  # 0.015
