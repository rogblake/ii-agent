"""Stripe billing configuration."""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StripeSettings(BaseSettings):
    """Stripe payment and billing configuration.

    Environment variables use STRIPE_ prefix:
        STRIPE_SECRET_KEY: Stripe API secret key
        STRIPE_WEBHOOK_SECRET: Stripe webhook signing secret
        STRIPE_PRICE_PLUS_MONTHLY: Price ID for Plus monthly plan
        STRIPE_PRICE_PLUS_ANNUALLY: Price ID for Plus annual plan
        STRIPE_PRICE_PRO_MONTHLY: Price ID for Pro monthly plan
        STRIPE_PRICE_PRO_ANNUALLY: Price ID for Pro annual plan
        STRIPE_RETURN_URL: Default return URL after checkout
        STRIPE_SUCCESS_URL: Success page URL
        STRIPE_CANCEL_URL: Cancel page URL
        STRIPE_PORTAL_RETURN_URL: Return URL from customer portal

    Example .env:
        STRIPE_SECRET_KEY=sk_test_...
        STRIPE_WEBHOOK_SECRET=whsec_...
        STRIPE_PRICE_PLUS_MONTHLY=price_...
        STRIPE_PRICE_PLUS_ANNUALLY=price_...
    """

    model_config = SettingsConfigDict(
        env_prefix="STRIPE_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Stripe API credentials
    secret_key: Optional[str] = Field(
        default=None,
        description="Stripe API secret key (sk_test_... or sk_live_...)",
    )

    webhook_secret: Optional[str] = Field(
        default=None,
        description="Stripe webhook signing secret for webhook verification",
    )

    # Pricing plan IDs (Plus plan)
    price_plus_monthly: Optional[str] = Field(
        default=None,
        description="Stripe Price ID for Plus monthly subscription",
    )

    price_plus_annually: Optional[str] = Field(
        default=None,
        description="Stripe Price ID for Plus annual subscription",
    )

    # Pricing plan IDs (Pro plan)
    price_pro_monthly: Optional[str] = Field(
        default=None,
        description="Stripe Price ID for Pro monthly subscription",
    )

    price_pro_annually: Optional[str] = Field(
        default=None,
        description="Stripe Price ID for Pro annual subscription",
    )

    # Checkout URLs
    return_url: Optional[str] = Field(
        default=None,
        description="Default return URL after checkout session",
    )

    success_url: Optional[str] = Field(
        default=None,
        description="Success page URL after successful payment",
    )

    cancel_url: Optional[str] = Field(
        default=None,
        description="Cancel page URL when user cancels checkout",
    )

    # Customer portal
    portal_return_url: Optional[str] = Field(
        default=None,
        description="Return URL from Stripe customer portal",
    )

    def is_configured(self) -> bool:
        """Check if Stripe is properly configured.

        Returns:
            bool: True if secret key is configured
        """
        return bool(self.secret_key)

    def has_webhooks(self) -> bool:
        """Check if webhook secret is configured.

        Returns:
            bool: True if webhook secret is configured
        """
        return bool(self.webhook_secret)

    def get_price_id(self, plan: str, billing_cycle: str) -> Optional[str]:
        """Get price ID for a given plan and billing cycle.

        Args:
            plan: Plan name ('plus' or 'pro')
            billing_cycle: Billing cycle ('monthly' or 'annually')

        Returns:
            Optional[str]: Price ID if configured, None otherwise
        """
        price_map = {
            ("plus", "monthly"): self.price_plus_monthly,
            ("plus", "annually"): self.price_plus_annually,
            ("pro", "monthly"): self.price_pro_monthly,
            ("pro", "annually"): self.price_pro_annually,
        }
        return price_map.get((plan.lower(), billing_cycle.lower()))
