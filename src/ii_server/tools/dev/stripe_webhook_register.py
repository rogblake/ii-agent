import hashlib
import os
import shlex
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

from ii_server.core.workspace import (
    FileSystemValidationError,
    WorkspaceManager,
)
from ii_server.tools.base import BaseTool, ToolResult


DEFAULT_TIMEOUT = 60

# Name
NAME = "stripe_webhook_register"
DISPLAY_NAME = "Register Stripe Webhook"

# Description
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

# Default events to subscribe to
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

# Input schema
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


class StripeWebhookRegisterTool(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
    ) -> None:
        super().__init__()
        self.workspace_manager = workspace_manager

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        stripe_secret_key = tool_input.get("stripe_secret_key", "").strip()
        endpoint_url = tool_input.get("endpoint_url", "").strip()
        raw_path = tool_input.get("project_directory", "").strip()
        events = tool_input.get("events") or DEFAULT_EVENTS
        description = tool_input.get("description", "Webhook registered via II Agent")

        # Validate stripe_secret_key
        if not stripe_secret_key:
            return ToolResult(
                llm_content="stripe_secret_key is required.",
                is_error=True,
            )
        if not stripe_secret_key.startswith(("sk_live_", "sk_test_")):
            return ToolResult(
                llm_content="Invalid stripe_secret_key format. Must start with 'sk_live_' or 'sk_test_'.",
                is_error=True,
            )

        # Validate endpoint_url
        if not endpoint_url:
            return ToolResult(
                llm_content="endpoint_url is required.",
                is_error=True,
            )
        if not endpoint_url.startswith("https://"):
            return ToolResult(
                llm_content="endpoint_url must be a public HTTPS URL (must start with 'https://').",
                is_error=True,
            )

        # Validate project_directory
        if not raw_path:
            return ToolResult(
                llm_content="project_directory is required.",
                is_error=True,
            )

        try:
            project_dir = self._resolve_directory(raw_path)
        except FileSystemValidationError as exc:
            return ToolResult(llm_content=str(exc), is_error=True)

        # Generate idempotency key based on endpoint_url to avoid duplicates
        idempotency_key = self._generate_idempotency_key(endpoint_url)

        # Register webhook with Stripe
        result, error = await self._register_stripe_webhook(
            stripe_secret_key=stripe_secret_key,
            endpoint_url=endpoint_url,
            events=events,
            description=description,
            idempotency_key=idempotency_key,
        )

        if error:
            return ToolResult(
                llm_content=f"Failed to register Stripe webhook: {error}",
                is_error=True,
            )

        webhook_id = result.get("id", "")
        webhook_secret = result.get("secret", "")

        if not webhook_secret:
            return ToolResult(
                llm_content="Stripe did not return a webhook signing secret. The webhook may have been created previously. Check your Stripe Dashboard.",
                user_display_content={
                    "webhook_endpoint_id": webhook_id,
                    "endpoint_url": endpoint_url,
                    "warning": "No signing secret returned - webhook may already exist",
                },
                is_error=True,
            )

        # Write STRIPE_WEBHOOK_SECRET to .env (do NOT write stripe_secret_key)
        self._write_webhook_secret_to_env(project_dir, webhook_secret)

        return ToolResult(
            llm_content=f"Successfully registered Stripe webhook endpoint.\n"
            f"- Webhook ID: {webhook_id}\n"
            f"- Endpoint URL: {endpoint_url}\n"
            f"- Events: {len(events)} event types\n"
            f"- STRIPE_WEBHOOK_SECRET has been written to {project_dir}/.env\n",
            user_display_content={
                "webhook_endpoint_id": webhook_id,
                "webhook_signing_secret": webhook_secret,
                "endpoint_url": endpoint_url,
                "events": events,
                "env_file_updated": f"{project_dir}/.env",
            },
            is_error=False,
        )

    def _generate_idempotency_key(self, endpoint_url: str) -> str:
        """Generate a stable idempotency key based on the endpoint URL."""
        return f"webhook_register_{hashlib.sha256(endpoint_url.encode()).hexdigest()[:32]}"

    async def _register_stripe_webhook(
        self,
        stripe_secret_key: str,
        endpoint_url: str,
        events: list[str],
        description: str,
        idempotency_key: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Register a webhook endpoint with Stripe API."""
        try:
            # Build form data for Stripe API
            # Stripe expects events as enabled_events[]
            form_data = {
                "url": endpoint_url,
                "description": description,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.stripe.com/v1/webhook_endpoints",
                    data=form_data,
                    params=[("enabled_events[]", event) for event in events],
                    headers={
                        "Authorization": f"Bearer {stripe_secret_key}",
                        "Idempotency-Key": idempotency_key,
                    },
                    timeout=DEFAULT_TIMEOUT,
                )

            if response.status_code == 200:
                return response.json(), None
            elif response.status_code == 400:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", response.text)
                return None, f"Bad request: {error_message}"
            elif response.status_code == 401:
                return None, "Invalid Stripe API key. Please check your STRIPE_SECRET_KEY."
            elif response.status_code == 409:
                # Idempotency conflict - webhook may already exist
                return None, "A webhook with this endpoint URL may already exist (idempotency conflict)."
            else:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_message = error_data.get("error", {}).get("message", response.text)
                return None, f"Stripe API error (status {response.status_code}): {error_message}"

        except httpx.TimeoutException:
            return None, "Request to Stripe API timed out."
        except httpx.RequestError as exc:
            return None, f"Network error connecting to Stripe API: {exc}"
        except Exception as exc:
            return None, f"Unexpected error: {exc}"

    def _write_webhook_secret_to_env(self, project_dir: str, webhook_secret: str) -> None:
        """Write STRIPE_WEBHOOK_SECRET to the project's .env file."""
        env_path = Path(project_dir) / ".env"
        env_key = "STRIPE_WEBHOOK_SECRET"

        # Read existing .env content if it exists
        existing_lines: list[str] = []
        if env_path.exists():
            existing_content = env_path.read_text(encoding="utf-8")
            existing_lines = existing_content.splitlines()

        # Check if STRIPE_WEBHOOK_SECRET already exists and update it
        updated = False
        new_lines = []
        for line in existing_lines:
            stripped = line.strip()
            if stripped.startswith(f"{env_key}=") or stripped.startswith(f"{env_key} ="):
                new_lines.append(f"{env_key}={webhook_secret}")
                updated = True
            else:
                new_lines.append(line)

        # If not found, append the new key
        if not updated:
            new_lines.append(f"{env_key}={webhook_secret}")

        # Write back to .env
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        # Also write to container paths if they exist
        self._write_to_container_env(env_key, webhook_secret)

    def _write_to_container_env(self, key: str, value: str) -> None:
        """Write to container environment files if running in container."""
        # Write to /app/.user_env
        app_env_path = Path("/app/.user_env")
        if app_env_path.parent.exists():
            self._append_or_update_env_file(app_env_path, key, value)

        # Write to /app/.user_env.sh
        app_env_sh_path = Path("/app/.user_env.sh")
        if app_env_sh_path.parent.exists():
            self._append_or_update_env_file(
                app_env_sh_path,
                key,
                value,
                export_format=True,
            )

    def _append_or_update_env_file(
        self,
        path: Path,
        key: str,
        value: str,
        export_format: bool = False,
    ) -> None:
        """Append or update a key in an env file."""
        existing_lines: list[str] = []
        if path.exists():
            existing_lines = path.read_text(encoding="utf-8").splitlines()

        line_prefix = f"export {key}=" if export_format else f"{key}="
        new_value = f"export {key}={shlex.quote(value)}" if export_format else f"{key}={value}"

        updated = False
        new_lines = []
        for line in existing_lines:
            stripped = line.strip()
            if stripped.startswith(line_prefix) or stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                new_lines.append(new_value)
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(new_value)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    def _resolve_directory(self, candidate: str) -> str:
        """Resolve and validate the project directory path."""
        workspace_root = str(self.workspace_manager.get_workspace_path())
        path = candidate
        if not os.path.isabs(path):
            path = os.path.join(workspace_root, path)
        self.workspace_manager.validate_existing_directory_path(path)
        return path

    async def execute_mcp_wrapper(
        self,
        stripe_secret_key: str,
        endpoint_url: str,
        project_directory: str,
        events: list[str] | None = None,
        description: str | None = None,
    ):
        """MCP wrapper for FastMCP compatibility."""
        return await self._mcp_wrapper(
            tool_input={
                "stripe_secret_key": stripe_secret_key,
                "endpoint_url": endpoint_url,
                "project_directory": project_directory,
                "events": events,
                "description": description,
            }
        )
