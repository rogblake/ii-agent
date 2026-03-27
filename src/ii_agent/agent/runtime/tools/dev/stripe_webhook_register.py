import json
import logging
import shlex
from typing import TYPE_CHECKING, Any

from ii_agent.agent.runtime.tools.base import TextContent, ToolResult
from ii_agent.agent.runtime.tools.sandbox.base import BaseSandboxTool

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall

logger = logging.getLogger(__name__)

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
            "description": "Specific Stripe event types to subscribe to. Defaults to common payment events.",
        },
        "description": {
            "type": "string",
            "description": "Optional description for the webhook endpoint in Stripe Dashboard.",
        },
    },
    "required": ["stripe_secret_key", "endpoint_url", "project_directory"],
}

DEFAULT_TIMEOUT = 120


class StripeWebhookRegisterTool(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            cmd_parts = [
                "ii-app", "stripe", "register-webhook",
                "--stripe-secret-key", tool_input["stripe_secret_key"],
                "--endpoint-url", tool_input["endpoint_url"],
                "--project-directory", tool_input["project_directory"],
                "--json",
            ]

            events = tool_input.get("events")
            if events:
                cmd_parts.extend(["--event", ",".join(events)])

            description = tool_input.get("description")
            if description:
                cmd_parts.extend(["--description", description])

            cmd = " ".join(shlex.quote(p) for p in cmd_parts)
            output = await self.sandbox.run_command(cmd, timeout=DEFAULT_TIMEOUT)
            result = json.loads(output)
            return ToolResult(
                llm_content=[TextContent(type="text", text=output)],
                user_display_content=result,
            )
        except Exception as e:
            logger.exception("Failed to register Stripe webhook")
            return ToolResult(
                llm_content=f"Failed to register Stripe webhook: {e}",
                user_display_content=f"Failed to register Stripe webhook: {e}",
                is_error=True,
            )
