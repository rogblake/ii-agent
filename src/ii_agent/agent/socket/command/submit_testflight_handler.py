"""Handler for submitting apps to TestFlight via EAS Build and Submit."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastmcp.client.client import CallToolResult

from ii_agent.core.db.manager import get_db_session_local
from ii_agent.mobile.apple import AppleAuthStateEnum, AppleCredentials, FastlaneAuthClient
from ii_agent.core.events.models import EventType, RealtimeEvent
from ii_agent.core.events.stream import EventStream
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.sandboxes.e2b import E2BSandboxManager
from ii_agent.agent.sandboxes.sandbox_client import MCPClient

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer

logger = logging.getLogger(__name__)


class SubmitTestflightHandler(CommandHandler):
    """Handler for building and submitting apps to TestFlight.

    This handler uses stored Apple credentials from the authentication flow
    to build the iOS app with EAS Build and submit it to TestFlight.
    """

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.SUBMIT_TESTFLIGHT

    async def handle(
        self, content: dict[str, Any], session_info: SessionInfo
    ) -> None:
        """Handle TestFlight build and submission request.

        This handler retrieves stored Apple credentials and Expo token,
        then builds and submits the app to TestFlight.

        Content:
            - expo_token: Expo access token (optional if already stored)
            - bundle_identifier: iOS bundle identifier (optional, from app setup)
            - asc_app_id: App Store Connect App ID (required for auto-submit)
            - app_specific_password: App-Specific Password for auto-submit (optional if stored)
        """
        # Get expo token from request or stored credentials
        expo_token = content.get("expo_token", "").strip()
        custom_bundle_id = content.get("bundle_identifier", "").strip()
        asc_app_id = content.get("asc_app_id", "").strip()
        app_specific_password = content.get("app_specific_password", "").strip()

        try:
            # Get authenticated Apple credential
            credential = await AppleCredentials.get_active_session(
                str(session_info.user_id)
            )

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

            # Get session data for credentials
            session_data = AppleCredentials.get_decrypted_session_data(credential)

            # Get stored expo token if not provided in request
            if not expo_token:
                expo_token = AppleCredentials.get_decrypted_expo_token(credential)

            if not expo_token:
                await self._send_error_event(
                    session_info.id,
                    message="Expo token is required. Please provide it in the Expo Setup step.",
                    error_type="validation_error",
                )
                return

            # Get Apple password from stored session
            apple_password = session_data.get("_temp_password") if session_data else None

            if not apple_password:
                await self._send_error_event(
                    session_info.id,
                    message="Apple session expired. Please re-authenticate with Apple.",
                    error_type="session_expired",
                )
                return

            # Clear the password from DB immediately after retrieving (security best practice)
            # We don't store passwords long-term - users must re-authenticate each deploy
            await AppleCredentials.clear_session_password(str(session_info.user_id))
            logger.info("Cleared stored Apple password after retrieval")

            # Handle App-Specific Password for auto-submit
            # If provided in request, save it for future use
            if app_specific_password:
                await AppleCredentials.save_app_specific_password(
                    str(session_info.user_id), app_specific_password
                )
                logger.info("Saved new App-Specific Password for user")
            else:
                # Get stored App-Specific Password
                app_specific_password = AppleCredentials.get_decrypted_app_specific_password(credential)

            if not app_specific_password:
                await self._send_error_event(
                    session_info.id,
                    message="App-Specific Password is required for auto-submit to TestFlight. Please provide it in the App Setup step.",
                    error_type="validation_error",
                )
                return

            apple_id = credential.apple_id
            team_id = credential.selected_team_id

        except Exception as e:
            logger.exception(f"Error retrieving credentials: {e}")
            await self._send_error_event(
                session_info.id,
                message="Failed to retrieve stored credentials. Please try again.",
                error_type="unexpected_error",
            )
            return

        # Send initial status
        await self._send_testflight_log(
            session_info.id,
            "Starting TestFlight submission...",
            status="running",
        )

        try:
            # Get sandbox URL and manager based on API version
            sandbox_url, sandbox_manager = await self._get_sandbox_url_and_manager(session_info)
            if not sandbox_url:
                await self._send_error_event(
                    session_info.id,
                    message="No sandbox found for session. Please refresh the page and try again.",
                    error_type="sandbox_error",
                )
                return

            # Build environment variable exports for EAS CLI authentication
            env_exports = [
                f'export EXPO_TOKEN="{expo_token}"',
                f'export EXPO_APPLE_ID="{apple_id}"',
            ]
            if team_id:
                env_exports.append(f'export EXPO_APPLE_TEAM_ID="{team_id}"')

            # Add Apple password for EAS build and submit
            escaped_password = apple_password.replace("'", "'\\''")
            env_exports.append(f"export EXPO_APPLE_PASSWORD='{escaped_password}'")

            # Add App-Specific Password for auto-submit to TestFlight
            escaped_app_specific_password = app_specific_password.replace("'", "'\\''")
            env_exports.append(f"export EXPO_APPLE_APP_SPECIFIC_PASSWORD='{escaped_app_specific_password}'")

            env_string = " && ".join(env_exports)

            # Determine the project directory from the database
            project_dir = await self._get_project_path(session_info)
            if not project_dir:
                await self._send_error_event(
                    session_info.id,
                    message="No mobile app project found for this session. Please initialize a mobile app first.",
                    error_type="project_not_found",
                )
                return

            # Determine bundle identifier
            if custom_bundle_id:
                bundle_identifier = custom_bundle_id
            else:
                # Generate bundle identifier from project name as fallback
                project_name = "app"
                async with get_db_session_local() as db:
                    project = await self.container.project_service.get_session_project_or_none(
                        db,
                        session_id=str(session_info.id),
                        user_id=str(session_info.user_id),
                    )
                    if project and project.name:
                        project_name = project.name
                sanitized_name = "".join(
                    c if c.isalnum() or c == "-" else "" for c in project_name
                ).lower()
                bundle_identifier = f"com.iiagent.{sanitized_name}"

            # Execute the command via MCP client
            async with MCPClient(sandbox_url) as client:
                # Initialize bash session
                shell_session_name = f"testflight-{str(session_info.id)[:8]}"
                await client.call_tool("BashInit", {"session_name": shell_session_name})

                # Step 1: Configure iOS bundle identifier and increment build number in app.json
                await self._send_testflight_log(
                    session_info.id,
                    f"Configuring iOS bundle identifier: {bundle_identifier} and incrementing build number...",
                    status="running",
                )

                # Use jq to update app.json with ios.bundleIdentifier, slug, and infoPlist config
                # Convert bundle ID to slug format: com.example.myapp -> com-example-myapp
                slug_from_bundle = bundle_identifier.replace(".", "-")

                # Configure ITSAppUsesNonExemptEncryption to avoid App Store Connect warning
                # Also set ios.buildNumber for each TestFlight submission
                # The buildNumber must be unique and higher than any previous upload
                # Use timestamp-based build number to guarantee uniqueness even if app.json
                # doesn't have buildNumber set (Expo defaults to "1" which may already exist)
                update_app_json_cmd = f'''
cd {project_dir} && \\
if [ -f app.json ]; then
  # Generate timestamp-based build number (seconds since epoch)
  # This guarantees a unique, always-increasing build number
  NEW_BUILD=$(date +%s)
  echo "Setting iOS build number to timestamp: $NEW_BUILD"
  # Update app.json with all iOS settings including the timestamp-based buildNumber
  jq --arg buildNum "$NEW_BUILD" '.expo.ios.bundleIdentifier = "{bundle_identifier}" | .expo.slug = "{slug_from_bundle}" | .expo.ios.infoPlist.ITSAppUsesNonExemptEncryption = false | .expo.ios.buildNumber = $buildNum' app.json > app.json.tmp && mv app.json.tmp app.json
  echo "Updated app.json with bundle identifier, slug, infoPlist config, and buildNumber: $NEW_BUILD"
else
  echo "app.json not found"
fi
'''
                update_result = await client.call_tool(
                    "Bash",
                    {
                        "session_name": shell_session_name,
                        "command": update_app_json_cmd,
                        "description": "Update app.json with iOS bundle identifier and build number",
                        "timeout": 30,
                        "wait_for_output": True,
                    },
                )

                # Log the build number update result
                update_output = self._extract_tool_output(update_result)
                logger.info(f"app.json update result: {update_output}")

                await asyncio.sleep(1)

                # Step 2: Get or generate iOS credentials (certificate + provisioning profile)
                # First, check if we have cached credentials for this bundle identifier
                cached_credentials = AppleCredentials.get_ios_credentials(
                    credential, bundle_identifier
                )

                if cached_credentials:
                    # Reuse cached credentials - avoids Apple's certificate limit (3 max)
                    await self._send_testflight_log(
                        session_info.id,
                        "Using cached iOS signing credentials (valid certificate found)...",
                        status="running",
                    )
                    p12_base64 = cached_credentials['p12_base64']
                    p12_password = cached_credentials['p12_password']
                    profile_base64 = cached_credentials['provisioning_profile_base64']
                    logger.info(
                        f"Reusing cached iOS credentials for bundle {bundle_identifier}, "
                        f"cert_id={cached_credentials.get('certificate_id')}, "
                        f"expires={cached_credentials.get('certificate_expiry')}"
                    )
                else:
                    # Generate new credentials
                    await self._send_testflight_log(
                        session_info.id,
                        "Generating new iOS signing credentials...",
                        status="running",
                    )

                    # Use FastlaneAuthClient to generate credentials.json for local builds
                    fastlane_client = FastlaneAuthClient()
                    try:
                        cred_result = await fastlane_client.generate_eas_credentials(
                            apple_id=apple_id,
                            password=apple_password,
                            team_id=team_id,
                            bundle_identifier=bundle_identifier,
                            user_id=str(session_info.user_id),
                            team_name=credential.team_name if hasattr(credential, 'team_name') else None,
                        )

                        # Extract credentials from result
                        p12_base64 = cred_result.get('p12_base64')
                        p12_password = cred_result.get('p12_password', '')
                        profile_base64 = cred_result.get('provisioning_profile_base64')

                        # Verify credentials were generated
                        if not p12_base64 or not profile_base64:
                            await self._send_testflight_log(
                                session_info.id,
                                f"Credential generation returned incomplete credentials. Result: {cred_result}",
                                status="failed",
                                is_error=True,
                            )
                            return

                        await self._send_testflight_log(
                            session_info.id,
                            f"Generated credentials: {cred_result.get('message', 'Success')}",
                            status="running",
                        )

                        # Cache the newly generated credentials for future deploys
                        # This avoids hitting Apple's certificate limit (3 max)
                        try:
                            await AppleCredentials.save_ios_credentials(
                                user_id=str(session_info.user_id),
                                bundle_identifier=bundle_identifier,
                                p12_base64=p12_base64,
                                p12_password=p12_password,
                                provisioning_profile_base64=profile_base64,
                                certificate_id=cred_result.get('certificate_id'),
                            )
                            logger.info(
                                f"Cached iOS credentials for bundle {bundle_identifier}"
                            )
                        except Exception as cache_error:
                            # Non-fatal: credentials were generated, just couldn't cache
                            logger.warning(
                                f"Failed to cache iOS credentials: {cache_error}"
                            )

                    except Exception as cred_error:
                        logger.error(f"Failed to generate credentials: {cred_error}")
                        await self._send_testflight_log(
                            session_info.id,
                            f"Failed to generate iOS credentials: {str(cred_error)}",
                            status="failed",
                            is_error=True,
                        )
                        return

                # Write credential files to sandbox
                await self._send_testflight_log(
                    session_info.id,
                    "Writing credential files to sandbox...",
                    status="running",
                )

                # Create certs directory
                certs_dir = f"{project_dir}/certs"
                p12_path = f"{certs_dir}/distribution.p12"
                profile_path = f"{certs_dir}/profile.mobileprovision"

                # Decode base64 credentials
                p12_content = base64.b64decode(p12_base64)
                profile_content = base64.b64decode(profile_base64)

                if sandbox_manager:
                    # Create certs directory
                    try:
                        await sandbox_manager.run_command(f"mkdir -p {certs_dir}")
                    except Exception:
                        pass  # Directory might already exist

                    # Write P12 file
                    try:
                        await sandbox_manager.write_file(p12_path, p12_content)
                        logger.info("Successfully wrote P12 file via sandbox manager")
                    except Exception as write_error:
                        logger.error(f"Failed to write P12 file: {write_error}")
                        await self._send_testflight_log(
                            session_info.id,
                            f"Failed to write P12 file: {str(write_error)}",
                            status="failed",
                            is_error=True,
                        )
                        return

                    # Write provisioning profile
                    try:
                        await sandbox_manager.write_file(profile_path, profile_content)
                        logger.info("Successfully wrote provisioning profile via sandbox manager")
                    except Exception as write_error:
                        logger.error(f"Failed to write provisioning profile: {write_error}")
                        await self._send_testflight_log(
                            session_info.id,
                            f"Failed to write provisioning profile: {str(write_error)}",
                            status="failed",
                            is_error=True,
                        )
                        return
                else:
                    # Fallback: use MCP Bash for non-v1 sessions
                    mkdir_cmd = f"mkdir -p {certs_dir}"
                    await client.call_tool(
                        "Bash",
                        {
                            "session_name": shell_session_name,
                            "command": mkdir_cmd,
                            "description": "Create certs directory",
                            "timeout": 30,
                            "wait_for_output": True,
                        },
                    )

                    # Write files via base64
                    write_p12_cmd = f"echo '{p12_base64}' | base64 -d > {p12_path}"
                    await client.call_tool(
                        "Bash",
                        {
                            "session_name": shell_session_name,
                            "command": write_p12_cmd,
                            "description": "Write P12 file",
                            "timeout": 30,
                            "wait_for_output": True,
                        },
                    )

                    write_profile_cmd = f"echo '{profile_base64}' | base64 -d > {profile_path}"
                    await client.call_tool(
                        "Bash",
                        {
                            "session_name": shell_session_name,
                            "command": write_profile_cmd,
                            "description": "Write provisioning profile",
                            "timeout": 30,
                            "wait_for_output": True,
                        },
                    )

                # Build credentials.json with file paths (EAS format)
                credentials_json = {
                    "ios": {
                        "provisioningProfilePath": "certs/profile.mobileprovision",
                        "distributionCertificate": {
                            "path": "certs/distribution.p12",
                            "password": p12_password
                        }
                    }
                }

                # Create eas.json with local credentials
                # Build submit config with ascAppId and appleId for auto-submit
                submit_ios_config: dict[str, Any] = {
                    "appleId": apple_id,
                }
                if asc_app_id:
                    submit_ios_config["ascAppId"] = asc_app_id

                eas_json_content = json.dumps({
                    "cli": {"version": ">= 3.0.0"},
                    "build": {
                        "development": {
                            "developmentClient": True,
                            "distribution": "internal",
                            "credentialsSource": "local"
                        },
                        "preview": {
                            "distribution": "internal",
                            "credentialsSource": "local"
                        },
                        "production": {
                            "credentialsSource": "local"
                        }
                    },
                    "submit": {
                        "production": {
                            "ios": submit_ios_config
                        }
                    }
                }, indent=2)

                eas_json_path = f"{project_dir}/eas.json"

                if sandbox_manager:
                    # Use sandbox manager for v1 sessions
                    try:
                        await sandbox_manager.write_file(eas_json_path, eas_json_content)
                        logger.info("Successfully wrote eas.json via sandbox manager")
                    except Exception as write_error:
                        logger.error(f"Failed to write eas.json via sandbox manager: {write_error}")
                        await self._send_testflight_log(
                            session_info.id,
                            f"Failed to write eas.json: {str(write_error)}",
                            status="failed",
                            is_error=True,
                        )
                        return
                else:
                    # Fallback: use MCP Bash for non-v1 sessions
                    create_eas_json_cmd = f'''
cd {project_dir} && \\
cat > eas.json << 'EASJSON'
{eas_json_content}
EASJSON
echo "Created eas.json with local credentials"
'''
                    await client.call_tool(
                        "Bash",
                        {
                            "session_name": shell_session_name,
                            "command": create_eas_json_cmd,
                            "description": "Create eas.json configuration",
                            "timeout": 30,
                            "wait_for_output": True,
                        },
                    )

                # Write credentials.json to the sandbox using sandbox manager for reliability
                credentials_json_str = json.dumps(credentials_json, indent=2)
                logger.info(f"Credentials JSON size: {len(credentials_json_str)} bytes")

                credentials_file_path = f"{project_dir}/credentials.json"

                if sandbox_manager:
                    # Use sandbox manager's write_file for v1 sessions (more reliable for large files)
                    try:
                        await sandbox_manager.write_file(credentials_file_path, credentials_json_str)
                        logger.info("Successfully wrote credentials.json via sandbox manager")
                    except Exception as write_error:
                        logger.error(f"Failed to write credentials.json via sandbox manager: {write_error}")
                        await self._send_testflight_log(
                            session_info.id,
                            f"Failed to write credentials.json: {str(write_error)}",
                            status="failed",
                            is_error=True,
                        )
                        return
                else:
                    # Fallback: use MCP Bash with printf for non-v1 sessions
                    # Split into chunks to avoid shell argument limits
                    credentials_b64 = base64.b64encode(credentials_json_str.encode()).decode()

                    # Write using printf which handles large strings better than echo
                    write_credentials_cmd = f'''
cd {project_dir} && \\
printf '%s' '{credentials_b64}' | base64 -d > credentials.json && \\
echo "Created credentials.json" && \\
ls -la credentials.json
'''
                    await client.call_tool(
                        "Bash",
                        {
                            "session_name": shell_session_name,
                            "command": write_credentials_cmd,
                            "description": "Write credentials.json",
                            "timeout": 30,
                            "wait_for_output": True,
                        },
                    )

                # Verify all credential files exist
                verify_cmd = f"cd {project_dir} && ls -la credentials.json certs/distribution.p12 certs/profile.mobileprovision && cat credentials.json"
                verify_result = await client.call_tool(
                    "Bash",
                    {
                        "session_name": shell_session_name,
                        "command": verify_cmd,
                        "description": "Verify credential files",
                        "timeout": 30,
                        "wait_for_output": True,
                    },
                )
                verify_output = self._extract_tool_output(verify_result)
                logger.info(f"Verify credential files: {verify_output[:500]}")

                if "No such file" in verify_output:
                    await self._send_testflight_log(
                        session_info.id,
                        f"Failed to write credential files to sandbox. Output: {verify_output[:200]}",
                        status="failed",
                        is_error=True,
                    )
                    return

                await asyncio.sleep(1)

                # Step 3: Initialize EAS project
                await self._send_testflight_log(
                    session_info.id,
                    "Initializing EAS project...",
                    status="running",
                )

                # Run eas init to create/link the EAS project
                # The slug is now based on bundle_identifier so it should be unique per app
                eas_init_cmd = f'''
cd {project_dir} && \\
{env_string} && \\
eas init 2>&1
'''
                init_result = await client.call_tool(
                    "Bash",
                    {
                        "session_name": shell_session_name,
                        "command": eas_init_cmd,
                        "description": "Initialize EAS project",
                        "timeout": 120,
                        "wait_for_output": True,
                    },
                )
                init_output = self._extract_tool_output(init_result)
                logger.info(f"EAS init output: {init_output}")

                await self._send_testflight_log(
                    session_info.id,
                    "EAS project initialized",
                    status="running",
                )

                await asyncio.sleep(1)

                # Step 4: Run EAS Build with auto-submit
                await self._send_testflight_log(
                    session_info.id,
                    "Starting EAS Build for iOS with auto-submit to TestFlight...",
                    status="running",
                )

                # Build the iOS app with --auto-submit
                # Use --no-wait so we don't block (free plan builds can be queued)
                build_command = f'''
cd {project_dir} && \\
{env_string} && \\
npx eas-cli build --platform ios --profile production --auto-submit --non-interactive --no-wait 2>&1
'''
                build_result = await client.call_tool(
                    "Bash",
                    {
                        "session_name": shell_session_name,
                        "command": build_command,
                        "description": "Run EAS Build for iOS with auto-submit",
                        "timeout": 180,
                        "wait_for_output": True,
                    },
                )

                build_output = self._extract_tool_output(build_result)

                # Log build output
                await self._send_testflight_log(
                    session_info.id,
                    f"Build output:\n{build_output[-2000:]}",
                    status="running",
                )

                # Check if build was queued successfully
                build_queued = "Uploaded to EAS" in build_output or "See logs:" in build_output
                has_error = "error" in build_output.lower() and "build command failed" in build_output.lower()

                if has_error and not build_queued:
                    await self._send_testflight_log(
                        session_info.id,
                        f"Build failed:\n{build_output[-1000:]}",
                        status="failed",
                        is_error=True,
                    )
                    return

                # Extract build URL from output
                build_url = None
                for line in build_output.split('\n'):
                    if 'expo.dev' in line and '/builds/' in line:
                        import re
                        url_match = re.search(r'https://expo\.dev[^\s]+', line)
                        if url_match:
                            build_url = url_match.group(0)
                            break

                # Build queued successfully with auto-submit
                success_message = "Build queued on EAS servers with auto-submit enabled! "
                if build_url:
                    success_message += f"Monitor progress at: {build_url} "
                success_message += (
                    "Your app will be automatically submitted to TestFlight after the build completes."
                )

                await self._send_testflight_log(
                    session_info.id,
                    success_message,
                    status="completed",
                )

        except Exception as e:
            logger.exception(f"TestFlight submission failed: {e}")
            await self._send_testflight_log(
                session_info.id,
                f"TestFlight submission failed: {str(e)}",
                status="failed",
                is_error=True,
            )

    async def _get_sandbox_url_and_manager(
        self,
        session_info: SessionInfo,
    ) -> tuple[str | None, E2BSandboxManager | None]:
        """Get the sandbox URL and manager for the session."""
        try:
            async with get_db_session_local() as db:
                sandbox_record = (
                    await self.container.sandbox_service.resolve_sandbox_for_session(
                        db,
                        session_info.id,
                        session_service=self.container.session_service,
                    )
                )

            if not sandbox_record or not sandbox_record.provider_sandbox_id:
                return None, None

            sandbox_manager = await E2BSandboxManager.connect(
                sandbox_id=str(sandbox_record.id),
                session_id=str(sandbox_record.session_id),
                provider_sandbox_id=sandbox_record.provider_sandbox_id,
            )
            url = await sandbox_manager.expose_port(self.container.config.mcp.port)
            return url, sandbox_manager
        except Exception as e:
            logger.error(f"Failed to get sandbox URL: {e}")
            return None, None

    async def _get_project_path(self, session_info: SessionInfo) -> str | None:
        """Get the mobile app project path from the database."""
        try:
            async with get_db_session_local() as db:
                project = await self.container.project_service.get_session_project_or_none(
                    db,
                    session_id=str(session_info.id),
                    user_id=str(session_info.user_id),
                )
                if project:
                    return project.project_path
        except Exception as e:
            logger.error(f"Failed to get project path: {e}")
        return None

    def _extract_tool_output(self, result: CallToolResult) -> str:
        structured = result.structured_content or {}
        display = structured.get("user_display_content")
        if isinstance(display, str):
            return display
        if isinstance(display, list):
            return "\n".join(str(item) for item in display)

        texts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                texts.append(text)
        return "\n".join(texts)

    async def _send_testflight_log(
        self,
        session_id: str | uuid.UUID,
        message: str,
        status: str = "running",
        is_error: bool = False,
    ) -> None:
        """Send TestFlight log event to the frontend."""
        session_uuid = (
            uuid.UUID(session_id) if isinstance(session_id, str) else session_id
        )

        await self.send_event(
            RealtimeEvent(
                session_id=session_uuid,
                type=EventType.TESTFLIGHT_LOG,
                content={
                    "message": message,
                    "status": status,
                    "is_error": is_error,
                },
            )
        )
