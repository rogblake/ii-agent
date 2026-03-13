"""RevenueCat helper tool for mobile subscription setup."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, Optional

from ii_agent.core.config.settings import get_settings
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.agent.sandboxes.env_sync_service import SandboxEnvSyncService
from ii_agent.agent.sandboxes.dependencies import get_sandbox_repository
from ii_agent.agent.runtime.tools.base import BaseAgentTool, ToolResult
from ii_agent.integrations.connectors.revenuecat import RevenueCatConnector
from ii_agent.sessions.dependencies import get_session_repository

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall

NAME = "revenuecat"
DISPLAY_NAME = "RevenueCat"
DESCRIPTION = """Inspect the connected RevenueCat account and prepare mobile-app RevenueCat configuration.

Use this for subscription, paywall, trial, or in-app purchase work in React Native / Expo apps.

Supported actions:
- `list_projects`: list RevenueCat projects available to the connected account.
- `list_apps`: list apps inside a RevenueCat project.
- `list_entitlements`: list entitlements inside a project.
- `list_offerings`: list offerings inside a project.
- `list_packages`: list packages inside a RevenueCat offering.
- `list_products`: list products inside a project.
- `configure_mobile_app`: resolve platform app IDs + public SDK keys, then save Expo env vars for the current project.
- `plan_mobile_catalog`: dry-run the RevenueCat resources needed for a mobile subscription catalog.
- `provision_mobile_catalog`: create/update the RevenueCat resources for a mobile subscription catalog, then optionally sync Expo env vars.
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "list_projects",
                "list_apps",
                "list_entitlements",
                "list_offerings",
                "list_packages",
                "list_products",
                "configure_mobile_app",
                "plan_mobile_catalog",
                "provision_mobile_catalog",
            ],
            "description": "RevenueCat action to run.",
        },
        "project_id": {
            "type": "string",
            "description": "RevenueCat project ID. Required for project-scoped actions when more than one project is available.",
        },
        "offering_id": {
            "type": "string",
            "description": "RevenueCat offering identifier. Used by list_packages and can also be saved into Expo env vars.",
        },
        "project_directory": {
            "type": "string",
            "description": "Project root path where Expo env vars should be synced for configure_mobile_app.",
        },
        "ios_bundle_id": {
            "type": "string",
            "description": "iOS bundle identifier to match an existing RevenueCat app.",
        },
        "android_package_name": {
            "type": "string",
            "description": "Android package name to match an existing RevenueCat app.",
        },
        "ios_app_id": {
            "type": "string",
            "description": "Explicit RevenueCat iOS app ID to use instead of bundle-id matching.",
        },
        "android_app_id": {
            "type": "string",
            "description": "Explicit RevenueCat Android app ID to use instead of package-name matching.",
        },
        "entitlement_id": {
            "type": "string",
            "description": "RevenueCat entitlement identifier to save into Expo env vars.",
        },
        "create_missing_apps": {
            "type": "boolean",
            "description": "Allow provisioning to create missing RevenueCat iOS/Android apps when bundle/package identifiers are provided.",
        },
        "ios_app_name": {
            "type": "string",
            "description": "Display name to use when creating a missing iOS RevenueCat app.",
        },
        "android_app_name": {
            "type": "string",
            "description": "Display name to use when creating a missing Android RevenueCat app.",
        },
        "entitlement_lookup_key": {
            "type": "string",
            "description": "Lookup key for the RevenueCat entitlement to ensure.",
        },
        "entitlement_display_name": {
            "type": "string",
            "description": "Display name for the RevenueCat entitlement to ensure.",
        },
        "offering_lookup_key": {
            "type": "string",
            "description": "Lookup key for the RevenueCat offering to ensure.",
        },
        "offering_display_name": {
            "type": "string",
            "description": "Display name for the RevenueCat offering to ensure.",
        },
        "offering_metadata": {
            "type": "object",
            "description": "Optional RevenueCat offering metadata to set when creating or updating the offering.",
            "additionalProperties": True,
        },
        "is_current_offering": {
            "type": "boolean",
            "description": "Whether the ensured offering should be marked as the current offering.",
        },
        "packages": {
            "type": "array",
            "description": "Packages to ensure inside the offering.",
            "items": {
                "type": "object",
                "properties": {
                    "lookup_key": {
                        "type": "string",
                        "description": "RevenueCat package lookup key, for example $rc_monthly.",
                    },
                    "display_name": {
                        "type": "string",
                        "description": "Display name for the package.",
                    },
                    "position": {
                        "type": "integer",
                        "description": "Optional sort position for the package.",
                    },
                    "products": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "store_identifier": {
                                    "type": "string",
                                    "description": "App Store / Play Store product identifier.",
                                },
                                "platform": {
                                    "type": "string",
                                    "enum": ["ios", "android"],
                                    "description": "Mobile platform for the product.",
                                },
                                "type": {
                                    "type": "string",
                                    "description": "RevenueCat product type, such as subscription or consumable.",
                                },
                                "display_name": {
                                    "type": "string",
                                    "description": "Optional RevenueCat display name for the product.",
                                },
                                "app_id": {
                                    "type": "string",
                                    "description": "Explicit RevenueCat app ID for this product.",
                                },
                                "app_identifier": {
                                    "type": "string",
                                    "description": "Bundle ID or package name used to resolve the RevenueCat app for this product.",
                                },
                                "eligibility_criteria": {
                                    "type": "string",
                                    "description": "Package product eligibility criteria. Defaults to 'all'.",
                                },
                            },
                            "required": ["store_identifier", "platform", "type"],
                        },
                    },
                },
                "required": ["lookup_key", "products"],
            },
        },
    },
    "required": ["action"],
}


class RevenueCatTool(BaseAgentTool):
    """Expose connected RevenueCat data to the mobile-app agent."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
    instructions = """
