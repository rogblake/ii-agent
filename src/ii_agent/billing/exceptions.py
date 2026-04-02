"""Custom exceptions for billing domain."""

from ii_agent.core.exceptions import IIAgentError


class BillingException(IIAgentError):
    """Base exception for billing domain."""

    status_code = 500


class BillingServiceError(BillingException):
    """Base error for billing service issues."""

    pass


class BillingConfigurationError(BillingServiceError):
    """Raised when billing configuration is missing or invalid."""

    pass


class BillingUnsupportedPlanError(BillingException):
    """Raised when a requested plan or billing cycle is not supported."""

    status_code = 400


class BillingGatewayError(BillingException):
    """Raised when a Stripe API call fails."""

    status_code = 502


class StripeConfigError(BillingConfigurationError):
    """Raised when Stripe configuration is missing or invalid."""

    pass
