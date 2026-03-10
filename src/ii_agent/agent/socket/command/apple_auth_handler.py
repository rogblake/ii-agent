"""Command handlers for Apple ID authentication flow."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from ii_agent.mobile.apple import (
    Apple2FAInvalidCodeError,
    AppleAccountLockedError,
    AppleAuthenticationError,
    AppleAuthState,
    AppleCredentials,
    AppleInvalidCredentialsError,
    AppleRateLimitError,
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


class AppleAuthLoginHandler(CommandHandler):
    """Handler for Apple ID login step."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)
        self.auth_client = FastlaneAuthClient()

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.APPLE_AUTH_LOGIN

    async def handle(
        self, content: dict[str, Any], session_info: SessionInfo
    ) -> None:
        """Handle Apple ID login request.

        Content:
            - apple_id: Apple ID email
            - password: Apple ID password
        """
        apple_id = content.get("apple_id")
        password = content.get("password")

        if not apple_id or not password:
            await self._send_error_event(
                session_info.id,
                message="Apple ID and password are required.",
                error_type="validation_error",
            )
            return

        try:
            # Send status update
            await self._send_auth_status(
                session_info.id,
                status="authenticating",
                message="Signing in to Apple Developer...",
            )

            # Initiate login with user-specific session isolation
            login_response = await self.auth_client.initiate_login(
                apple_id, password, str(session_info.user_id)
            )
            session = login_response.session

            # Save credential to database
            # For fastlane, we need to store the password temporarily for 2FA
            session_data = session.model_dump(mode="json")
            if login_response.requires_2fa:
                # Store password temporarily for 2FA step (encrypted in DB)
                session_data["_temp_password"] = password

            await AppleCredentials.save_or_update_credential(
                user_id=str(session_info.user_id),
                apple_id=apple_id,
                auth_state=session.auth_state.value,
                session_data=session_data,
                session_expiry=session.expiry,
            )

            if login_response.requires_2fa:
                # Send 2FA required event
                await self._send_2fa_required(
                    session_info.id,
                    message="Please enter the 6-digit code from your trusted Apple device.",
                )
            else:
                # No 2FA needed, proceed to team selection
                teams = await self.auth_client.get_teams(session)

                # Update credential with teams
                await AppleCredentials.save_or_update_credential(
                    user_id=str(session_info.user_id),
                    apple_id=apple_id,
                    auth_state=AppleAuthState.PENDING_TEAM_SELECTION.value,
                    available_teams=[t.model_dump() for t in teams],
                )

                await self._send_team_selection(session_info.id, teams)

        except AppleInvalidCredentialsError:
            await self._send_error_event(
                session_info.id,
                message="Invalid Apple ID or password. Please check your credentials.",
                error_type="auth_error",
            )
        except AppleAccountLockedError:
            await self._send_error_event(
                session_info.id,
                message="Your Apple account is locked. Please visit iforgot.apple.com to unlock it.",
                error_type="auth_error",
            )
        except AppleRateLimitError:
            await self._send_error_event(
                session_info.id,
                message="Too many login attempts. Please wait a few minutes and try again.",
                error_type="rate_limit_error",
            )
        except AppleAuthenticationError as e:
            logger.exception(f"Apple login failed: {e}")
            await self._send_error_event(
                session_info.id,
                message=f"Apple login failed: {e.message}",
                error_type="auth_error",
            )
        except Exception as e:
            logger.exception(f"Unexpected error during Apple login: {e}")
            await self._send_error_event(
                session_info.id,
                message="An unexpected error occurred. Please try again.",
                error_type="unexpected_error",
            )

    async def _send_auth_status(
        self, session_id: str | uuid.UUID, status: str, message: str
    ) -> None:
        """Send authentication status event."""
        session_uuid = (
            uuid.UUID(session_id) if isinstance(session_id, str) else session_id
        )
        await self.send_event(
            RealtimeEvent(
                session_id=session_uuid,
                type=EventType.APPLE_AUTH_STATUS,
                content={"status": status, "message": message},
            )
        )

    async def _send_2fa_required(
        self, session_id: str | uuid.UUID, message: str
    ) -> None:
        """Send 2FA required event."""
        session_uuid = (
            uuid.UUID(session_id) if isinstance(session_id, str) else session_id
        )
        await self.send_event(
            RealtimeEvent(
                session_id=session_uuid,
                type=EventType.APPLE_2FA_REQUIRED,
                content={"message": message},
            )
        )

    async def _send_team_selection(
        self, session_id: str | uuid.UUID, teams: list
    ) -> None:
        """Send team selection event."""
        session_uuid = (
            uuid.UUID(session_id) if isinstance(session_id, str) else session_id
        )
        await self.send_event(
            RealtimeEvent(
                session_id=session_uuid,
                type=EventType.APPLE_TEAM_SELECTION,
                content={
                    "teams": [t.model_dump() for t in teams],
                    "message": "Select your Apple Developer team.",
                },
            )
        )


