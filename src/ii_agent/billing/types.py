"""Shared billing identity types used across domains."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class BillingContextValue(StrEnum):
    """Canonical high-level origins for billable work."""

    STORYBOOK = "storybook"


class BillingScope:
    """Lightweight billing scope for credit operations."""

    def __init__(
        self,
        *,
        user_id: uuid.UUID,
        app_kind: str,
        session_id: uuid.UUID,
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
        user_id: uuid.UUID,
        app_kind: str,
        session_id: uuid.UUID,
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
            "session_id": str(self.session_id),
            "billing_context": str(self.billing_context),
        }


@dataclass
class BillingResult:
    """Result of a billable operation carrying actual cost information."""

    value: Any
    actual_usd: float = 0.0
    usage_payload: dict[str, Any] = field(default_factory=dict)
