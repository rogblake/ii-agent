"""Credits domain constants."""

from decimal import Decimal

# Minimum credit balance required to start or continue an agent run.
# Used both at session validation (pre-run gate) and after each deduction
# (exhaustion check).
MINIMUM_REQUIRED_CREDITS = Decimal("1")