class AppleAuth2FAHandler(CommandHandler):
    """Handler for Apple 2FA verification."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)
        self.auth_client = FastlaneAuthClient()

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.APPLE_AUTH_2FA

    async def handle(
        self, content: dict[str, Any], session_info: SessionInfo
    ) -> None:
        """Handle 2FA code verification.

        Content:
            - code: 6-digit verification code
        """
        code = content.get("code", "").strip()

        if not code or len(code) != 6 or not code.isdigit():
            await self._send_error_event(
                session_info.id,
                message="Please enter a valid 6-digit code.",
                error_type="validation_error",
            )
            return

        try:
            # Get stored credential
            credential = await AppleCredentials.get_user_credential(
                str(session_info.user_id)
            )

            if not credential:
                await self._send_error_event(
                    session_info.id,
                    message="No active Apple session found. Please start over.",
                    error_type="session_error",
                )
                return

            # Get session data
            session_data = AppleCredentials.get_decrypted_session_data(credential)
            if not session_data:
                await self._send_error_event(
                    session_info.id,
                    message="Session data corrupted. Please start over.",
                    error_type="session_error",
                )
                return

            # Deserialize session
            from ii_agent.mobile.apple.types import AppleSession
            session = AppleSession.model_validate(session_data)

            # Get stored password (needed for fastlane 2FA)
            password = session_data.get("_temp_password")
            if not password:
                await self._send_error_event(
                    session_info.id,
                    message="Session expired. Please start over.",
                    error_type="session_error",
                )
                return

            # Send status update
            await self._send_auth_status(
                session_info.id,
                status="verifying",
                message="Verifying code...",
            )

            # Verify 2FA with fastlane (requires password, user_id for session isolation)
            updated_session = await self.auth_client.verify_2fa_code(
                session, code, password, str(session_info.user_id)
            )

            # Get teams
            teams = await self.auth_client.get_teams(updated_session)

            # Update credential with new session and teams
            # Keep the password and 2FA code for the app setup step (certificate creation)
            # The 2FA code is needed for Portal operations (separate from Tunes)
            new_session_data = updated_session.model_dump(mode="json")
            new_session_data["_temp_password"] = password  # Preserve for app setup
            new_session_data["_temp_2fa_code"] = code  # Preserve for Portal auth

            logger.info(
                f"2FA verification - saving password and 2FA code for user, "
                f"session_data keys: {list(new_session_data.keys())}"
            )

            await AppleCredentials.save_or_update_credential(
                user_id=str(session_info.user_id),
                apple_id=credential.apple_id,
                auth_state=AppleAuthState.PENDING_TEAM_SELECTION.value,
                session_data=new_session_data,
                available_teams=[t.model_dump() for t in teams],
                session_expiry=updated_session.expiry,
            )

            # Send team selection event
            await self._send_team_selection(session_info.id, teams)

        except Apple2FAInvalidCodeError:
            await self._send_error_event(
                session_info.id,
                message="Invalid verification code. Please try again.",
                error_type="auth_error",
            )
        except AppleSessionExpiredError:
            await self._send_error_event(
                session_info.id,
                message="Session expired. Please start over.",
                error_type="session_expired",
            )
        except AppleAuthenticationError as e:
            logger.exception(f"2FA verification failed: {e}")
            await self._send_error_event(
                session_info.id,
                message=f"Verification failed: {e.message}",
                error_type="auth_error",
            )
        except Exception as e:
            logger.exception(f"Unexpected error during 2FA verification: {e}")
            await self._send_error_event(
                session_info.id,
                message="An unexpected error occurred. Please try again.",
                error_type="unexpected_error",
            )

    async def _send_auth_status(
        self, session_id: str | uuid.UUID, status: str, message: str
    ) -> None:
        """Send authentication status event."""
        session_uuid = (
            uuid.UUID(session_id) if isinstance(session_id, str) else session_id
        )
        await self.send_event(
            RealtimeEvent(
                session_id=session_uuid,
                type=EventType.APPLE_AUTH_STATUS,
                content={"status": status, "message": message},
            )
        )

    async def _send_team_selection(
        self, session_id: str | uuid.UUID, teams: list
    ) -> None:
        """Send team selection event."""
        session_uuid = (
            uuid.UUID(session_id) if isinstance(session_id, str) else session_id
        )
        await self.send_event(
            RealtimeEvent(
                session_id=session_uuid,
                type=EventType.APPLE_TEAM_SELECTION,
                content={
                    "teams": [t.model_dump() for t in teams],
                    "message": "Select your Apple Developer team.",
                },
            )
        )


class AppleAuthSelectTeamHandler(CommandHandler):
    """Handler for team selection."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)
        self.auth_client = FastlaneAuthClient()

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.APPLE_AUTH_SELECT_TEAM

    async def handle(
        self, content: dict[str, Any], session_info: SessionInfo
    ) -> None:
        """Handle team selection.

        Content:
            - team_id: Selected team ID
        """
        team_id = content.get("team_id")

        if not team_id:
            await self._send_error_event(
                session_info.id,
                message="Please select a team.",
                error_type="validation_error",
            )
            return

        try:
            # Get stored credential
            credential = await AppleCredentials.get_user_credential(
                str(session_info.user_id)
            )

            if not credential:
                await self._send_error_event(
                    session_info.id,
                    message="No active Apple session found. Please start over.",
                    error_type="session_error",
                )
                return

            # Validate team_id is in available teams
            available_teams = credential.available_teams or []
            team = next((t for t in available_teams if t.get("team_id") == team_id), None)

            if not team:
                await self._send_error_event(
                    session_info.id,
                    message="Invalid team selection.",
                    error_type="validation_error",
                )
                return

            # Get session data
            session_data = AppleCredentials.get_decrypted_session_data(credential)
            logger.info(
                f"Team selection - retrieved session_data keys: "
                f"{list(session_data.keys()) if session_data else 'None'}, "
                f"has_password: {'_temp_password' in session_data if session_data else False}"
            )

            if not session_data:
                await self._send_error_event(
                    session_info.id,
                    message="Session data corrupted. Please start over.",
                    error_type="session_error",
                )
                return

            # Update session with selected team
            from ii_agent.mobile.apple.types import AppleSession, AppleTeam
            session = AppleSession.model_validate(session_data)

            # Reconstruct teams from available_teams
            session.teams = [
                AppleTeam.model_validate(t) for t in available_teams
            ]

            session = await self.auth_client.select_team(session, team_id)

            # Update credential with selected team
            # Preserve the password and 2FA code for the app setup step (certificate creation)
            new_session_data = session.model_dump(mode="json")
            has_password = "_temp_password" in session_data
            has_2fa_code = "_temp_2fa_code" in session_data
            if has_password:
                new_session_data["_temp_password"] = session_data["_temp_password"]
            if has_2fa_code:
                new_session_data["_temp_2fa_code"] = session_data["_temp_2fa_code"]

            logger.info(
                f"Team selection - preserving password: {has_password}, "
                f"2fa_code: {has_2fa_code}, "
                f"session_data keys: {list(session_data.keys())}"
            )

            await AppleCredentials.save_or_update_credential(
                user_id=str(session_info.user_id),
                apple_id=credential.apple_id,
                auth_state=AppleAuthState.AUTHENTICATED.value,
                session_data=new_session_data,
                team_id=team_id,
                team_name=team.get("name"),
            )

            # Send success event
            session_uuid = (
                uuid.UUID(session_info.id)
                if isinstance(session_info.id, str)
                else session_info.id
            )
            await self.send_event(
                RealtimeEvent(
                    session_id=session_uuid,
                    type=EventType.APPLE_AUTH_STATUS,
                    content={
                        "status": "authenticated",
                        "message": f"Successfully authenticated with team: {team.get('name')}",
                        "team_id": team_id,
                        "team_name": team.get("name"),
                    },
                )
            )

        except AppleAuthenticationError as e:
            logger.exception(f"Team selection failed: {e}")
            await self._send_error_event(
                session_info.id,
                message=f"Team selection failed: {e.message}",
                error_type="auth_error",
            )
        except Exception as e:
            logger.exception(f"Unexpected error during team selection: {e}")
            await self._send_error_event(
                session_info.id,
                message="An unexpected error occurred. Please try again.",
                error_type="unexpected_error",
            )