Use `revenuecat` before wiring subscriptions or paywalls in mobile apps.
- If RevenueCat is not connected, tell the user to connect it in Settings > Account.
- For `configure_mobile_app`, pass the Expo project directory plus bundle/package identifiers from the app config.
- For `plan_mobile_catalog`, always provide the desired entitlement, offering, and package/product structure before editing app purchase code.
- For `provision_mobile_catalog`, prefer bundle/package identifiers that already match existing RevenueCat apps. Only set create_missing_apps when app creation is intentional.
- After the tool saves Expo env vars, install `react-native-purchases` and `react-native-purchases-ui` and wire the purchase flow against those env vars.
"""

    def __init__(self) -> None:
        self._user_id: Optional[str] = None
        self._session_id: Optional[str] = None

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:  # noqa: ARG002
        self._user_id = str(getattr(agent, "user_id", "")) or None
        session_id = getattr(agent, "session_id", None)
        self._session_id = str(session_id) if session_id is not None else None

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        action = tool_input.get("action")
        if not action:
            return _error_result("Missing required RevenueCat action.")

        if not self._user_id:
            return _error_result("No user context available for RevenueCat tool.")

        try:
            async with get_db_session_local() as db:
                connector = RevenueCatConnector(db)
                access_token = await connector.get_valid_token(self._user_id)
                if not access_token:
                    return _error_result(
                        "RevenueCat is not connected for this user. Ask the user to connect RevenueCat in Settings > Account first."
                    )

                if action == "list_projects":
                    projects = await connector.list_projects(access_token)
                    payload = {"projects": [_project_item(project) for project in projects]}
                    return _success_result(payload)

                project_id = tool_input.get("project_id")
                if action == "configure_mobile_app":
                    payload = await self._configure_mobile_app(
                        connector=connector,
                        access_token=access_token,
                        tool_input=tool_input,
                    )
                    return _success_result(payload)

                if action in {"plan_mobile_catalog", "provision_mobile_catalog"}:
                    payload = await self._plan_or_provision_mobile_catalog(
                        connector=connector,
                        access_token=access_token,
                        tool_input=tool_input,
                        apply_changes=(action == "provision_mobile_catalog"),
                    )
                    return _success_result(payload)

                resolved_project_id, project_resolution = await _resolve_project_id(
                    connector=connector,
                    access_token=access_token,
                    requested_project_id=project_id,
                )
                if not resolved_project_id:
                    return _error_result(project_resolution["error"])

                if action == "list_apps":
                    apps = await connector.list_apps(access_token, resolved_project_id)
                    return _success_result(
                        {
                            "project": project_resolution["project"],
                            "apps": [_app_item(app) for app in apps],
                        }
                    )

                if action == "list_entitlements":
                    entitlements = await connector.list_entitlements(
                        access_token,
                        resolved_project_id,
                    )
                    return _success_result(
                        {
                            "project": project_resolution["project"],
                            "entitlements": [
                                _catalog_item(entitlement) for entitlement in entitlements
                            ],
                        }
                    )

                if action == "list_offerings":
                    offerings = await connector.list_offerings(
                        access_token,
                        resolved_project_id,
                    )
                    return _success_result(
                        {
                            "project": project_resolution["project"],
                            "offerings": [_catalog_item(offering) for offering in offerings],
                        }
                    )

                if action == "list_packages":
                    offering_id = tool_input.get("offering_id")
                    if not offering_id:
                        return _error_result("offering_id is required for list_packages.")
                    packages = await connector.list_packages(
                        access_token,
                        resolved_project_id,
                        offering_id,
                    )
                    return _success_result(
                        {
                            "project": project_resolution["project"],
                            "offering_id": offering_id,
                            "packages": [_package_item(package) for package in packages],
                        }
                    )

                if action == "list_products":
                    products = await connector.list_products(
                        access_token,
                        resolved_project_id,
                    )
                    return _success_result(
                        {
                            "project": project_resolution["project"],
                            "products": [_catalog_item(product) for product in products],
                        }
                    )

                return _error_result(f"Unsupported RevenueCat action: {action}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("RevenueCat tool failed")
            return _error_result(f"RevenueCat request failed: {exc}")

    async def _configure_mobile_app(
        self,
        *,
        connector: RevenueCatConnector,
        access_token: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        project_directory = tool_input.get("project_directory")
        if not project_directory:
            raise ValueError("project_directory is required for configure_mobile_app")

        resolved_project_id, project_resolution = await _resolve_project_id(
            connector=connector,
            access_token=access_token,
            requested_project_id=tool_input.get("project_id"),
        )
        if not resolved_project_id:
            raise ValueError(project_resolution["error"])

        apps = await connector.list_apps(access_token, resolved_project_id)
        ios_app = _resolve_app(
            apps=apps,
            explicit_app_id=tool_input.get("ios_app_id"),
            identifier=tool_input.get("ios_bundle_id"),
            platform="ios",
        )
        android_app = _resolve_app(
            apps=apps,
            explicit_app_id=tool_input.get("android_app_id"),
            identifier=tool_input.get("android_package_name"),
            platform="android",
        )

        if (
            tool_input.get("ios_bundle_id")
            and tool_input.get("ios_bundle_id") != ""
            and ios_app is None
        ):
            raise ValueError(
                "No RevenueCat iOS app matched the provided ios_bundle_id. "
                f"Available apps: {json.dumps([_app_item(app) for app in apps], indent=2)}"
            )
        if (
            tool_input.get("android_package_name")
            and tool_input.get("android_package_name") != ""
            and android_app is None
        ):
            raise ValueError(
                "No RevenueCat Android app matched the provided android_package_name. "
                f"Available apps: {json.dumps([_app_item(app) for app in apps], indent=2)}"
            )

        if ios_app is None and android_app is None:
            raise ValueError(
                "configure_mobile_app requires at least one matched iOS or Android RevenueCat app."
            )

        entitlement_id = tool_input.get("entitlement_id")
        offering_id = tool_input.get("offering_id")
        entitlements = await connector.list_entitlements(access_token, resolved_project_id)
        offerings = await connector.list_offerings(access_token, resolved_project_id)

        if not entitlement_id and len(entitlements) == 1:
            entitlement_id = _catalog_item(entitlements[0])["identifier"]
        if not offering_id and len(offerings) == 1:
            offering_id = _catalog_item(offerings[0])["identifier"]

        secrets: dict[str, str] = {}
        platforms: dict[str, Any] = {}

        if ios_app:
            ios_key = await _resolve_public_api_key(
                connector=connector,
                access_token=access_token,
                project_id=resolved_project_id,
                app=ios_app,
            )
            if not ios_key:
                raise ValueError(
                    f"Could not determine a RevenueCat public API key for iOS app {_app_item(ios_app)['id']}."
                )
            secrets["EXPO_PUBLIC_REVENUECAT_IOS_API_KEY"] = ios_key
            platforms["ios"] = {
                **_app_item(ios_app),
                "public_api_key": ios_key,
            }

        if android_app:
            android_key = await _resolve_public_api_key(
                connector=connector,
                access_token=access_token,
                project_id=resolved_project_id,
                app=android_app,
            )
            if not android_key:
                raise ValueError(
                    f"Could not determine a RevenueCat public API key for Android app {_app_item(android_app)['id']}."
                )
            secrets["EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY"] = android_key
            platforms["android"] = {
                **_app_item(android_app),
                "public_api_key": android_key,
            }

        if entitlement_id:
            secrets["EXPO_PUBLIC_REVENUECAT_ENTITLEMENT_ID"] = entitlement_id
        if offering_id:
            secrets["EXPO_PUBLIC_REVENUECAT_OFFERING_ID"] = offering_id

        persistence = await self._persist_project_secrets(
            project_directory=project_directory,
            secrets=secrets,
        )

        return {
            "project": project_resolution["project"],
            "project_directory": project_directory,
            "platforms": platforms,
            "env": secrets,
            "entitlement_id": entitlement_id,
            "offering_id": offering_id,
            "packages": [
                "react-native-purchases",
                "react-native-purchases-ui",
            ],
            "persistence": persistence,
            "next_steps": [
                "Install react-native-purchases and react-native-purchases-ui with Expo-compatible package versions.",
                "Configure Purchases with Platform.select using the EXPO_PUBLIC_REVENUECAT_* API keys.",
                "Use RevenueCat offerings / entitlements for the paywall and customer access checks.",
            ],
        }

    async def _plan_or_provision_mobile_catalog(
        self,
        *,
        connector: RevenueCatConnector,
        access_token: str,
        tool_input: dict[str, Any],
        apply_changes: bool,
    ) -> dict[str, Any]:
        desired = _parse_catalog_request(tool_input)
        resolved_project_id, project_resolution = await _resolve_project_id(
            connector=connector,
            access_token=access_token,
            requested_project_id=tool_input.get("project_id"),
        )
        if not resolved_project_id:
            raise ValueError(project_resolution["error"])

        apps = await connector.list_apps(access_token, resolved_project_id)
        entitlements = await connector.list_entitlements(access_token, resolved_project_id)
        offerings = await connector.list_offerings(access_token, resolved_project_id)
        products = await connector.list_products(access_token, resolved_project_id)

        operations: list[dict[str, Any]] = []
        conflicts: list[str] = []
        warnings: list[str] = []

        resolved_products = _resolve_catalog_products(
            apps=apps,
            desired=desired,
            create_missing_apps=bool(tool_input.get("create_missing_apps")),
            ios_bundle_id=tool_input.get("ios_bundle_id"),
            android_package_name=tool_input.get("android_package_name"),
            ios_app_name=tool_input.get("ios_app_name"),
            android_app_name=tool_input.get("android_app_name"),
        )
        conflicts.extend(resolved_products["conflicts"])

        resolved_product_lookup = {
            _product_request_signature(product["package_lookup_key"], product): product
            for product in resolved_products["products"]
        }
        for package in desired["packages"]:
            package["products"] = [
                dict(
                    resolved_product_lookup[
                        _product_request_signature(package["lookup_key"], product)
                    ]
                )
                for product in package["products"]
            ]

        planned_apps = resolved_products["planned_apps"]
        for planned_app in planned_apps.values():
            operations.append(
                {
                    "resource": "app",
                    "action": "create",
                    "platform": planned_app["platform"],
                    "identifier": planned_app["identifier"],
                    "name": planned_app["name"],
                }
            )

        entitlement = _find_catalog_item(
            entitlements,
            desired["entitlement_lookup_key"],
        )
        if entitlement is None:
            operations.append(
                {
                    "resource": "entitlement",
                    "action": "create",
                    "lookup_key": desired["entitlement_lookup_key"],
                    "display_name": desired["entitlement_display_name"],
                }
            )
        elif _catalog_item(entitlement)["name"] != desired["entitlement_display_name"]:
            operations.append(
                {
                    "resource": "entitlement",
                    "action": "update",
                    "lookup_key": desired["entitlement_lookup_key"],
                    "display_name": desired["entitlement_display_name"],
                }
            )

        offering = _find_catalog_item(
            offerings,
            desired["offering_lookup_key"],
        )
        if offering is None:
            operations.append(
                {
                    "resource": "offering",
                    "action": "create",
                    "lookup_key": desired["offering_lookup_key"],
                    "display_name": desired["offering_display_name"],
                }
            )
        else:
            desired_offering_changes = _offering_update_payload(
                offering,
                desired["offering_display_name"],
                desired["offering_metadata"],
                desired["is_current_offering"],
            )
            if desired_offering_changes:
                operations.append(
                    {
                        "resource": "offering",
                        "action": "update",
                        "lookup_key": desired["offering_lookup_key"],
                        **desired_offering_changes,
                    }
                )

        existing_packages: list[dict[str, Any]] = []
        if offering is not None:
            existing_packages = await connector.list_packages(
                access_token,
                resolved_project_id,
                _catalog_item(offering)["id"],
            )

        package_specs: list[dict[str, Any]] = []
        for package in desired["packages"]:
            existing_package = _find_catalog_item(existing_packages, package["lookup_key"])
            if existing_package is None:
                operations.append(
                    {
                        "resource": "package",
                        "action": "create",
                        "lookup_key": package["lookup_key"],
                        "display_name": package["display_name"],
                        "position": package["position"],
                    }
                )
            else:
                package_drift = _package_conflicts(existing_package, package)
                conflicts.extend(package_drift)

            package_specs.append(
                {
                    **package,
                    "existing": existing_package,
                }
            )

        existing_product_map = _build_existing_product_map(products)
        desired_product_map: dict[tuple[str, str, str], dict[str, Any]] = {}
        for product in resolved_products["products"]:
            key = (
                product["store_identifier"],
                product["platform"],
                product["app_key"],
            )
            if key in desired_product_map:
                continue

            existing_product = None
            if product.get("resolved_app"):
                existing_product = existing_product_map.get(
                    (
                        product["store_identifier"],
                        str(product["resolved_app"]["id"]),
                    )
                )

            desired_product_map[key] = {
                **product,
                "existing": existing_product,
            }
            if existing_product is None:
                operations.append(
                    {
                        "resource": "product",
                        "action": "create",
                        "store_identifier": product["store_identifier"],
                        "platform": product["platform"],
                        "type": product["type"],
                    }
                )
            else:
                product_conflicts = _product_conflicts(existing_product, product)
                conflicts.extend(product_conflicts)

        if entitlement is not None:
            try:
                entitlement_products = await connector.get_products_from_entitlement(
                    access_token,
                    resolved_project_id,
                    _catalog_item(entitlement)["id"],
                )
                entitlement_missing = _missing_entitlement_attachments(
                    entitlement_products,
                    [item for item in desired_product_map.values() if item["existing"] is not None],
                )
                if entitlement_missing:
                    operations.append(
                        {
                            "resource": "entitlement_products",
                            "action": "attach",
                            "lookup_key": desired["entitlement_lookup_key"],
                            "products": entitlement_missing,
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Could not inspect current entitlement attachments: {exc}")

        if offering is not None:
            for package in package_specs:
                existing_package = package["existing"]
                if existing_package is None:
                    continue
                try:
                    attached_products = await connector.get_products_from_package(
                        access_token,
                        resolved_project_id,
                        _catalog_item(existing_package)["id"],
                        offering_id=_catalog_item(offering)["id"],
                    )
                    missing_products, package_conflicts = _package_attachment_diff(
                        attached_products,
                        package["products"],
                        desired_product_map,
                    )
                    conflicts.extend(package_conflicts)
                    if missing_products:
                        operations.append(
                            {
                                "resource": "package_products",
                                "action": "attach",
                                "lookup_key": package["lookup_key"],
                                "products": missing_products,
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    warnings.append(
                        f"Could not inspect current package attachments for {package['lookup_key']}: {exc}"
                    )

        if conflicts:
            return {
                "project": project_resolution["project"],
                "mode": "apply" if apply_changes else "plan",
                "applied": False,
                "conflicts": conflicts,
                "warnings": warnings,
                "operations": operations,
            }

        if not apply_changes:
            env_preview = await self._build_mobile_env(
                connector=connector,
                access_token=access_token,
                project_id=resolved_project_id,
                ios_app=resolved_products["default_apps"].get("ios"),
                android_app=resolved_products["default_apps"].get("android"),
                entitlement_identifier=desired["entitlement_lookup_key"],
                offering_identifier=desired["offering_lookup_key"],
            )
            return {
                "project": project_resolution["project"],
                "mode": "plan",
                "applied": False,
                "conflicts": [],
                "warnings": warnings,
                "operations": operations,
                "env_preview": env_preview["env"],
            }

        for app_key, planned_app in planned_apps.items():
            created_app = await connector.create_app(
                access_token,
                resolved_project_id,
                name=planned_app["name"],
                app_type=planned_app["app_type"],
                bundle_id=planned_app.get("bundle_id"),
                package_name=planned_app.get("package_name"),
            )
            planned_app["app"] = created_app
            resolved_products["default_apps"][planned_app["platform"]] = created_app
            for product in desired_product_map.values():
                if product["app_key"] == app_key:
                    product["resolved_app"] = created_app

        if entitlement is None:
            entitlement = await connector.create_entitlement(
                access_token,
                resolved_project_id,
                lookup_key=desired["entitlement_lookup_key"],
                display_name=desired["entitlement_display_name"],
            )
        elif _catalog_item(entitlement)["name"] != desired["entitlement_display_name"]:
            entitlement = await connector.update_entitlement(
                access_token,
                resolved_project_id,
                _catalog_item(entitlement)["id"],
                display_name=desired["entitlement_display_name"],
            )

        if offering is None:
            offering = await connector.create_offering(
                access_token,
                resolved_project_id,
                lookup_key=desired["offering_lookup_key"],
                display_name=desired["offering_display_name"],
                metadata=desired["offering_metadata"],
            )
            if desired["is_current_offering"] is not None:
                offering = await connector.update_offering(
                    access_token,
                    resolved_project_id,
                    _catalog_item(offering)["id"],
                    is_current=desired["is_current_offering"],
                )
        else:
            desired_offering_changes = _offering_update_payload(
                offering,
                desired["offering_display_name"],
                desired["offering_metadata"],
                desired["is_current_offering"],
            )
            if desired_offering_changes:
                offering = await connector.update_offering(
                    access_token,
                    resolved_project_id,
                    _catalog_item(offering)["id"],
                    display_name=desired_offering_changes.get("display_name"),
                    metadata=desired_offering_changes.get("metadata"),
                    is_current=desired_offering_changes.get("is_current"),
                )

        existing_packages = await connector.list_packages(
            access_token,
            resolved_project_id,
            _catalog_item(offering)["id"],
        )

        for product in desired_product_map.values():
            if product["existing"] is not None:
                continue
            resolved_app = product.get("resolved_app")
            if not resolved_app:
                raise ValueError(
                    f"Could not resolve a RevenueCat app for product {product['store_identifier']}."
                )
            created_product = await connector.create_product(
                access_token,
                resolved_project_id,
                store_identifier=product["store_identifier"],
                product_type=product["type"],
                app_id=str(_catalog_item(resolved_app)["id"]),
                display_name=product.get("display_name"),
            )
            product["existing"] = created_product

        refreshed_packages: dict[str, dict[str, Any]] = {
            _catalog_item(package)["identifier"]: package for package in existing_packages
        }
        for package in package_specs:
            existing_package = refreshed_packages.get(package["lookup_key"])
            if existing_package is None:
                existing_package = await connector.create_package(
                    access_token,
                    resolved_project_id,
                    _catalog_item(offering)["id"],
                    lookup_key=package["lookup_key"],
                    display_name=package["display_name"],
                    position=package["position"],
                )
                refreshed_packages[package["lookup_key"]] = existing_package
            package["existing"] = existing_package

        entitlement_products = await connector.get_products_from_entitlement(
            access_token,
            resolved_project_id,
            _catalog_item(entitlement)["id"],
        )
        entitlement_missing_ids = _missing_entitlement_attachment_ids(
            entitlement_products,
            desired_product_map.values(),
        )
        if entitlement_missing_ids:
            await connector.attach_products_to_entitlement(
                access_token,
                resolved_project_id,
                _catalog_item(entitlement)["id"],
                entitlement_missing_ids,
            )

        for package in package_specs:
            existing_package = package["existing"]
            attached_products = await connector.get_products_from_package(
                access_token,
                resolved_project_id,
                _catalog_item(existing_package)["id"],
                offering_id=_catalog_item(offering)["id"],
            )
            missing_products, _ = _package_attachment_diff(
                attached_products,
                package["products"],
                desired_product_map,
            )
            if missing_products:
                await connector.attach_products_to_package(
                    access_token,
                    resolved_project_id,
                    _catalog_item(existing_package)["id"],
                    missing_products,
                )

        env_payload = await self._build_mobile_env(
            connector=connector,
            access_token=access_token,
            project_id=resolved_project_id,
            ios_app=resolved_products["default_apps"].get("ios"),
            android_app=resolved_products["default_apps"].get("android"),
            entitlement_identifier=desired["entitlement_lookup_key"],
            offering_identifier=desired["offering_lookup_key"],
        )

        persistence = None
        project_directory = tool_input.get("project_directory")
        if project_directory:
            persistence = await self._persist_project_secrets(
                project_directory=project_directory,
                secrets=env_payload["env"],
            )

        return {
            "project": project_resolution["project"],
            "mode": "apply",
            "applied": True,
            "conflicts": [],
            "warnings": warnings,
            "operations": operations,
            "resources": {
                "apps": env_payload["platforms"],
                "entitlement": {
                    "id": _catalog_item(entitlement)["id"],
                    "identifier": desired["entitlement_lookup_key"],
                    "name": desired["entitlement_display_name"],
                },
                "offering": {
                    "id": _catalog_item(offering)["id"],
                    "identifier": desired["offering_lookup_key"],
                    "name": desired["offering_display_name"],
                },
                "packages": [
                    _package_item(package["existing"]) for package in package_specs
                ],
            },
            "env": env_payload["env"],
            "persistence": persistence,
        }

    async def _build_mobile_env(
        self,
        *,
        connector: RevenueCatConnector,
        access_token: str,
        project_id: str,
        ios_app: Optional[dict[str, Any]],
        android_app: Optional[dict[str, Any]],
        entitlement_identifier: Optional[str],
        offering_identifier: Optional[str],
    ) -> dict[str, Any]:
        env: dict[str, str] = {}
        platforms: dict[str, Any] = {}

        if ios_app:
            ios_key = await _resolve_public_api_key(
                connector=connector,
                access_token=access_token,
                project_id=project_id,
                app=ios_app,
            )
            if ios_key:
                env["EXPO_PUBLIC_REVENUECAT_IOS_API_KEY"] = ios_key
                platforms["ios"] = {
                    **_app_item(ios_app),
                    "public_api_key": ios_key,
                }

        if android_app:
            android_key = await _resolve_public_api_key(
                connector=connector,
                access_token=access_token,
                project_id=project_id,
                app=android_app,
            )
            if android_key:
                env["EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY"] = android_key
                platforms["android"] = {
                    **_app_item(android_app),
                    "public_api_key": android_key,
                }

        if entitlement_identifier:
            env["EXPO_PUBLIC_REVENUECAT_ENTITLEMENT_ID"] = entitlement_identifier
        if offering_identifier:
            env["EXPO_PUBLIC_REVENUECAT_OFFERING_ID"] = offering_identifier

        return {
            "env": env,
            "platforms": platforms,
        }

    async def _persist_project_secrets(
        self,
        *,
        project_directory: str,
        secrets: dict[str, str],
    ) -> dict[str, Any]:
        if not self._session_id or not self._user_id or not self.dependencies:
            return {
                "saved_to_project": False,
                "synced_to_sandbox": False,
                "reason": "Missing session or dependency context.",
            }

        try:
            session_uuid = uuid.UUID(self._session_id)
        except ValueError:
            return {
                "saved_to_project": False,
                "synced_to_sandbox": False,
                "reason": "Invalid session identifier.",
            }

        async with get_db_session_local() as db:
            project = await self.dependencies.project_service.get_session_project_or_none(
                db,
                session_id=self._session_id,
                user_id=self._user_id,
            )
            if not project:
                return {
                    "saved_to_project": False,
                    "synced_to_sandbox": False,
                    "reason": "No project is linked to this session yet.",
                }

            existing_secrets = project.secrets_json or {}
            if not isinstance(existing_secrets, dict):
                existing_secrets = {}
            existing_secrets.update(secrets)

            await self.dependencies.project_service.update_session_project_secrets(
                db,
                project_id=project.id,
                secrets=existing_secrets,
            )

            env_sync_service = SandboxEnvSyncService(
                session_repo=get_session_repository(),
                sandbox_repo=get_sandbox_repository(),
                config=get_settings(),
            )
            synced = await env_sync_service.sync_env_files(
                db,
                session_uuid,
                secrets,
                project_path=project_directory or project.project_path,
            )

            return {
                "saved_to_project": True,
                "synced_to_sandbox": synced,
                "project_id": project.id,
            }


def _success_result(payload: dict[str, Any]) -> ToolResult:
    return ToolResult(
        llm_content=json.dumps(payload, indent=2),
        user_display_content=payload,
        is_error=False,
    )


def _error_result(message: str) -> ToolResult:
    return ToolResult(
        llm_content=message,
        user_display_content=message,
        is_error=True,
    )


async def _resolve_project_id(
    *,
    connector: RevenueCatConnector,
    access_token: str,
    requested_project_id: Optional[str],
) -> tuple[Optional[str], dict[str, Any]]:
    projects = await connector.list_projects(access_token)
    summaries = [_project_item(project) for project in projects]

    if requested_project_id:
        for summary in summaries:
            if summary["id"] == requested_project_id:
                return requested_project_id, {"project": summary}
        return None, {
            "error": (
                f"RevenueCat project '{requested_project_id}' was not found. "
                f"Available projects: {json.dumps(summaries, indent=2)}"
            )
        }

    if len(summaries) == 1:
        return summaries[0]["id"], {"project": summaries[0]}

    if not summaries:
        return None, {"error": "No RevenueCat projects were found for the connected account."}

    return None, {
        "error": (
            "Multiple RevenueCat projects are available. Call list_projects first and pass project_id explicitly. "
            f"Projects: {json.dumps(summaries, indent=2)}"
        )
    }


def _project_item(project: dict[str, Any]) -> dict[str, Any]:
    attrs = _attrs(project)
    return {
        "id": str(project.get("id") or attrs.get("id") or ""),
        "name": attrs.get("name") or project.get("name") or str(project.get("id") or ""),
    }


def _app_item(app: dict[str, Any]) -> dict[str, Any]:
    attrs = _attrs(app)
    return {
        "id": str(app.get("id") or attrs.get("id") or ""),
        "name": attrs.get("name") or app.get("name") or str(app.get("id") or ""),
        "platform": _normalize_platform(
            attrs.get("platform")
            or attrs.get("store")
            or app.get("platform")
            or app.get("store")
        ),
        "identifier": _app_identifier(app),
    }


def _catalog_item(item: dict[str, Any]) -> dict[str, Any]:
    attrs = _attrs(item)
    identifier = (
        attrs.get("lookup_key")
        or attrs.get("identifier")
        or attrs.get("name")
        or item.get("id")
    )
    return {
        "id": str(item.get("id") or attrs.get("id") or ""),
        "identifier": str(identifier or ""),
        "name": attrs.get("name") or str(identifier or ""),
    }


def _package_item(item: dict[str, Any]) -> dict[str, Any]:
    base = _catalog_item(item)
    base["position"] = _package_position(item)
    return base


def _parse_catalog_request(tool_input: dict[str, Any]) -> dict[str, Any]:
    packages_raw = tool_input.get("packages")
    if not isinstance(packages_raw, list) or not packages_raw:
        raise ValueError("packages is required and must be a non-empty array.")

    entitlement_lookup_key = _required_text(tool_input, "entitlement_lookup_key")
    offering_lookup_key = _required_text(tool_input, "offering_lookup_key")

    offering_metadata = tool_input.get("offering_metadata")
    if offering_metadata is not None and not isinstance(offering_metadata, dict):
        raise ValueError("offering_metadata must be an object when provided.")

    packages: list[dict[str, Any]] = []
    for index, package_raw in enumerate(packages_raw):
        if not isinstance(package_raw, dict):
            raise ValueError("Each RevenueCat package must be an object.")

        products_raw = package_raw.get("products")
        if not isinstance(products_raw, list) or not products_raw:
            raise ValueError(
                f"Package {package_raw.get('lookup_key') or index} must include a non-empty products array."
            )

        package_products: list[dict[str, Any]] = []
        for product_raw in products_raw:
            if not isinstance(product_raw, dict):
                raise ValueError("Each RevenueCat package product must be an object.")
            platform = _normalize_platform(product_raw.get("platform"))
            if platform not in {"ios", "android"}:
                raise ValueError(
                    f"Unsupported RevenueCat product platform '{product_raw.get('platform')}'."
                )
            package_products.append(
                {
                    "store_identifier": _required_text(product_raw, "store_identifier"),
                    "platform": platform,
                    "type": _required_text(product_raw, "type"),
                    "display_name": _optional_text(product_raw, "display_name"),
                    "app_id": _optional_text(product_raw, "app_id"),
                    "app_identifier": _optional_text(product_raw, "app_identifier"),
                    "eligibility_criteria": (
                        _optional_text(product_raw, "eligibility_criteria") or "all"
                    ),
                }
            )

        packages.append(
            {
                "lookup_key": _required_text(package_raw, "lookup_key"),
                "display_name": _optional_text(package_raw, "display_name")
                or _required_text(package_raw, "lookup_key"),
                "position": package_raw.get("position"),
                "products": package_products,
            }
        )

    return {
        "entitlement_lookup_key": entitlement_lookup_key,
        "entitlement_display_name": (
            _optional_text(tool_input, "entitlement_display_name") or entitlement_lookup_key
        ),
        "offering_lookup_key": offering_lookup_key,
        "offering_display_name": (
            _optional_text(tool_input, "offering_display_name") or offering_lookup_key
        ),
        "offering_metadata": offering_metadata,
        "is_current_offering": tool_input.get("is_current_offering"),
        "packages": packages,
    }


def _resolve_catalog_products(
    *,
    apps: list[dict[str, Any]],
    desired: dict[str, Any],
    create_missing_apps: bool,
    ios_bundle_id: Optional[str],
    android_package_name: Optional[str],
    ios_app_name: Optional[str],
    android_app_name: Optional[str],
) -> dict[str, Any]:
    apps_by_id = {_catalog_item(app)["id"]: app for app in apps if _catalog_item(app)["id"]}
    apps_by_platform_identifier = {
        (_app_item(app)["platform"], _app_item(app)["identifier"]): app
        for app in apps
        if _app_item(app)["platform"] and _app_item(app)["identifier"]
    }

    default_apps = {
        "ios": _resolve_default_platform_app(apps, "ios", ios_bundle_id),
        "android": _resolve_default_platform_app(apps, "android", android_package_name),
    }
    planned_apps: dict[str, dict[str, Any]] = {}
    conflicts: list[str] = []
    resolved_products: list[dict[str, Any]] = []

    for package in desired["packages"]:
        for product in package["products"]:
            platform = product["platform"]
            resolved_app = None
            app_key = ""

            if product.get("app_id"):
                resolved_app = apps_by_id.get(product["app_id"])
                if not resolved_app:
                    conflicts.append(
                        f"RevenueCat product {product['store_identifier']} references unknown app_id {product['app_id']}."
                    )
                    continue
            else:
                requested_identifier = (
                    product.get("app_identifier")
                    or (ios_bundle_id if platform == "ios" else android_package_name)
                )
                if requested_identifier:
                    resolved_app = apps_by_platform_identifier.get(
                        (platform, requested_identifier)
                    )
                elif default_apps.get(platform):
                    resolved_app = default_apps[platform]
                else:
                    platform_apps = [
                        app for app in apps if _app_item(app)["platform"] == platform
                    ]
                    if len(platform_apps) == 1:
                        resolved_app = platform_apps[0]

                if not resolved_app and create_missing_apps and requested_identifier:
                    app_key = f"planned:{platform}:{requested_identifier}"
                    if app_key not in planned_apps:
                        planned_apps[app_key] = {
                            "platform": platform,
                            "identifier": requested_identifier,
                            "name": (
                                ios_app_name
                                if platform == "ios" and ios_app_name
                                else android_app_name
                                if platform == "android" and android_app_name
                                else f"{requested_identifier} ({platform})"
                            ),
                            "app_type": "app_store" if platform == "ios" else "play_store",
                            "bundle_id": requested_identifier if platform == "ios" else None,
                            "package_name": (
                                requested_identifier if platform == "android" else None
                            ),
                        }
                elif not resolved_app:
                    conflicts.append(
                        f"Could not resolve a RevenueCat {platform} app for product {product['store_identifier']}. "
                        f"Provide app_id/app_identifier or the top-level {'ios_bundle_id' if platform == 'ios' else 'android_package_name'}."
                    )
                    continue

            if resolved_app:
                app_key = _catalog_item(resolved_app)["id"]
                if not default_apps.get(platform):
                    default_apps[platform] = resolved_app

            resolved_products.append(
                {
                    **product,
                    "package_lookup_key": package["lookup_key"],
                    "resolved_app": resolved_app,
                    "app_key": app_key,
                }
            )

    return {
        "products": resolved_products,
        "planned_apps": planned_apps,
        "default_apps": default_apps,
        "conflicts": conflicts,
    }


def _resolve_default_platform_app(
    apps: list[dict[str, Any]],
    platform: str,
    requested_identifier: Optional[str],
) -> Optional[dict[str, Any]]:
    platform_apps = [app for app in apps if _app_item(app)["platform"] == platform]
    if requested_identifier:
        for app in platform_apps:
            if _app_item(app)["identifier"] == requested_identifier:
                return app
        return None
    if len(platform_apps) == 1:
        return platform_apps[0]
    return None


def _find_catalog_item(
    items: list[dict[str, Any]],
    identifier: str,
) -> Optional[dict[str, Any]]:
    for item in items:
        summary = _catalog_item(item)
        if summary["identifier"] == identifier or summary["id"] == identifier:
            return item
    return None


def _offering_update_payload(
    offering: dict[str, Any],
    desired_display_name: str,
    desired_metadata: Optional[dict[str, Any]],
    desired_is_current: Optional[bool],
) -> dict[str, Any]:
    attrs = _attrs(offering)
    current_name = attrs.get("name") or attrs.get("display_name") or _catalog_item(offering)["name"]
    current_metadata = attrs.get("metadata") if isinstance(attrs.get("metadata"), dict) else None
    current_is_current = attrs.get("is_current")
    if current_is_current is None:
        current_is_current = attrs.get("current")

    updates: dict[str, Any] = {}
    if desired_display_name and current_name != desired_display_name:
        updates["display_name"] = desired_display_name
    if desired_metadata is not None and current_metadata != desired_metadata:
        updates["metadata"] = desired_metadata
    if desired_is_current is not None and current_is_current != desired_is_current:
        updates["is_current"] = desired_is_current
    return updates


def _package_conflicts(existing_package: dict[str, Any], desired_package: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
    existing = _package_item(existing_package)
    if existing["name"] != desired_package["display_name"]:
        conflicts.append(
            f"RevenueCat package {desired_package['lookup_key']} already exists with name '{existing['name']}' "
            f"but the request wants '{desired_package['display_name']}'."
        )
    desired_position = desired_package.get("position")
    if desired_position is not None and existing.get("position") not in (None, desired_position):
        conflicts.append(
            f"RevenueCat package {desired_package['lookup_key']} already exists at position {existing.get('position')} "
            f"but the request wants {desired_position}."
        )
    return conflicts


def _build_existing_product_map(
    products: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    product_map: dict[tuple[str, str], dict[str, Any]] = {}
    for product in products:
        store_identifier = _product_store_identifier(product)
        app_id = _product_app_id(product)
        if store_identifier and app_id:
            product_map[(store_identifier, app_id)] = product
    return product_map


def _product_conflicts(existing_product: dict[str, Any], desired_product: dict[str, Any]) -> list[str]:
    existing_type = _product_type(existing_product)
    if existing_type and existing_type != desired_product["type"]:
        return [
            f"RevenueCat product {desired_product['store_identifier']} already exists with type '{existing_type}' "
            f"but the request wants '{desired_product['type']}'."
        ]
    return []


def _missing_entitlement_attachments(
    attached_products: list[dict[str, Any]],
    desired_products: list[dict[str, Any]],
) -> list[str]:
    attached_ids = {
        _catalog_item(product)["id"]
        for product in attached_products
        if _catalog_item(product)["id"]
    }
    missing: list[str] = []
    for desired_product in desired_products:
        existing = desired_product["existing"]
        if existing is None:
            missing.append(desired_product["store_identifier"])
            continue
        product_id = _catalog_item(existing)["id"]
        if product_id and product_id not in attached_ids:
            missing.append(desired_product["store_identifier"])
    return missing


def _missing_entitlement_attachment_ids(
    attached_products: list[dict[str, Any]],
    desired_products: Any,
) -> list[str]:
    attached_ids = {
        _catalog_item(product)["id"]
        for product in attached_products
        if _catalog_item(product)["id"]
    }
    missing: list[str] = []
    for desired_product in desired_products:
        existing = desired_product["existing"]
        if existing is None:
            continue
        product_id = _catalog_item(existing)["id"]
        if product_id and product_id not in attached_ids:
            missing.append(product_id)
    return missing


def _package_attachment_diff(
    attached_products: list[dict[str, Any]],
    desired_products: list[dict[str, Any]],
    desired_product_map: dict[tuple[str, str, str], dict[str, Any]],
) -> tuple[list[dict[str, str]], list[str]]:
    attached_by_id = {
        _catalog_item(product)["id"]: product
        for product in attached_products
        if _catalog_item(product)["id"]
    }
    missing_products: list[dict[str, str]] = []
    conflicts: list[str] = []

    for desired_product in desired_products:
        key = (
            desired_product["store_identifier"],
            desired_product["platform"],
            desired_product["app_key"],
        )
        resolved_product = desired_product_map[key]
        existing = resolved_product["existing"]
        if existing is None:
            continue
        product_id = _catalog_item(existing)["id"]
        if not product_id:
            continue

        attached = attached_by_id.get(product_id)
        if attached is None:
            missing_products.append(
                {
                    "product_id": product_id,
                    "eligibility_criteria": desired_product["eligibility_criteria"],
                }
            )
            continue

        attached_eligibility = _package_product_eligibility(attached)
        if (
            attached_eligibility
            and attached_eligibility != desired_product["eligibility_criteria"]
        ):
            conflicts.append(
                f"RevenueCat package attachment for {desired_product['store_identifier']} already exists with "
                f"eligibility '{attached_eligibility}' but the request wants '{desired_product['eligibility_criteria']}'."
            )

    return missing_products, conflicts


def _product_request_signature(
    package_lookup_key: str,
    product: dict[str, Any],
) -> tuple[str, str, str, str, str]:
    return (
        package_lookup_key,
        product["store_identifier"],
        product["platform"],
        product.get("app_id") or "",
        product.get("app_identifier") or "",
    )


def _resolve_app(
    *,
    apps: list[dict[str, Any]],
    explicit_app_id: Optional[str],
    identifier: Optional[str],
    platform: str,
) -> Optional[dict[str, Any]]:
    normalized_platform = _normalize_platform(platform)

    if explicit_app_id:
        for app in apps:
            if str(app.get("id")) == explicit_app_id:
                return app
        return None

    if identifier:
        for app in apps:
            if _normalize_platform(_app_item(app)["platform"]) != normalized_platform:
                continue
            if _app_identifier(app) == identifier:
                return app

    return None


async def _resolve_public_api_key(
    *,
    connector: RevenueCatConnector,
    access_token: str,
    project_id: str,
    app: dict[str, Any],
) -> Optional[str]:
    app_id = str(app.get("id") or "")
    key = _extract_public_api_key(app)
    if key:
        return key

    if not app_id:
        return None

    key_entries = await connector.list_public_api_keys(access_token, project_id, app_id)
    for entry in key_entries:
        extracted = _extract_public_api_key(entry)
        if extracted:
            return extracted
    return None


def _attrs(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes")
    return attributes if isinstance(attributes, dict) else {}


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required.")
    return value.strip()


def _optional_text(payload: dict[str, Any], key: str) -> Optional[str]:
    value = payload.get(key)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _app_identifier(app: dict[str, Any]) -> str:
    attrs = _attrs(app)
    for key in ("bundle_id", "package_name", "identifier", "app_id", "package"):
        value = attrs.get(key) or app.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _extract_public_api_key(item: dict[str, Any]) -> Optional[str]:
    attrs = _attrs(item)
    for key in (
        "public_api_key",
        "api_key",
        "key",
        "value",
        "publicKey",
    ):
        value = attrs.get(key) or item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _product_store_identifier(item: dict[str, Any]) -> str:
    attrs = _attrs(item)
    for key in ("store_identifier", "identifier", "lookup_key", "name"):
        value = attrs.get(key) or item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _product_app_id(item: dict[str, Any]) -> str:
    attrs = _attrs(item)
    for key in ("app_id", "app", "application_id"):
        value = attrs.get(key) or item.get(key)
        if isinstance(value, str) and value:
            return value

    relationships = item.get("relationships")
    if isinstance(relationships, dict):
        for key in ("app", "application"):
            rel = relationships.get(key)
            if isinstance(rel, dict):
                data = rel.get("data")
                if isinstance(data, dict):
                    rel_id = data.get("id")
                    if isinstance(rel_id, str) and rel_id:
                        return rel_id
    return ""


def _product_type(item: dict[str, Any]) -> str:
    attrs = _attrs(item)
    for key in ("type", "product_type", "store_product_type"):
        value = attrs.get(key) or item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _package_position(item: dict[str, Any]) -> Optional[int]:
    attrs = _attrs(item)
    value = attrs.get("position") or item.get("position")
    return value if isinstance(value, int) else None


def _package_product_eligibility(item: dict[str, Any]) -> str:
    attrs = _attrs(item)
    for key in ("eligibility_criteria", "eligibility", "eligibility_type"):
        value = attrs.get(key) or item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _normalize_platform(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    lowered = value.lower()
    if "ios" in lowered or "app_store" in lowered:
        return "ios"
    if "android" in lowered or "play" in lowered:
        return "android"
    return lowered
