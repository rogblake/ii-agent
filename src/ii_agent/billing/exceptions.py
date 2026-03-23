"""Custom exceptions for billing domain."""

from __future__ import annotations

from typing import Any

from ii_agent.core.exceptions import IIAgentError, PaymentRequiredError


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


# ---------------------------------------------------------------------------
# Typed billing errors (credit_fix.md §Error Handling Contract)
# ---------------------------------------------------------------------------


class InsufficientCreditsError(PaymentRequiredError):
    """User does not have enough credits to proceed."""

    def __init__(
        self,
        message: str = "Insufficient credits",
        *,
        phase: str | None = None,
        available_credits: float | None = None,
        required_credits: float | None = None,
        reservation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = False
        self.billing_context: dict[str, Any] = {
            "phase": phase,
            "available_credits": available_credits,
            "required_credits": required_credits,
            "reservation_id": reservation_id,
        }

    def to_billing_payload(self) -> dict[str, Any]:
        return {
            "code": "insufficient_credits",
            "message": self.message,
            "retryable": False,
            "billing_context": self.billing_context,
        }


class BillingReconciliationRequiredError(PaymentRequiredError):
    """Account is blocked pending billing reconciliation."""

    def __init__(
        self,
        message: str = "Billing reconciliation required",
        *,
        reservation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = False
        self.billing_context: dict[str, Any] = {
            "phase": "reserve",
            "reservation_id": reservation_id,
        }

    def to_billing_payload(self) -> dict[str, Any]:
        return {
            "code": "billing_reconciliation_required",
            "message": self.message,
            "retryable": False,
            "billing_context": self.billing_context,
        }


class BillingTemporarilyUnavailableError(BillingException):
    """Billing system is temporarily unavailable — retry later."""

    status_code = 503

    def __init__(self, message: str = "Billing temporarily unavailable") -> None:
        super().__init__(message)
        self.retryable = True

    def to_billing_payload(self) -> dict[str, Any]:
        return {
            "code": "billing_temporarily_unavailable",
            "message": self.message,
            "retryable": True,
            "billing_context": {},
        }


class BillingDuplicateOperationError(BillingException):
    """A deterministic billing operation key was reused."""

    status_code = 409

    def __init__(
        self,
        message: str = "Billing operation key already in use",
        *,
        reservation_id: str | None = None,
        reservation_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = False
        self.reservation_id = reservation_id
        self.reservation_status = reservation_status

    def to_billing_payload(self) -> dict[str, Any]:
        return {
            "code": "duplicate_billing_operation",
            "message": self.message,
            "retryable": False,
            "billing_context": {
                "reservation_id": self.reservation_id,
                "reservation_status": self.reservation_status,
            },
        }


class BillingSettlementRetryableError(BillingException):
    """Settlement failed but can be retried."""

    def __init__(
        self,
        message: str = "Settlement failed (retryable)",
        *,
        reservation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = True
        self.reservation_id = reservation_id

    def to_billing_payload(self) -> dict[str, Any]:
        return {
            "code": "settlement_failed_retryable",
            "message": self.message,
            "retryable": True,
            "billing_context": {"reservation_id": self.reservation_id},
        }


class BillingSettlementFinalError(BillingException):
    """Settlement failed permanently."""

    def __init__(
        self,
        message: str = "Settlement failed permanently",
        *,
        reservation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = False
        self.reservation_id = reservation_id

    def to_billing_payload(self) -> dict[str, Any]:
        return {
            "code": "settlement_failed_final",
            "message": self.message,
            "retryable": False,
            "billing_context": {"reservation_id": self.reservation_id},
        }