class AppleCheckAuthHandler(CommandHandler):
    """Handler for checking existing Apple authentication status."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.APPLE_CHECK_AUTH

    async def handle(
        self, content: dict[str, Any], session_info: SessionInfo
    ) -> None:
        """Check if user has valid Apple credentials stored.

        Returns information about existing auth state so frontend can skip
        login steps if already authenticated. Also returns expo_token if available.
        """
        try:
            # Get stored credential - first try active session
            credential = await AppleCredentials.get_active_session(
                str(session_info.user_id)
            )

            # If no active session, check if we have any credential (for expo token)
            if not credential:
                credential = await AppleCredentials.get_user_credential(
                    str(session_info.user_id)
                )

            session_uuid = (
                uuid.UUID(session_info.id)
                if isinstance(session_info.id, str)
                else session_info.id
            )

            # Get expo token and app-specific password if available
            expo_token = None
            app_specific_password = None
            if credential:
                expo_token = AppleCredentials.get_decrypted_expo_token(credential)
                app_specific_password = AppleCredentials.get_decrypted_app_specific_password(credential)

            if not credential:
                # No credential found at all
                await self.send_event(
                    RealtimeEvent(
                        session_id=session_uuid,
                        type=EventType.APPLE_AUTH_CHECK_RESULT,
                        content={
                            "has_valid_auth": False,
                            "has_expo_token": False,
                            "has_app_specific_password": False,
                            "message": "No valid Apple authentication found.",
                        },
                    )
                )
                return

            # Always require re-authentication for security (don't store passwords long-term)
            # We only return stored non-sensitive data for convenience (pre-fill forms)
            await self.send_event(
                RealtimeEvent(
                    session_id=session_uuid,
                    type=EventType.APPLE_AUTH_CHECK_RESULT,
                    content={
                        "has_valid_auth": False,  # Always require fresh login
                        "has_expo_token": bool(expo_token),
                        "expo_token": expo_token,
                        "has_app_specific_password": bool(app_specific_password),
                        "apple_id": credential.apple_id if credential.apple_id != "pending" else None,
                        "team_name": credential.team_name,
                        "message": "Please log in with your Apple ID.",
                    },
                )
            )

        except Exception as e:
            logger.exception(f"Error checking Apple auth: {e}")
            session_uuid = (
                uuid.UUID(session_info.id)
                if isinstance(session_info.id, str)
                else session_info.id
            )
            await self.send_event(
                RealtimeEvent(
                    session_id=session_uuid,
                    type=EventType.APPLE_AUTH_CHECK_RESULT,
                    content={
                        "has_valid_auth": False,
                        "has_expo_token": False,
                        "has_app_specific_password": False,
                        "message": "Error checking authentication status.",
                    },
                )
            )


class SaveExpoTokenHandler(CommandHandler):
    """Handler for saving Expo access token."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.SAVE_EXPO_TOKEN

    async def handle(
        self, content: dict[str, Any], session_info: SessionInfo
    ) -> None:
        """Save the Expo access token for the user.

        Content:
            - expo_token: The Expo access token to save
        """
        expo_token = content.get("expo_token", "").strip()

        if not expo_token:
            await self._send_error_event(
                session_info.id,
                message="Expo token is required.",
                error_type="validation_error",
            )
            return

        try:
            # Save the expo token
            await AppleCredentials.save_expo_token(
                str(session_info.user_id),
                expo_token,
            )

            session_uuid = (
                uuid.UUID(session_info.id)
                if isinstance(session_info.id, str)
                else session_info.id
            )

            await self.send_event(
                RealtimeEvent(
                    session_id=session_uuid,
                    type=EventType.EXPO_TOKEN_SAVED,
                    content={
                        "success": True,
                        "message": "Expo token saved successfully.",
                    },
                )
            )

        except Exception as e:
            logger.exception(f"Error saving expo token: {e}")
            await self._send_error_event(
                session_info.id,
                message="Failed to save Expo token.",
                error_type="unexpected_error",
            )
