from ii_agent.engine.v1.tools.mcp.base import MCPTool

NAME = "stripe_webhook_register"
DISPLAY_NAME = "Register Stripe Webhook"
DESCRIPTION = """Registers a webhook endpoint with Stripe API so users do NOT need to configure it manually in Stripe Dashboard.

Usage:
- Provide the user's STRIPE_SECRET_KEY.
- Provide a public HTTPS URL where Stripe will send webhook events.
- Optionally specify which events to subscribe to (defaults to common payment events).
- The tool will register the webhook with Stripe and write the returned signing secret to the project's .env file.

Returns:
- webhook_endpoint_id: The Stripe webhook endpoint ID.
- webhook_signing_secret: The whsec_... secret for verifying webhook signatures (written to .env as STRIPE_WEBHOOK_SECRET).

Notes:
- Uses Idempotency-Key to avoid creating duplicate webhook endpoints if tool is re-run.
"""
DEFAULT_EVENTS = [
    "checkout.session.completed",
    "checkout.session.expired",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
]
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "stripe_secret_key": {
            "type": "string",
            "description": "The Stripe secret key (sk_live_... or sk_test_...).",
        },
        "endpoint_url": {
            "type": "string",
            "description": "The public HTTPS URL to receive Stripe webhook events (e.g., https://myapp.com/api/webhooks/stripe).",
        },
        "project_directory": {
            "type": "string",
            "description": "Absolute or workspace-relative path to the project root where .env should be updated with STRIPE_WEBHOOK_SECRET.",
        },
        "events": {
            "type": "array",
            "items": {"type": "string"},
            "description": f"Specific Stripe event types to subscribe to. Defaults to common payment events: {DEFAULT_EVENTS[:3]}...",
        },
        "description": {
            "type": "string",
            "description": "Optional description for the webhook endpoint in Stripe Dashboard.",
        },
    },
    "required": ["stripe_secret_key", "endpoint_url", "project_directory"],
}


class StripeWebhookRegisterTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
