"""Shared Stripe configuration and helper methods."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import stripe

from ii_agent.core.config.settings import Settings
from ii_agent.billing.exceptions import StripeConfigError


class StripeConfig:
    """Shared Stripe configuration used by BillingService and StripeWebhookHandler."""

    def __init__(self, *, config: Settings) -> None:
        self._config = config
        self._price_map: dict[str, dict[str, str | None]] = {
            "plus": {
                "monthly": self._config.stripe.price_plus_monthly,
                "annually": self._config.stripe.price_plus_annually,
            },
            "pro": {
                "monthly": self._config.stripe.price_pro_monthly,
                "annually": self._config.stripe.price_pro_annually,
            },
        }

    @property
    def config(self) -> Settings:
        return self._config

    def ensure_api_key(self) -> None:
        if not self._config.stripe.secret_key:
            raise StripeConfigError("Stripe secret key is not configured")

        if stripe.api_key != self._config.stripe.secret_key:
            stripe.api_key = self._config.stripe.secret_key

    def get_price_id(self, plan_id: str, billing_cycle: str) -> str:
        from ii_agent.billing.exceptions import BillingUnsupportedPlanError, BillingConfigurationError

        plan_prices = self._price_map.get(plan_id)
        if not plan_prices:
            raise BillingUnsupportedPlanError(
                f"Plan '{plan_id}' is not available for upgrade"
            )

        price_id = plan_prices.get(billing_cycle)
        if not price_id:
            raise BillingConfigurationError(
                f"Stripe price id is not configured for plan '{plan_id}' with billing cycle '{billing_cycle}'"
            )

        return price_id

    def plan_cycle_from_price(
        self, price_id: str | None
    ) -> tuple[str, str] | None:
        if not price_id:
            return None

        for plan_id, cycles in self._price_map.items():
            for cycle, configured_price in cycles.items():
                if configured_price and configured_price == price_id:
                    return plan_id, cycle
        return None

    def resolve_return_urls(self, return_url: str | None) -> tuple[str, str]:
        from ii_agent.billing.exceptions import BillingConfigurationError

        base_url = (return_url or self._config.stripe_return_url or "").rstrip("/")

        success_url = self._config.stripe_success_url
        cancel_url = self._config.stripe_cancel_url

        if base_url:
            success_url = (
                success_url
                or f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
            )
            cancel_url = cancel_url or f"{base_url}"

        if not success_url or not cancel_url:
            raise BillingConfigurationError(
                "Stripe success and cancel URLs are not configured. Provide them via configuration or request."
            )

        return success_url, cancel_url

    def plan_credits(self, plan_id: str | None) -> float | None:
        if not plan_id:
            return None
        return self._config.credits.default_plans_credits.get(plan_id)

    _INTERVAL_TO_CYCLE: dict[str, str] = {
        "month": "monthly",
        "monthly": "monthly",
        "year": "annually",
        "annually": "annually",
    }

    @classmethod
    def normalize_billing_cycle(cls, raw: str | None) -> str | None:
        """Map Stripe interval values (``month``/``year``) to our canonical
        billing cycle names (``monthly``/``annually``).

        Returns ``None`` for unrecognised values.
        """
        if not raw:
            return None
        return cls._INTERVAL_TO_CYCLE.get(raw)

    @staticmethod
    def to_datetime(timestamp: int | None) -> datetime | None:
        if not timestamp:
            return None
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    @staticmethod
    def as_dict(stripe_object: Any) -> dict[str, Any]:
        if stripe_object is None:
            return {}
        if isinstance(stripe_object, dict):
            return stripe_object
        if hasattr(stripe_object, "to_dict_recursive"):
            return stripe_object.to_dict_recursive()
        return dict(stripe_object)
