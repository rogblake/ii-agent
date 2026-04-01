"""Credits domain enums."""

from enum import StrEnum


class TransactionType(StrEnum):
    """Every possible credit movement.

    Positive amounts (top-up):
        SIGNUP_GRANT       -- Initial credits on account creation
        SUBSCRIPTION_GRANT -- Monthly/yearly plan credits
        BONUS_GRANT        -- Promotional bonus
        PURCHASE           -- One-time credit purchase
        REFUND             -- Refund of a previous deduction
        ADJUSTMENT         -- Manual admin adjustment

    Negative amounts (deduction):
        LLM_USAGE          -- Token cost from LLM API call
        TOOL_USAGE         -- Direct tool cost
        MEDIA_GENERATION   -- Media generation cost
    """

    # Top-ups (positive)
    SIGNUP_GRANT = "signup_grant"
    SUBSCRIPTION_GRANT = "subscription_grant"
    BONUS_GRANT = "bonus_grant"
    PURCHASE = "purchase"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"

    # Deductions (negative)
    LLM_USAGE = "llm_usage"
    TOOL_USAGE = "tool_usage"
    MEDIA_GENERATION = "media_generation"


class CreditType(StrEnum):
    """Which balance pool a transaction affects."""

    REGULAR = "regular"
    BONUS = "bonus"
