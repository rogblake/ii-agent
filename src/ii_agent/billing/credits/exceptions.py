"""Custom exceptions for credits domain."""

from ii_agent.core.exceptions import NotFoundError


class CreditBalanceNotFoundError(NotFoundError):
    """Raised when a user's credit balance is not found."""

    pass
