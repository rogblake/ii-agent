"""Cloudflare KV Service for subdomain routing.

Manages subdomain -> Cloud Run URL mappings in Cloudflare KV.
The mappings are read by a Cloudflare Worker to route traffic.

Flow:
1. User deploys app to Cloud Run
2. User claims subdomain (e.g., "myapp")
3. Backend writes to KV: "myapp" -> {"cloud_run_url": "https://xxx.a.run.app", ...}
4. Worker reads KV and routes traffic

Environment Variables Required:
- CLOUDFLARE_API_TOKEN: API token with KV write permissions
- CLOUDFLARE_ACCOUNT_ID: Your Cloudflare account ID
- CLOUDFLARE_KV_NAMESPACE_ID: The KV namespace ID for subdomain routes
- CLOUDFLARE_BASE_DOMAIN: Base domain (e.g., "iiapp.dev")
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx

from ii_agent.core.logger import logger


class SubdomainStatus(Enum):
    """Status of a subdomain."""

    ACTIVE = "active"
    PENDING = "pending"
    DELETED = "deleted"
    FAILED = "failed"


@dataclass
class SubdomainResult:
    """Result of a subdomain operation."""

    success: bool
    subdomain: str | None = None
    full_domain: str | None = None
    status: SubdomainStatus | None = None
    cloud_run_url: str | None = None
    error: str | None = None


@dataclass
class CloudflareKVConfig:
    """Configuration for Cloudflare KV service."""

    api_token: str
    account_id: str
    kv_namespace_id: str
    base_domain: str

    @classmethod
    def from_env(cls) -> CloudflareKVConfig:
        """Create config from environment variables."""
        api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
        if not api_token:
            raise ValueError("CLOUDFLARE_API_TOKEN environment variable is required")

        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        if not account_id:
            raise ValueError("CLOUDFLARE_ACCOUNT_ID environment variable is required")

        kv_namespace_id = os.environ.get("CLOUDFLARE_KV_NAMESPACE_ID")
        if not kv_namespace_id:
            raise ValueError("CLOUDFLARE_KV_NAMESPACE_ID environment variable is required")

        base_domain = os.environ.get("CLOUDFLARE_BASE_DOMAIN")
        if not base_domain:
            raise ValueError("CLOUDFLARE_BASE_DOMAIN environment variable is required")

        return cls(
            api_token=api_token,
            account_id=account_id,
            kv_namespace_id=kv_namespace_id,
            base_domain=base_domain,
        )


# Reserved subdomains that users cannot use
RESERVED_SUBDOMAINS = {
    "www", "api", "app", "admin", "mail", "email", "smtp", "pop", "imap",
    "ftp", "ssh", "vpn", "proxy", "cdn", "static", "assets", "img", "images",
    "js", "css", "fonts", "media", "video", "docs", "help", "support",
    "status", "blog", "news", "shop", "store", "pay", "billing", "account",
    "login", "auth", "oauth", "sso", "dashboard", "console", "panel",
    "test", "dev", "staging", "prod", "production", "demo", "beta", "alpha",
}


def validate_subdomain(subdomain: str) -> tuple[bool, str | None]:
    """Validate subdomain name.

    Returns:
        Tuple of (is_valid, error_message)
    """
    subdomain = subdomain.lower().strip()

    if len(subdomain) < 2:
        return False, "Subdomain must be at least 2 characters"
    if len(subdomain) > 63:
        return False, "Subdomain must be at most 63 characters"

    if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", subdomain):
        return False, "Subdomain can only contain lowercase letters, numbers, and hyphens"

    if subdomain in RESERVED_SUBDOMAINS:
        return False, f"'{subdomain}' is a reserved subdomain"

    return True, None


class CloudflareKVService:
    """Service for managing subdomain routes in Cloudflare KV."""

    BASE_URL = "https://api.cloudflare.com/client/v4"
    RESERVED_SUBDOMAINS = RESERVED_SUBDOMAINS

    def __init__(self, config: CloudflareKVConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-loaded HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.config.api_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def create_subdomain(
        self,
        subdomain: str,
        cloud_run_url: str,
        project_id: str | None = None,
        user_id: str | None = None,
    ) -> SubdomainResult:
        """Create a subdomain route in KV."""
        subdomain = subdomain.lower().strip()

        is_valid, error = validate_subdomain(subdomain)
        if not is_valid:
            return SubdomainResult(success=False, subdomain=subdomain, error=error)

        full_domain = f"{subdomain}.{self.config.base_domain}"

        kv_value = {
            "cloud_run_url": cloud_run_url,
            "project_id": project_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            existing = await self._get_kv_value(subdomain)
            if existing:
                return await self.update_subdomain(subdomain, cloud_run_url, project_id, user_id)

            url = (
                f"{self.BASE_URL}/accounts/{self.config.account_id}"
                f"/storage/kv/namespaces/{self.config.kv_namespace_id}/values/{subdomain}"
            )

            response = await self.client.put(url, content=json.dumps(kv_value))

            if response.status_code not in (200, 201):
                error_msg = f"Failed to write to KV: {response.status_code}"
                try:
                    data = response.json()
                    if data.get("errors"):
                        error_msg = data["errors"][0].get("message", error_msg)
                except Exception:
                    pass
                return SubdomainResult(
                    success=False, subdomain=subdomain, full_domain=full_domain, error=error_msg,
                )

            logger.info(f"Created subdomain route: {subdomain} -> {cloud_run_url}")

            return SubdomainResult(
                success=True,
                subdomain=subdomain,
                full_domain=full_domain,
                status=SubdomainStatus.ACTIVE,
                cloud_run_url=cloud_run_url,
            )

        except Exception as e:
            logger.exception(f"Failed to create subdomain: {subdomain}")
            return SubdomainResult(
                success=False, subdomain=subdomain, full_domain=full_domain, error=str(e),
            )

    async def update_subdomain(
        self,
        subdomain: str,
        cloud_run_url: str,
        project_id: str | None = None,
        user_id: str | None = None,
    ) -> SubdomainResult:
        """Update a subdomain route in KV."""
        subdomain = subdomain.lower().strip()
        full_domain = f"{subdomain}.{self.config.base_domain}"

        existing = await self._get_kv_value(subdomain)

        kv_value = {
            "cloud_run_url": cloud_run_url,
            "project_id": project_id or (existing.get("project_id") if existing else None),
            "user_id": user_id or (existing.get("user_id") if existing else None),
            "created_at": existing.get("created_at") if existing else datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            url = (
                f"{self.BASE_URL}/accounts/{self.config.account_id}"
                f"/storage/kv/namespaces/{self.config.kv_namespace_id}/values/{subdomain}"
            )

            response = await self.client.put(url, content=json.dumps(kv_value))

            if response.status_code not in (200, 201):
                error_msg = f"Failed to update KV: {response.status_code}"
                return SubdomainResult(
                    success=False, subdomain=subdomain, full_domain=full_domain, error=error_msg,
                )

            logger.info(f"Updated subdomain route: {subdomain} -> {cloud_run_url}")

            return SubdomainResult(
                success=True,
                subdomain=subdomain,
                full_domain=full_domain,
                status=SubdomainStatus.ACTIVE,
                cloud_run_url=cloud_run_url,
            )

        except Exception as e:
            logger.exception(f"Failed to update subdomain: {subdomain}")
            return SubdomainResult(
                success=False, subdomain=subdomain, full_domain=full_domain, error=str(e),
            )

    async def delete_subdomain(self, subdomain: str) -> SubdomainResult:
        """Delete a subdomain route from KV."""
        subdomain = subdomain.lower().strip()
        full_domain = f"{subdomain}.{self.config.base_domain}"

        try:
            url = (
                f"{self.BASE_URL}/accounts/{self.config.account_id}"
                f"/storage/kv/namespaces/{self.config.kv_namespace_id}/values/{subdomain}"
            )

            response = await self.client.delete(url)

            if response.status_code not in (200, 204):
                error_msg = f"Failed to delete from KV: {response.status_code}"
                return SubdomainResult(
                    success=False, subdomain=subdomain, full_domain=full_domain, error=error_msg,
                )

            logger.info(f"Deleted subdomain route: {subdomain}")

            return SubdomainResult(
                success=True,
                subdomain=subdomain,
                full_domain=full_domain,
                status=SubdomainStatus.DELETED,
            )

        except Exception as e:
            logger.exception(f"Failed to delete subdomain: {subdomain}")
            return SubdomainResult(
                success=False, subdomain=subdomain, full_domain=full_domain, error=str(e),
            )

    async def get_subdomain(self, subdomain: str) -> SubdomainResult:
        """Get subdomain details from KV."""
        subdomain = subdomain.lower().strip()
        full_domain = f"{subdomain}.{self.config.base_domain}"

        try:
            data = await self._get_kv_value(subdomain)

            if not data:
                return SubdomainResult(
                    success=False, subdomain=subdomain, full_domain=full_domain,
                    error="Subdomain not found",
                )

            return SubdomainResult(
                success=True,
                subdomain=subdomain,
                full_domain=full_domain,
                status=SubdomainStatus.ACTIVE,
                cloud_run_url=data.get("cloud_run_url"),
            )

        except Exception as e:
            logger.exception(f"Failed to get subdomain: {subdomain}")
            return SubdomainResult(
                success=False, subdomain=subdomain, full_domain=full_domain, error=str(e),
            )

    async def check_availability(self, subdomain: str) -> tuple[bool, str | None]:
        """Check if a subdomain is available."""
        subdomain = subdomain.lower().strip()

        is_valid, error = validate_subdomain(subdomain)
        if not is_valid:
            return False, error

        existing = await self._get_kv_value(subdomain)
        if existing:
            return False, f"'{subdomain}' is already taken"

        return True, None

    async def list_subdomains(
        self,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[SubdomainResult], int]:
        """List all subdomains from KV."""
        try:
            url = (
                f"{self.BASE_URL}/accounts/{self.config.account_id}"
                f"/storage/kv/namespaces/{self.config.kv_namespace_id}/keys"
            )

            params = {
                "limit": per_page,
                "cursor": None if page == 1 else f"page_{page}",
            }

            response = await self.client.get(url, params=params)
            data = response.json()

            if not data.get("success"):
                return [], 0

            results = data.get("result", [])
            result_info = data.get("result_info", {})
            total_count = result_info.get("count", len(results))

            subdomains = []
            for item in results:
                key = item.get("name", "")
                value = await self._get_kv_value(key)
                if value:
                    subdomains.append(
                        SubdomainResult(
                            success=True,
                            subdomain=key,
                            full_domain=f"{key}.{self.config.base_domain}",
                            status=SubdomainStatus.ACTIVE,
                            cloud_run_url=value.get("cloud_run_url"),
                        )
                    )

            return subdomains, total_count

        except Exception as e:
            logger.exception("Failed to list subdomains")
            return [], 0

    async def _get_kv_value(self, key: str) -> dict[str, Any] | None:
        """Get a value from KV."""
        url = (
            f"{self.BASE_URL}/accounts/{self.config.account_id}"
            f"/storage/kv/namespaces/{self.config.kv_namespace_id}/values/{key}"
        )

        response = await self.client.get(url)

        if response.status_code == 404:
            return None

        if response.status_code != 200:
            return None

        try:
            return response.json()
        except Exception:
            return {"cloud_run_url": response.text}


# Convenience functions
async def create_subdomain_route(
    subdomain: str,
    cloud_run_url: str,
    project_id: str | None = None,
    user_id: str | None = None,
) -> SubdomainResult:
    """Create a subdomain route using default config from environment."""
    config = CloudflareKVConfig.from_env()
    service = CloudflareKVService(config)
    try:
        return await service.create_subdomain(subdomain, cloud_run_url, project_id, user_id)
    finally:
        await service.close()


async def check_subdomain_availability(subdomain: str) -> tuple[bool, str | None]:
    """Check subdomain availability using default config from environment."""
    config = CloudflareKVConfig.from_env()
    service = CloudflareKVService(config)
    try:
        return await service.check_availability(subdomain)
    finally:
        await service.close()
