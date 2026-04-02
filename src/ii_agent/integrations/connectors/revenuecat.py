"""RevenueCat connector implementation."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import get_settings
from ii_agent.integrations.connectors.models import Connector, ConnectorType

from .base import BaseConnector, ConnectorData

logger = logging.getLogger(__name__)

REVENUECAT_AUTH_BASE = "https://api.revenuecat.com/oauth2"
REVENUECAT_API_BASE = "https://api.revenuecat.com/v2"
REVENUECAT_SCOPES = [
    "project_configuration:projects:read_write",
    "project_configuration:apps:read_write",
    "project_configuration:products:read_write",
    "project_configuration:entitlements:read_write",
    "project_configuration:offerings:read_write",
    "project_configuration:packages:read_write",
    "charts_metrics:overview:read",
    "charts_metrics:charts:read",
]


def _mask_exchange_payload(payload: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for key, value in payload.items():
        if key in {"client_secret", "code", "code_verifier"} and value:
            masked[key] = f"{value[:8]}..."
        else:
            masked[key] = value
    return masked


class RevenueCatConnector(BaseConnector):
    """RevenueCat OAuth connector for dashboard API access."""

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)

    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.REVENUECAT

    @property
    def scopes(self) -> list[str]:
        return REVENUECAT_SCOPES

    @staticmethod
    def generate_pkce() -> tuple[str, str]:
        """Generate PKCE code_verifier and code_challenge (S256)."""
        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return code_verifier, code_challenge

    async def get_auth_url(
        self,
        state: str,
        redirect_uri: Optional[str] = None,
        code_challenge: Optional[str] = None,
    ) -> str:
        settings = get_settings()
        if not settings.oauth.has_revenuecat_oauth():
            raise ValueError("RevenueCat integration is not configured")

        effective_redirect_uri = redirect_uri or settings.oauth.revenuecat_redirect_uri
        params = {
            "response_type": "code",
            "client_id": settings.oauth.revenuecat_client_id,
            "redirect_uri": "https://agent.ii.inc/auth/oauth/revenuecat/callback",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return f"{REVENUECAT_AUTH_BASE}/authorize?{urllib.parse.urlencode(params)}"

    async def handle_callback(
        self,
        code: str,
        state: str,  # noqa: ARG002 - kept for interface parity
        redirect_uri: Optional[str] = None,
        code_verifier: Optional[str] = None,
    ) -> ConnectorData:
        effective_redirect_uri = redirect_uri or get_settings().oauth.revenuecat_redirect_uri
        token_data = await self._exchange_token(
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "https://agent.ii.inc/auth/oauth/revenuecat/callback",
                **({"code_verifier": code_verifier} if code_verifier else {}),
            }
        )
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("RevenueCat OAuth response did not include an access token")

        token_expiry = _build_expiry(token_data.get("expires_in"))
        projects = await self.list_projects(access_token)
        metadata = {
            "scopes_granted": (token_data.get("scope") or "").split(),
            "project_count": len(projects),
            "projects": [_project_summary(project) for project in projects[:10]],
            "token_type": token_data.get("token_type"),
        }

        return ConnectorData(
            access_token=access_token,
            refresh_token=token_data.get("refresh_token"),
            token_expiry=token_expiry,
            metadata=metadata,
        )

    async def refresh_access_token(self, connector: Connector) -> ConnectorData:
        if not connector.refresh_token:
            raise ValueError("No RevenueCat refresh token available")

        token_data = await self._exchange_token(
            data={
                "grant_type": "refresh_token",
                "refresh_token": connector.refresh_token,
            }
        )
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("RevenueCat refresh response did not include an access token")

        metadata = dict(connector.connector_metadata or {})
        if token_data.get("scope"):
            metadata["scopes_granted"] = token_data["scope"].split()
        if token_data.get("token_type"):
            metadata["token_type"] = token_data["token_type"]

        return ConnectorData(
            access_token=access_token,
            refresh_token=token_data.get("refresh_token") or connector.refresh_token,
            token_expiry=_build_expiry(token_data.get("expires_in")),
            metadata=metadata,
        )

    async def validate_token(self, access_token: str) -> bool:
        try:
            await self.api_request(access_token, "GET", "/projects")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to validate RevenueCat token: %s", exc)
            return False

    async def revoke_access(self, connector: Connector) -> bool:  # noqa: ARG002
        # RevenueCat documents dashboard revocation via the connected apps UI.
        return True

    async def api_request(
        self,
        access_token: str,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> Any:
        url = path if path.startswith("http") else f"{REVENUECAT_API_BASE}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

    async def api_request_candidates(
        self,
        access_token: str,
        method: str,
        candidates: list[dict[str, Any]],
    ) -> Any:
        errors: list[str] = []
        last_exc: Optional[Exception] = None

        for candidate in candidates:
            path = candidate["path"]
            try:
                return await self.api_request(
                    access_token,
                    method,
                    path,
                    params=candidate.get("params"),
                    json=candidate.get("json"),
                )
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code != 404:
                    raise
                errors.append(path)

        if last_exc:
            raise last_exc

        raise ValueError(
            "RevenueCat API endpoint not found. Tried: "
            + ", ".join(errors or [candidate["path"] for candidate in candidates])
        )

    async def list_projects(self, access_token: str) -> list[dict[str, Any]]:
        payload = await self.api_request(access_token, "GET", "/projects")
        return _extract_collection(payload)

    async def list_apps(
        self,
        access_token: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self.api_request(access_token, "GET", f"/projects/{project_id}/apps")
        return _extract_collection(payload)

    async def list_entitlements(
        self,
        access_token: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self.api_request(
            access_token,
            "GET",
            f"/projects/{project_id}/entitlements",
        )
        return _extract_collection(payload)

    async def list_offerings(
        self,
        access_token: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self.api_request(
            access_token,
            "GET",
            f"/projects/{project_id}/offerings",
        )
        return _extract_collection(payload)

    async def list_products(
        self,
        access_token: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self.api_request(
            access_token,
            "GET",
            f"/projects/{project_id}/products",
        )
        return _extract_collection(payload)

    async def list_packages(
        self,
        access_token: str,
        project_id: str,
        offering_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self.api_request_candidates(
            access_token,
            "GET",
            [
                {
                    "path": f"/projects/{project_id}/offerings/{offering_id}/packages",
                },
                {
                    "path": f"/projects/{project_id}/packages",
                    "params": {"offering_id": offering_id},
                },
            ],
        )
        return _extract_collection(payload)

    async def create_app(
        self,
        access_token: str,
        project_id: str,
        *,
        name: str,
        app_type: str,
        bundle_id: Optional[str] = None,
        package_name: Optional[str] = None,
    ) -> dict[str, Any]:
        payload = await self.api_request(
            access_token,
            "POST",
            f"/projects/{project_id}/apps",
            json={
                "name": name,
                "type": app_type,
                **({"bundle_id": bundle_id} if bundle_id else {}),
                **({"package_name": package_name} if package_name else {}),
            },
        )
        return _extract_resource(payload)

    async def update_app(
        self,
        access_token: str,
        project_id: str,
        app_id: str,
        *,
        name: Optional[str] = None,
        bundle_id: Optional[str] = None,
        package_name: Optional[str] = None,
    ) -> dict[str, Any]:
        payload = await self.api_request(
            access_token,
            "PATCH",
            f"/projects/{project_id}/apps/{app_id}",
            json={
                **({"name": name} if name else {}),
                **({"bundle_id": bundle_id} if bundle_id else {}),
                **({"package_name": package_name} if package_name else {}),
            },
        )
        return _extract_resource(payload)

    async def create_product(
        self,
        access_token: str,
        project_id: str,
        *,
        store_identifier: str,
        product_type: str,
        app_id: str,
        display_name: Optional[str] = None,
    ) -> dict[str, Any]:
        payload = await self.api_request(
            access_token,
            "POST",
            f"/projects/{project_id}/products",
            json={
                "store_identifier": store_identifier,
                "type": product_type,
                "app_id": app_id,
                **({"display_name": display_name} if display_name else {}),
            },
        )
        return _extract_resource(payload)

    async def create_entitlement(
        self,
        access_token: str,
        project_id: str,
        *,
        lookup_key: str,
        display_name: str,
    ) -> dict[str, Any]:
        payload = await self.api_request(
            access_token,
            "POST",
            f"/projects/{project_id}/entitlements",
            json={
                "lookup_key": lookup_key,
                "display_name": display_name,
            },
        )
        return _extract_resource(payload)

    async def update_entitlement(
        self,
        access_token: str,
        project_id: str,
        entitlement_id: str,
        *,
        display_name: str,
    ) -> dict[str, Any]:
        payload = await self.api_request(
            access_token,
            "PATCH",
            f"/projects/{project_id}/entitlements/{entitlement_id}",
            json={"display_name": display_name},
        )
        return _extract_resource(payload)

    async def get_products_from_entitlement(
        self,
        access_token: str,
        project_id: str,
        entitlement_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self.api_request_candidates(
            access_token,
            "GET",
            [
                {
                    "path": f"/projects/{project_id}/entitlements/{entitlement_id}/products",
                },
            ],
        )
        return _extract_collection(payload)

    async def attach_products_to_entitlement(
        self,
        access_token: str,
        project_id: str,
        entitlement_id: str,
        product_ids: list[str],
    ) -> dict[str, Any]:
        payload = await self.api_request_candidates(
            access_token,
            "POST",
            [
                {
                    "path": f"/projects/{project_id}/entitlements/{entitlement_id}/attach_products",
                    "json": {"product_ids": product_ids},
                },
                {
                    "path": f"/projects/{project_id}/entitlements/{entitlement_id}/products/attach",
                    "json": {"product_ids": product_ids},
                },
            ],
        )
        return _extract_resource(payload)

    async def create_offering(
        self,
        access_token: str,
        project_id: str,
        *,
        lookup_key: str,
        display_name: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload = await self.api_request(
            access_token,
            "POST",
            f"/projects/{project_id}/offerings",
            json={
                "lookup_key": lookup_key,
                "display_name": display_name,
                **({"metadata": metadata} if metadata else {}),
            },
        )
        return _extract_resource(payload)

    async def update_offering(
        self,
        access_token: str,
        project_id: str,
        offering_id: str,
        *,
        display_name: Optional[str] = None,
        is_current: Optional[bool] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload = await self.api_request(
            access_token,
            "PATCH",
            f"/projects/{project_id}/offerings/{offering_id}",
            json={
                **({"display_name": display_name} if display_name else {}),
                **({"is_current": is_current} if is_current is not None else {}),
                **({"metadata": metadata} if metadata is not None else {}),
            },
        )
        return _extract_resource(payload)

    async def create_package(
        self,
        access_token: str,
        project_id: str,
        offering_id: str,
        *,
        lookup_key: str,
        display_name: str,
        position: Optional[int] = None,
    ) -> dict[str, Any]:
        payload = await self.api_request_candidates(
            access_token,
            "POST",
            [
                {
                    "path": f"/projects/{project_id}/offerings/{offering_id}/packages",
                    "json": {
                        "lookup_key": lookup_key,
                        "display_name": display_name,
                        **({"position": position} if position is not None else {}),
                    },
                },
                {
                    "path": f"/projects/{project_id}/packages",
                    "json": {
                        "offering_id": offering_id,
                        "lookup_key": lookup_key,
                        "display_name": display_name,
                        **({"position": position} if position is not None else {}),
                    },
                },
            ],
        )
        return _extract_resource(payload)

    async def get_products_from_package(
        self,
        access_token: str,
        project_id: str,
        package_id: str,
        *,
        offering_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        candidates = [
            {
                "path": f"/projects/{project_id}/packages/{package_id}/products",
            }
        ]
        if offering_id:
            candidates.append(
                {
                    "path": f"/projects/{project_id}/offerings/{offering_id}/packages/{package_id}/products",
                }
            )

        payload = await self.api_request_candidates(access_token, "GET", candidates)
        return _extract_collection(payload)

    async def attach_products_to_package(
        self,
        access_token: str,
        project_id: str,
        package_id: str,
        products: list[dict[str, str]],
    ) -> dict[str, Any]:
        payload = await self.api_request_candidates(
            access_token,
            "POST",
            [
                {
                    "path": f"/projects/{project_id}/packages/{package_id}/attach_products",
                    "json": {"products": products},
                },
                {
                    "path": f"/projects/{project_id}/packages/{package_id}/products/attach",
                    "json": {"products": products},
                },
            ],
        )
        return _extract_resource(payload)

    async def list_public_api_keys(
        self,
        access_token: str,
        project_id: str,
        app_id: str,
    ) -> list[dict[str, Any]]:
        candidate_paths = [
            f"/projects/{project_id}/apps/{app_id}/public_api_keys",
            f"/projects/{project_id}/apps/{app_id}/public-api-keys",
        ]
        errors: list[str] = []
        for path in candidate_paths:
            try:
                payload = await self.api_request(access_token, "GET", path)
                return _extract_collection(payload)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                errors.append(path)

        logger.warning(
            "RevenueCat public API key endpoint not found for app %s. Tried: %s",
            app_id,
            ", ".join(errors),
        )
        return []

    async def _exchange_token(self, *, data: dict[str, str]) -> dict[str, Any]:
        settings = get_settings()
        if not settings.oauth.has_revenuecat_oauth():
            raise ValueError("RevenueCat integration is not configured")

        payload = {
            "client_id": settings.oauth.revenuecat_client_id,
            **{key: value for key, value in data.items() if value is not None},
        }

        if settings.oauth.revenuecat_client_secret:
            payload["client_secret"] = settings.oauth.revenuecat_client_secret

        logger.info(
            "RevenueCat token exchange payload=%s",
            _mask_exchange_payload(payload),
        )
        logger.debug(
            "RevenueCat token exchange grant_type=%s auth_method=%s has_code_verifier=%s redirect_uri=%s",
            payload.get("grant_type"),
            "client_secret_post" if settings.oauth.revenuecat_client_secret else "none",
            "code_verifier" in payload,
            payload.get("redirect_uri"),
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{REVENUECAT_AUTH_BASE}/token",
                data=payload,
                headers={"Accept": "application/json"},
            )
            if response.status_code >= 400:
                logger.error(
                    "RevenueCat token exchange failed: status=%s body=%s",
                    response.status_code,
                    response.text,
                )
            response.raise_for_status()
            token_data = response.json()
            if token_data.get("error"):
                raise ValueError(token_data.get("error_description") or token_data["error"])
            return token_data


def _build_expiry(expires_in: Any) -> Optional[datetime]:
    if expires_in in (None, ""):
        return None
    try:
        return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    except (TypeError, ValueError):
        return None


def _extract_collection(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extract_resource(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        for key in ("data", "item", "result"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
    return {}


def _project_summary(project: dict[str, Any]) -> dict[str, Any]:
    attrs = project.get("attributes") if isinstance(project.get("attributes"), dict) else {}
    return {
        "id": project.get("id") or attrs.get("id"),
        "name": attrs.get("name") or project.get("name"),
    }
