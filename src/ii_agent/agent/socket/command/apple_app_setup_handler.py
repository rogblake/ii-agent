"""Command handler for Apple app setup (bundle ID and App Store Connect app).

This handler registers the bundle ID in Apple Developer Portal and creates
the app in App Store Connect. iOS signing credentials (certificates and
provisioning profiles) are handled by EAS CLI during the build process.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from ii_agent.integrations.mobile.apple import (
    AppleAppBundleIdTakenError,
    AppleAppNameTakenError,
    AppleAuthStateEnum,
    AppleBundleIdError,
    AppleCertificateError,
    AppleCredentials,
    AppleSessionExpiredError,
    FastlaneAuthClient,
)
from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.stream import EventStream
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.sessions.schemas import SessionInfo

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer

logger = logging.getLogger(__name__)


class AppleAppSetupHandler(CommandHandler):
    """Handler for setting up iOS app (bundle ID and distribution certificate).

    This handler:
    1. Validates the bundle ID and app name
    2. Registers the Bundle ID in Apple Developer Portal
    3. Creates or verifies iOS Distribution Certificate
    """

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)
        self.fastlane_client = FastlaneAuthClient()

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.APPLE_APP_SETUP

    async def handle(self, content: dict[str, Any], session_info: SessionInfo) -> None:
        """Handle app setup request.

        This registers the bundle ID and creates/verifies the iOS Distribution
        Certificate using fastlane's Spaceship library.

        Content:
            - bundle_identifier: iOS bundle ID (e.g., com.example.app)
            - app_name: Display name for the app
            - password: Apple ID password (for Spaceship operations)
        """
        bundle_id = content.get("bundle_identifier", "").strip()
        app_name = content.get("app_name", "").strip()
        # Password can come from the request (preferred) or from stored session
        request_password = content.get("password", "").strip()

        if not bundle_id:
            await self._send_error_event(
                session_info.id,
                message="Bundle identifier is required.",
                error_type="validation_error",
            )
            return

        if not app_name:
            await self._send_error_event(
                session_info.id,
                message="App name is required.",
                error_type="validation_error",
            )
            return

        # Validate bundle ID format
        if not self._validate_bundle_id(bundle_id):
            await self._send_error_event(
                session_info.id,
                message="Invalid bundle identifier format. Use reverse domain notation (e.g., com.example.app).",
                error_type="validation_error",
            )
            return

        try:
            # Get authenticated credential
            credential = await AppleCredentials.get_active_session(str(session_info.user_id))

            if not credential:
                await self._send_error_event(
                    session_info.id,
                    message="Please authenticate with Apple first.",
                    error_type="auth_error",
                )
                return

            if credential.auth_state != AppleAuthStateEnum.AUTHENTICATED.value:
                await self._send_error_event(
                    session_info.id,
                    message="Apple authentication incomplete. Please complete the login process.",
                    error_type="auth_error",
                )
                return

            # Get password and 2FA code - prefer from request, fallback to stored session
            password = request_password
            verification_code = None

            # Try to get from stored session data
            session_data = AppleCredentials.get_decrypted_session_data(credential)
            logger.info(
                f"Session data for user {session_info.user_id}: "
                f"has_data={session_data is not None}, "
                f"keys={list(session_data.keys()) if session_data else []}"
            )

            if session_data:
                if not password:
                    password = session_data.get("_temp_password")
                # Get the 2FA code for Portal authentication
                verification_code = session_data.get("_temp_2fa_code")

            if not password:
                logger.warning(
                    f"No password available for user {session_info.user_id}. "
                    f"Request password empty and no stored password."
                )
                await self._send_error_event(
                    session_info.id,
                    message="Password required. Please re-authenticate with Apple.",
                    error_type="session_expired",
                )
                return

            team_id = credential.selected_team_id
            team_name = credential.team_name  # Used to match Portal team by name
            apple_id = credential.apple_id

            logger.info(
                f"Starting app setup for user {session_info.user_id}: "
                f"bundle_id={bundle_id}, app_name={app_name}, team_id={team_id}, "
                f"team_name={team_name}, has_verification_code={verification_code is not None}"
            )

            # Step 1: Register Bundle ID in Developer Portal
            await self._send_setup_status(
                session_info.id,
                status="registering_bundle",
                message=f"Registering Bundle ID: {bundle_id}...",
                step=1,
                total_steps=3,
            )

            try:
                bundle_result = await self.fastlane_client.register_bundle_id(
                    apple_id=apple_id,
                    password=password,
                    team_id=team_id,
                    bundle_identifier=bundle_id,
                    app_name=app_name,
                    user_id=str(session_info.user_id),
                    verification_code=verification_code,
                    team_name=team_name,
                )

                if bundle_result.get("created"):
                    logger.info(f"Created new Bundle ID: {bundle_id}")
                else:
                    logger.info(f"Bundle ID already exists: {bundle_id}")

            except AppleBundleIdError as e:
                # If bundle ID already exists, that's fine
                if "already exists" not in str(e).lower():
                    raise
                logger.info(f"Bundle ID already exists: {bundle_id}")

            # Step 2: Create App in App Store Connect
            await self._send_setup_status(
                session_info.id,
                status="creating_app",
                message=f"Creating app in App Store Connect: {app_name}...",
                step=2,
                total_steps=3,
            )

            app_id = None
            try:
                app_result = await self.fastlane_client.create_app_store_connect_app(
                    apple_id=apple_id,
                    password=password,
                    team_id=team_id,
                    bundle_identifier=bundle_id,
                    app_name=app_name,
                    user_id=str(session_info.user_id),
                    verification_code=verification_code,
                    team_name=team_name,
                )

                app_id = app_result.get("app_id")
                if app_result.get("created"):
                    logger.info(f"Created new App in App Store Connect: {app_id}")
                    await self._send_setup_status(
                        session_info.id,
                        status="app_created",
                        message="Created app in App Store Connect",
                        step=2,
                        total_steps=3,
                    )
                else:
                    logger.info(f"App already exists in App Store Connect: {app_id}")
                    await self._send_setup_status(
                        session_info.id,
                        status="app_exists",
                        message="Using existing app in App Store Connect",
                        step=2,
                        total_steps=3,
                    )

            except AppleAppNameTakenError as e:
                # Name is globally unique on App Store - user must pick a different name
                logger.warning(f"App name taken: {e}")
                await self._send_error_event(
                    session_info.id,
                    message=str(e),
                    error_type="name_taken",
                )
                return  # Stop the setup - user must change app name

            except AppleAppBundleIdTakenError as e:
                # Bundle ID registered by another developer
                logger.warning(f"Bundle ID taken by another developer: {e}")
                await self._send_error_event(
                    session_info.id,
                    message=str(e),
                    error_type="bundle_id_taken",
                )
                return  # Stop the setup - user must change bundle ID

            except Exception as e:
                logger.warning(f"App Store Connect app creation warning: {e}")
                # Send warning but continue - the app might already exist
                await self._send_setup_status(
                    session_info.id,
                    status="app_warning",
                    message=f"Could not create app: {str(e)}. You may need to create it manually.",
                    step=2,
                    total_steps=3,
                    warning=True,
                )

            # Step 3: Finalize setup
            # Note: We skip certificate creation here because EAS Build will handle
            # iOS signing credentials automatically during the build process.
            # EAS uses the Apple credentials (EXPO_APPLE_ID, EXPO_APPLE_PASSWORD, EXPO_APPLE_TEAM_ID)
            # to create and manage certificates and provisioning profiles.
            await self._send_setup_status(
                session_info.id,
                status="finalizing",
                message="Finalizing app setup...",
                step=3,
                total_steps=3,
            )

            # Send completion event
            await self._send_setup_status(
                session_info.id,
                status="completed",
                message="App setup completed! Ready to build and deploy to TestFlight.",
                step=3,
                total_steps=3,
                bundle_id=bundle_id,
                app_name=app_name,
                app_id=app_id,
            )

        except AppleSessionExpiredError:
            # Clear the stored credentials so user must re-authenticate
            logger.warning(
                f"Session expired for user {session_info.user_id}, clearing stored credentials"
            )
            try:
                await AppleCredentials.update_auth_state(
                    str(session_info.user_id),
                    AppleAuthStateEnum.EXPIRED.value,
                )
            except Exception as clear_error:
                logger.error(f"Failed to clear credentials: {clear_error}")

            await self._send_error_event(
                session_info.id,
                message="Apple session expired. Please re-authenticate.",
                error_type="session_expired",
            )
        except AppleBundleIdError as e:
            error_msg = str(e).lower()
            logger.exception(f"Bundle ID error: {e}")

            # Check if this is actually a session/auth expiration error
            is_auth_error = (
                "session expired" in error_msg
                or "re-authenticate" in error_msg
                or "invalid username and password" in error_msg
                or "authentication error" in error_msg
                or "invalid credentials" in error_msg
            )

            if is_auth_error:
                # Clear the stored credentials
                try:
                    await AppleCredentials.update_auth_state(
                        str(session_info.user_id),
                        AppleAuthStateEnum.EXPIRED.value,
                    )
                except Exception as clear_error:
                    logger.error(f"Failed to clear credentials: {clear_error}")

                await self._send_error_event(
                    session_info.id,
                    message="Apple credentials invalid or expired. Please re-authenticate.",
                    error_type="session_expired",
                )
            else:
                await self._send_error_event(
                    session_info.id,
                    message=f"Bundle ID error: {str(e)}",
                    error_type="bundle_error",
                )
        except AppleCertificateError as e:
            logger.exception(f"Certificate error: {e}")
            await self._send_error_event(
                session_info.id,
                message=f"Certificate error: {str(e)}",
                error_type="certificate_error",
            )
        except Exception as e:
            logger.exception(f"Unexpected error during app setup: {e}")
            await self._send_error_event(
                session_info.id,
                message="An unexpected error occurred. Please try again.",
                error_type="unexpected_error",
            )

    def _validate_bundle_id(self, bundle_id: str) -> bool:
        """Validate bundle identifier format.

        Args:
            bundle_id: Bundle identifier to validate

        Returns:
            True if valid format
        """
        # Basic validation: reverse domain notation
        if not bundle_id:
            return False

        parts = bundle_id.split(".")
        if len(parts) < 2:
            return False

        # Each part should be valid identifier
        for part in parts:
            if not part:
                return False
            if not part[0].isalpha() and part[0] != "_":
                return False
            if not all(c.isalnum() or c in "_-" for c in part):
                return False

        return True

    async def _send_setup_status(
        self,
        session_id: str | uuid.UUID,
        status: str,
        message: str,
        step: int = 0,
        total_steps: int = 0,
        warning: bool = False,
        **kwargs,
    ) -> None:
        """Send app setup status event."""
        session_uuid = uuid.UUID(session_id) if isinstance(session_id, str) else session_id

        content = {
            "status": status,
            "message": message,
            "step": step,
            "total_steps": total_steps,
            "warning": warning,
        }
        content.update(kwargs)

        await self.send_event(
            RealtimeEvent(
                session_id=session_uuid,
                type=EventType.APPLE_APP_SETUP_STATUS,
                content=content,
            )
        )


class AppleListAppsHandler(CommandHandler):
    """Handler for listing existing apps from App Store Connect."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)
        self.fastlane_client = FastlaneAuthClient()

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.APPLE_LIST_APPS

    async def handle(self, content: dict[str, Any], session_info: SessionInfo) -> None:
        """Handle list apps request.

        This lists all apps from App Store Connect for the authenticated user.
        """
        try:
            # Get authenticated credential
            credential = await AppleCredentials.get_active_session(str(session_info.user_id))

            if not credential:
                await self._send_error_event(
                    session_info.id,
                    message="Please authenticate with Apple first.",
                    error_type="auth_error",
                )
                return

            if credential.auth_state != AppleAuthStateEnum.AUTHENTICATED.value:
                await self._send_error_event(
                    session_info.id,
                    message="Apple authentication incomplete. Please complete the login process.",
                    error_type="auth_error",
                )
                return

            # Get password and 2FA code from stored session
            session_data = AppleCredentials.get_decrypted_session_data(credential)
            password = session_data.get("_temp_password") if session_data else None
            verification_code = session_data.get("_temp_2fa_code") if session_data else None

            if not password:
                await self._send_error_event(
                    session_info.id,
                    message="Session expired. Please re-authenticate with Apple.",
                    error_type="session_expired",
                )
                return

            team_id = credential.selected_team_id
            team_name = credential.team_name
            apple_id = credential.apple_id

            # List apps
            apps = await self.fastlane_client.list_apps(
                apple_id=apple_id,
                password=password,
                team_id=team_id,
                user_id=str(session_info.user_id),
                verification_code=verification_code,
                team_name=team_name,
            )

            # Send apps list event
            session_uuid = (
                uuid.UUID(session_info.id) if isinstance(session_info.id, str) else session_info.id
            )
            await self.send_event(
                RealtimeEvent(
                    session_id=session_uuid,
                    type=EventType.APPLE_APPS_LIST,
                    content={
                        "apps": apps,
                        "message": f"Found {len(apps)} apps in App Store Connect.",
                    },
                )
            )

        except Exception as e:
            logger.exception(f"Unexpected error listing apps: {e}")
            await self._send_error_event(
                session_info.id,
                message="Failed to list apps. Please try again.",
                error_type="unexpected_error",
            )
