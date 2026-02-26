# Unit Test Plan: `billing`

## Scope

- checkout/portal orchestration (`billing/service.py`)
- webhook dispatch and per-event handlers (`billing/webhook_handler.py`)
- credit arithmetic and usage tracking (`billing/credits/service.py`)
- price/plan mapping behavior (`billing/stripe_config.py`, `billing/credits/pricing.py`)

## Priority test suites

1. Checkout session creation.
- free plan is rejected (`BillingUnsupportedPlanError`)
- existing `stripe_customer_id` is reused
- metadata and tax fields are passed correctly

2. Portal session creation.
- missing user/customer/return URL error branches
- Stripe API error is translated into service error

3. Webhook event construction.
- missing secret/signature handling
- invalid payload/signature handling

4. Webhook idempotency and updates.
- duplicate `event_id` does not create duplicate transactions
- invoice/subscription events update user subscription fields correctly
- cancellation resets plan to `free` and baseline credits

5. Credit service arithmetic.
- `has_sufficient` checks regular+bonus total
- `deduct` consumes bonus before regular
- `add` and `set_balance` update expected fields
- session usage accumulation creates/updates metrics

## Fixtures / mocks

- monkeypatched Stripe SDK calls
- fake user/billing repositories
- async DB fixture for credit balance assertions

## Proposed test layout

- `src/tests/unit/billing/test_checkout_service.py`
- `src/tests/unit/billing/test_webhook_handler.py`
- `src/tests/unit/billing/test_credit_service.py`
- `src/tests/unit/billing/test_pricing_mapping.py`

## Exit criteria

- billing idempotency and credit integrity verified
- all external Stripe interactions covered with mocks
