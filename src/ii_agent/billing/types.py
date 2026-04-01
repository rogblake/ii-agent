"""Shared billing identity types used across domains."""

from __future__ import annotations

from enum import StrEnum


class BillingContextValue(StrEnum):
    """Canonical high-level origins for billable work."""

    STORYBOOK = "storybook"


class BillingScope:
    """Lightweight billing scope for credit operations."""

    def __init__(
        self,
        *,
        user_id: str,
        app_kind: str,
        session_id: str,
        billing_context: BillingContextValue,
        run_id: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.app_kind = app_kind
        self.session_id = session_id
        self.billing_context = billing_context
        self.run_id = run_id

    @classmethod
    def for_session(
        cls,
        *,
        user_id: str,
        app_kind: str,
        session_id: str,
        billing_context: BillingContextValue,
        run_id: str | None = None,
    ) -> BillingScope:
        return cls(
            user_id=user_id,
            app_kind=app_kind,
            session_id=session_id,
            billing_context=billing_context,
            run_id=run_id,
        )

    def billing_metadata(self) -> dict:
        return {
            "app_kind": self.app_kind,
            "session_id": self.session_id,
            "billing_context": str(self.billing_context),
        }
