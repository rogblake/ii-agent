"""Apple authentication using fastlane's Spaceship library.

This module uses Ruby scripts with Spaceship to handle Apple authentication.
Spaceship properly manages SSL certificates and session handling, providing
reliable authentication with 2FA support via trusted devices.
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from .exceptions import (
    AppleAccountLockedError,
    AppleAuthenticationError,
    AppleBundleIdError,
    AppleCertificateError,
    AppleInvalidCredentialsError,
    AppleRateLimitError,
    AppleSessionExpiredError,
)
from .types import (
    AppleAuthState,
    AppleSession,
    AppleTeam,
    LoginResponse,
)

logger = logging.getLogger(__name__)

# Session validity duration
SESSION_DURATION_DAYS = 30

# Base directory for user-specific Spaceship sessions
# Each user gets their own subdirectory to prevent session conflicts
SPACESHIP_SESSIONS_BASE_DIR = "/tmp/spaceship_sessions"

# Ruby script template for fastlane authentication
# Uses Spaceship which handles Apple's auth properly
# This script handles both initial login (detecting 2FA) and login with 2FA code
# Scripts are stored as Ruby assets to keep this module focused on orchestration.
SCRIPT_ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _load_ruby_script(script_name: str) -> str:
    script_path = SCRIPT_ASSETS_DIR / script_name
    try:
        return script_path.read_text()
    except OSError as exc:
        raise RuntimeError(f"Unable to read Ruby script asset: {script_path}") from exc


# FASTLANE_2FA_SCRIPT is no longer needed - FASTLANE_AUTH_SCRIPT handles both cases
# by checking if VERIFICATION_CODE is provided
FASTLANE_AUTH_SCRIPT = _load_ruby_script("fastlane_auth.rb")
FASTLANE_GET_TEAMS_SCRIPT = _load_ruby_script("fastlane_get_teams.rb")
FASTLANE_CREATE_CERTIFICATE_SCRIPT = _load_ruby_script("fastlane_create_certificate.rb")
FASTLANE_GENERATE_EAS_CREDENTIALS_SCRIPT = _load_ruby_script("fastlane_generate_eas_credentials.rb")
FASTLANE_REGISTER_BUNDLE_ID_SCRIPT = _load_ruby_script("fastlane_register_bundle_id.rb")
FASTLANE_CREATE_APP_SCRIPT = _load_ruby_script("fastlane_create_app.rb")
FASTLANE_LIST_APPS_SCRIPT = _load_ruby_script("fastlane_list_apps.rb")


class FastlaneAuthClient:
    """Apple authentication client using fastlane's Spaceship library.

    This provides reliable authentication by leveraging Spaceship's
    battle-tested Apple API integration with proper SSL handling.
    """

    def __init__(self):
        self._check_fastlane_installed()

    def _get_user_cookie_path(self, user_id: str) -> str:
        """Get the user-specific Spaceship cookie/session path.

        Each user gets their own directory to prevent session conflicts
        when multiple users authenticate simultaneously.

        Args:
            user_id: The user's unique identifier

        Returns:
            Path to the user's Spaceship session directory
        """
        # Sanitize user_id to be filesystem-safe
        safe_user_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
        user_path = os.path.join(SPACESHIP_SESSIONS_BASE_DIR, safe_user_id)

        # Ensure the directory exists
        os.makedirs(user_path, exist_ok=True)

        return user_path

    def _check_fastlane_installed(self) -> bool:
        """Check if fastlane is installed."""
        try:
            result = subprocess.run(
                ["fastlane", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Fastlane not installed")
            return False

    def _run_ruby_script(
        self, script: str, env: dict[str, str], timeout: int = 60
    ) -> dict[str, Any]:
        """Run a Ruby script and parse JSON output."""
        # Create a temporary file for the script
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rb", delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            # Build environment
            run_env = os.environ.copy()
            run_env.update(env)

            # Run the script
            result = subprocess.run(
                ["ruby", script_path],
                env=run_env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Log raw output for debugging
            logger.info(f"Ruby script stdout: {result.stdout[:500] if result.stdout else 'empty'}")
            if result.stderr:
                logger.info(f"Ruby script stderr: {result.stderr[:500]}")

            # Parse JSON output
            output = result.stdout
            if "---JSON_OUTPUT_START---" in output:
                json_start = output.find("---JSON_OUTPUT_START---") + len("---JSON_OUTPUT_START---")
                json_end = output.find("---JSON_OUTPUT_END---")
                json_str = output[json_start:json_end].strip()
                parsed = json.loads(json_str)
                logger.info(f"Parsed Ruby output: {parsed}")
                return parsed
            else:
                # Check stderr for errors
                logger.error(
                    f"Ruby script failed - no JSON output. stdout: {result.stdout}, stderr: {result.stderr}"
                )

                # Check if stderr contains 2FA-related messages
                stderr_lower = (result.stderr or "").lower()
                if (
                    "two-factor" in stderr_lower
                    or "2fa" in stderr_lower
                    or "verification" in stderr_lower
                ):
                    return {
                        "success": False,
                        "requires_2fa": True,
                        "error": "2fa_required",
                        "message": "Two-factor authentication required",
                    }

                return {
                    "success": False,
                    "error": "script_error",
                    "message": result.stderr or "Unknown error",
                }

        except subprocess.TimeoutExpired:
            logger.error("Ruby script timed out")
            return {"success": False, "error": "timeout", "message": "Authentication timed out"}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON output: {e}")
            return {"success": False, "error": "parse_error", "message": str(e)}
        finally:
            # Clean up temp file
            try:
                os.unlink(script_path)
            except Exception:
                pass

    async def initiate_login(self, apple_id: str, password: str, user_id: str) -> LoginResponse:
        """Initiate Apple ID login using fastlane.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            user_id: The user's unique identifier (for session isolation)

        Returns:
            LoginResponse with session and 2FA requirement flag
        """
        # Get user-specific cookie path for session isolation
        cookie_path = self._get_user_cookie_path(user_id)

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_AUTH_SCRIPT,
            {
                "APPLE_ID": apple_id,
                "APPLE_PASSWORD": password,
                "FASTLANE_DONT_STORE_PASSWORD": "1",
                "FASTLANE_SKIP_UPDATE_CHECK": "1",
                "FORCE_FRESH_LOGIN": "1",  # Clear cache for initial login
                "SPACESHIP_COOKIE_PATH": cookie_path,  # User-specific session
            },
            120,  # 2 minute timeout for login
        )

        # Log the result for debugging
        logger.info(
            f"Fastlane auth result: success={result.get('success')}, "
            f"requires_2fa={result.get('requires_2fa')}, "
            f"error={result.get('error')}"
        )

        if result.get("success"):
            # Login succeeded
            session = AppleSession(
                session_id=str(uuid.uuid4()),
                scnt="",
                x_apple_id_session_id=result.get("session_id", ""),
                auth_state=AppleAuthState.PENDING_TEAM_SELECTION,
                apple_id=apple_id,
                cookies=result.get("cookies", {}),
                teams=[
                    AppleTeam(
                        team_id=t["team_id"],
                        name=t["name"],
                        team_type=t["team_type"],
                    )
                    for t in result.get("teams", [])
                ],
                expiry=datetime.now(timezone.utc) + timedelta(days=SESSION_DURATION_DAYS),
            )
            return LoginResponse(
                session=session,
                requires_2fa=False,
                auth_type=None,
            )

        elif result.get("requires_2fa") or result.get("error") == "2fa_required":
            # 2FA required - store the session tokens for verification
            session = AppleSession(
                session_id=str(uuid.uuid4()),
                scnt=result.get("scnt", ""),
                x_apple_id_session_id=result.get("session_id", ""),
                auth_state=AppleAuthState.PENDING_2FA,
                apple_id=apple_id,
                cookies={},
                expiry=datetime.now(timezone.utc) + timedelta(days=SESSION_DURATION_DAYS),
            )
            # Store password temporarily for 2FA step (will be cleared after)
            session._temp_password = password
            return LoginResponse(
                session=session,
                requires_2fa=True,
                auth_type=result.get("auth_type", "hsa2"),
            )

        else:
            # Handle errors
            error = result.get("error", "unknown")
            message = result.get("message", "Authentication failed")

            if error == "invalid_credentials":
                raise AppleInvalidCredentialsError()
            elif error == "account_locked":
                raise AppleAccountLockedError()
            elif error == "rate_limit":
                raise AppleRateLimitError()
            else:
                raise AppleAuthenticationError(message)

    async def verify_2fa_code(
        self,
        session: AppleSession,
        code: str,
        password: str,
        user_id: str,
    ) -> AppleSession:
        """Verify 2FA code using Spaceship.

        This re-runs the full login with the 2FA code provided. Spaceship will
        use the monkey-patched ask_for_2fa_code method to get the code.

        Args:
            session: Current session from login
            code: 6-digit verification code
            password: Apple ID password (needed for Spaceship re-login with 2FA)
            user_id: The user's unique identifier (for session isolation)

        Returns:
            Updated session with authenticated state
        """
        # Get user-specific cookie path for session isolation
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        # Use the same auth script but with VERIFICATION_CODE set
        # The script will monkey-patch Spaceship to use this code
        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_AUTH_SCRIPT,
            {
                "APPLE_ID": session.apple_id,
                "APPLE_PASSWORD": password,
                "VERIFICATION_CODE": code,
                "FASTLANE_DONT_STORE_PASSWORD": "1",
                "FASTLANE_SKIP_UPDATE_CHECK": "1",
                "SPACESHIP_COOKIE_PATH": cookie_path,  # User-specific session
            },
            120,
        )

        logger.info(f"2FA verification result: {result}")

        if result.get("success"):
            # Update session with teams from successful login
            session.auth_state = AppleAuthState.PENDING_TEAM_SELECTION
            session.teams = [
                AppleTeam(
                    team_id=t["team_id"],
                    name=t["name"],
                    team_type=t["team_type"],
                )
                for t in result.get("teams", [])
            ]
            return session
        else:
            error = result.get("error", "unknown")
            message = result.get("message", "Verification failed")

            if error == "invalid_code":
                from .exceptions import Apple2FAInvalidCodeError

                raise Apple2FAInvalidCodeError()
            else:
                raise AppleAuthenticationError(message)

    async def get_teams(self, session: AppleSession) -> list[AppleTeam]:
        """Get available teams from session.

        If teams are already in session, return them.
        """
        if session.teams:
            return session.teams

        # Teams should have been populated during 2FA verification
        # Return empty list if not available
        return []

        return []

    async def select_team(self, session: AppleSession, team_id: str) -> AppleSession:
        """Select a team for subsequent operations."""
        team = next((t for t in session.teams if t.team_id == team_id), None)
        if not team:
            raise AppleAuthenticationError(f"Team {team_id} not found")

        session.selected_team_id = team_id
        session.auth_state = AppleAuthState.AUTHENTICATED
        return session

    async def create_distribution_certificate(
        self,
        apple_id: str,
        password: str,
        team_id: str,
        user_id: str,
        verification_code: str | None = None,
        team_name: str | None = None,
    ) -> dict[str, Any]:
        """Create an iOS Distribution Certificate using Spaceship.

        This creates a new distribution certificate if one doesn't exist,
        or returns information about existing certificates.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            team_id: Selected team ID
            user_id: The user's unique identifier (for session isolation)
            verification_code: Optional 2FA code (for Portal authentication)
            team_name: Team name (used to match Portal team if team_id is Tunes ID)

        Returns:
            Dict with certificate info (certificate_id, name, expiry, created)
        """
        # Get user-specific cookie path for session isolation
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        env = {
            "APPLE_ID": apple_id,
            "APPLE_PASSWORD": password,
            "TEAM_ID": team_id,
            "FASTLANE_DONT_STORE_PASSWORD": "1",
            "FASTLANE_SKIP_UPDATE_CHECK": "1",
            "SPACESHIP_COOKIE_PATH": cookie_path,  # User-specific session
        }
        if verification_code:
            env["VERIFICATION_CODE"] = verification_code
        if team_name:
            env["TEAM_NAME"] = team_name

        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_CREATE_CERTIFICATE_SCRIPT,
            env,
            180,  # 3 minute timeout for certificate creation
        )

        logger.info(f"Certificate creation result: {result}")

        if result.get("success"):
            return {
                "certificate_id": result.get("certificate_id"),
                "name": result.get("name"),
                "expiry": result.get("expiry"),
                "created": result.get("created", False),
                "existing_count": result.get("existing_count", 0),
            }
        else:
            error = result.get("error", "unknown")
            message = result.get("message", "Certificate creation failed")

            if error == "max_certificates":
                from .exceptions import AppleCertificateError

                raise AppleCertificateError(
                    "Maximum number of iOS Distribution Certificates reached. "
                    "Please revoke an existing certificate in the Apple Developer Portal."
                )
            elif error == "session_expired":
                from .exceptions import AppleSessionExpiredError

                raise AppleSessionExpiredError()
            else:
                from .exceptions import AppleCertificateError

                raise AppleCertificateError(message)

    async def register_bundle_id(
        self,
        apple_id: str,
        password: str,
        team_id: str,
        bundle_identifier: str,
        app_name: str,
        user_id: str,
        verification_code: str | None = None,
        team_name: str | None = None,
    ) -> dict[str, Any]:
        """Register a Bundle ID using Spaceship.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            team_id: Selected team ID
            bundle_identifier: The bundle ID (e.g., com.example.app)
            app_name: The app name
            user_id: The user's unique identifier (for session isolation)
            verification_code: Optional 2FA code (for Portal authentication)
            team_name: Team name (used to match Portal team if team_id is Tunes ID)

        Returns:
            Dict with bundle ID info (bundle_id, name, created)
        """
        # Get user-specific cookie path for session isolation
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        env = {
            "APPLE_ID": apple_id,
            "APPLE_PASSWORD": password,
            "TEAM_ID": team_id,
            "BUNDLE_IDENTIFIER": bundle_identifier,
            "APP_NAME": app_name,
            "FASTLANE_DONT_STORE_PASSWORD": "1",
            "FASTLANE_SKIP_UPDATE_CHECK": "1",
            "SPACESHIP_COOKIE_PATH": cookie_path,  # User-specific session
        }
        if verification_code:
            env["VERIFICATION_CODE"] = verification_code
        if team_name:
            env["TEAM_NAME"] = team_name

        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_REGISTER_BUNDLE_ID_SCRIPT,
            env,
            120,
        )

        logger.info(f"Bundle ID registration result: {result}")

        if result.get("success"):
            return {
                "bundle_id": result.get("bundle_id"),
                "name": result.get("name"),
                "created": result.get("created", False),
            }
        else:
            error = result.get("error", "unknown")
            message = result.get("message", "Bundle ID registration failed")

            if error == "already_exists":
                # This is actually fine - bundle ID already exists
                return {
                    "bundle_id": bundle_identifier,
                    "name": app_name,
                    "created": False,
                }
            elif error == "session_expired":
                from .exceptions import AppleSessionExpiredError

                raise AppleSessionExpiredError()
            else:
                from .exceptions import AppleBundleIdError

                raise AppleBundleIdError(message)

    async def create_app_store_connect_app(
        self,
        apple_id: str,
        password: str,
        team_id: str,
        bundle_identifier: str,
        app_name: str,
        user_id: str,
        verification_code: str | None = None,
        team_name: str | None = None,
    ) -> dict[str, Any]:
        """Create an App in App Store Connect.

        This creates the app record in App Store Connect, which is required
        for TestFlight submissions.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            team_id: Selected team ID
            bundle_identifier: The bundle ID (e.g., com.example.app)
            app_name: The app name
            user_id: The user's unique identifier (for session isolation)
            verification_code: Optional 2FA code
            team_name: Team name (used to match team)

        Returns:
            Dict with app info (app_id, bundle_id, name, created)
        """
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        env = {
            "APPLE_ID": apple_id,
            "APPLE_PASSWORD": password,
            "TEAM_ID": team_id,
            "BUNDLE_IDENTIFIER": bundle_identifier,
            "APP_NAME": app_name,
            "FASTLANE_DONT_STORE_PASSWORD": "1",
            "FASTLANE_SKIP_UPDATE_CHECK": "1",
            "SPACESHIP_COOKIE_PATH": cookie_path,
        }
        if verification_code:
            env["VERIFICATION_CODE"] = verification_code
        if team_name:
            env["TEAM_NAME"] = team_name

        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_CREATE_APP_SCRIPT,
            env,
            120,
        )

        logger.info(f"App Store Connect app creation result: {result}")

        if result.get("success"):
            return {
                "app_id": result.get("app_id"),
                "bundle_id": result.get("bundle_id"),
                "name": result.get("name"),
                "created": result.get("created", False),
            }
        else:
            error = result.get("error", "unknown")
            message = result.get("message", "App creation failed")
            conflict_type = result.get("conflict_type")

            if error == "already_exists" and conflict_type == "unknown":
                # Generic already exists with unknown conflict - treat as partial success
                # The app might be ours or might be a name/bundle conflict
                return {
                    "app_id": result.get("app_id"),
                    "bundle_id": bundle_identifier,
                    "name": app_name,
                    "created": False,
                }
            elif error == "name_taken":
                # Name is globally unique and taken by someone else
                from .exceptions import AppleAppNameTakenError

                raise AppleAppNameTakenError(app_name, message)
            elif error == "bundle_id_taken":
                # Bundle ID registered by another developer
                from .exceptions import AppleAppBundleIdTakenError

                raise AppleAppBundleIdTakenError(bundle_identifier, message)
            elif error == "session_expired":
                raise AppleSessionExpiredError()
            else:
                raise AppleAuthenticationError(message)

    async def list_apps(
        self,
        apple_id: str,
        password: str,
        team_id: str,
        user_id: str,
        verification_code: str | None = None,
        team_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all apps from App Store Connect.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            team_id: Selected team ID
            user_id: The user's unique identifier (for session isolation)
            verification_code: Optional 2FA code
            team_name: Team name (used to match team)

        Returns:
            List of apps with (app_id, bundle_id, name, sku)
        """
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        env = {
            "APPLE_ID": apple_id,
            "APPLE_PASSWORD": password,
            "TEAM_ID": team_id,
            "FASTLANE_DONT_STORE_PASSWORD": "1",
            "FASTLANE_SKIP_UPDATE_CHECK": "1",
            "SPACESHIP_COOKIE_PATH": cookie_path,
        }
        if verification_code:
            env["VERIFICATION_CODE"] = verification_code
        if team_name:
            env["TEAM_NAME"] = team_name

        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_LIST_APPS_SCRIPT,
            env,
            60,
        )

        logger.info(f"List apps result: {result}")

        if result.get("success"):
            return result.get("apps", [])
        else:
            error = result.get("error", "unknown")
            if error == "session_expired":
                raise AppleSessionExpiredError()
            return []

    async def generate_eas_credentials(
        self,
        apple_id: str,
        password: str,
        team_id: str,
        bundle_identifier: str,
        user_id: str,
        verification_code: str | None = None,
        team_name: str | None = None,
    ) -> dict[str, Any]:
        """Generate credentials.json for EAS local builds.

        This creates or retrieves:
        - iOS Distribution Certificate (with private key if new)
        - App Store Provisioning Profile

        And returns them in credentials.json format for EAS.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            team_id: Selected team ID
            bundle_identifier: The bundle ID (e.g., com.example.app)
            user_id: The user's unique identifier (for session isolation)
            verification_code: Optional 2FA code
            team_name: Team name (used to match team)

        Returns:
            Dict with:
            - credentials: The credentials.json structure for EAS
            - certificate_id, certificate_name, certificate_expiry
            - profile_id, profile_name, profile_expiry
            - has_private_key: Whether a new certificate was created with private key
        """
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        env = {
            "APPLE_ID": apple_id,
            "APPLE_PASSWORD": password,
            "TEAM_ID": team_id,
            "BUNDLE_IDENTIFIER": bundle_identifier,
            "FASTLANE_DONT_STORE_PASSWORD": "1",
            "FASTLANE_SKIP_UPDATE_CHECK": "1",
            "SPACESHIP_COOKIE_PATH": cookie_path,
        }
        if verification_code:
            env["VERIFICATION_CODE"] = verification_code
        if team_name:
            env["TEAM_NAME"] = team_name

        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_GENERATE_EAS_CREDENTIALS_SCRIPT,
            env,
            300,  # 5 minute timeout for credential generation
        )

        logger.info(f"EAS credentials generation result: {result}")

        if result.get("success"):
            return {
                "p12_base64": result.get("p12_base64"),
                "p12_password": result.get("p12_password", ""),
                "provisioning_profile_base64": result.get("provisioning_profile_base64"),
                "certificate_id": result.get("certificate_id"),
                "certificate_name": result.get("certificate_name"),
                "certificate_expiry": result.get("certificate_expiry"),
                "profile_id": result.get("profile_id"),
                "profile_name": result.get("profile_name"),
                "profile_expiry": result.get("profile_expiry"),
                "has_private_key": result.get("has_private_key", False),
                "message": result.get("message"),
            }
        else:
            error = result.get("error", "unknown")
            message = result.get("message", "Credential generation failed")

            if error == "max_certificates":
                raise AppleCertificateError(
                    "Maximum number of iOS Distribution Certificates reached. "
                    "Please revoke an existing certificate in the Apple Developer Portal."
                )
            elif error == "session_expired":
                raise AppleSessionExpiredError()
            elif error == "bundle_id_not_found":
                raise AppleBundleIdError(
                    f"Bundle ID {bundle_identifier} not registered. "
                    "Please complete the App Setup step first."
                )
            else:
                raise AppleCertificateError(message)
