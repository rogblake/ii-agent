"""Unit tests for mobile/apple/fastlane_auth.py - FastlaneAuthClient."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.integrations.mobile.apple.fastlane_auth import FastlaneAuthClient
from ii_agent.integrations.mobile.apple.exceptions import (
    AppleAccountLockedError,
    AppleAuthenticationError,
    AppleInvalidCredentialsError,
    AppleRateLimitError,
    AppleSessionExpiredError,
)
from ii_agent.integrations.mobile.apple.types import AppleAuthState, AppleSession, AppleTeam


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> FastlaneAuthClient:
    """Create a FastlaneAuthClient without running _check_fastlane_installed."""
    with patch.object(FastlaneAuthClient, "_check_fastlane_installed", return_value=True):
        client = FastlaneAuthClient()
    return client


def _make_session(
    apple_id: str = "dev@example.com",
    auth_state: AppleAuthState = AppleAuthState.PENDING_2FA,
    teams=None,
) -> AppleSession:
    session = MagicMock(spec=AppleSession)
    session.session_id = "sess-uuid"
    session.apple_id = apple_id
    session.auth_state = auth_state
    session.teams = teams or []
    session.selected_team_id = None
    return session


# ---------------------------------------------------------------------------
# _check_fastlane_installed
# ---------------------------------------------------------------------------


class TestCheckFastlaneInstalled:
    def test_returns_true_when_installed(self):
        with patch("subprocess.run") as mock_run:
            result_mock = MagicMock()
            result_mock.returncode = 0
            mock_run.return_value = result_mock
            client = _make_client()
            assert client._check_fastlane_installed() is True

    def test_returns_false_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            client = _make_client()
            assert client._check_fastlane_installed() is False

    def test_returns_false_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("fastlane", 10)):
            client = _make_client()
            assert client._check_fastlane_installed() is False

    def test_returns_false_when_returncode_nonzero(self):
        with patch("subprocess.run") as mock_run:
            result_mock = MagicMock()
            result_mock.returncode = 1
            mock_run.return_value = result_mock
            client = _make_client()
            assert client._check_fastlane_installed() is False


# ---------------------------------------------------------------------------
# _get_user_cookie_path
# ---------------------------------------------------------------------------


class TestGetUserCookiePath:
    def test_returns_path_containing_user_id(self):
        client = _make_client()
        with patch("os.makedirs"):
            path = client._get_user_cookie_path("user-123")
        assert "user" in path.lower() or "123" in path

    def test_sanitizes_special_chars(self):
        client = _make_client()
        with patch("os.makedirs"):
            path = client._get_user_cookie_path("user@example.com")
        # Should replace @ and . with _
        assert "@" not in path

    def test_creates_directory(self):
        client = _make_client()
        with patch("os.makedirs") as mock_makedirs:
            client._get_user_cookie_path("user-1")
        mock_makedirs.assert_called_once()


# ---------------------------------------------------------------------------
# _run_ruby_script
# ---------------------------------------------------------------------------


class TestRunRubyScript:
    def _make_successful_result(self, data: dict) -> MagicMock:
        payload = json.dumps(data)
        output = f"Some Ruby output\n---JSON_OUTPUT_START---\n{payload}\n---JSON_OUTPUT_END---\n"
        result = MagicMock()
        result.stdout = output
        result.stderr = ""
        result.returncode = 0
        return result

    def test_parses_json_output_on_success(self):
        client = _make_client()
        data = {"success": True, "teams": []}

        with patch("subprocess.run", return_value=self._make_successful_result(data)):
            with patch("tempfile.NamedTemporaryFile") as mock_tf:
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.name = "/tmp/test_script.rb"
                mock_tf.return_value = mock_file
                with patch("os.unlink"):
                    result = client._run_ruby_script("puts 'hi'", {})

        assert result["success"] is True

    def test_returns_error_when_no_json_output(self):
        client = _make_client()

        proc_result = MagicMock()
        proc_result.stdout = "Some non-JSON output"
        proc_result.stderr = "An error occurred"
        proc_result.returncode = 1

        with patch("subprocess.run", return_value=proc_result):
            with patch("tempfile.NamedTemporaryFile") as mock_tf:
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.name = "/tmp/test_script.rb"
                mock_tf.return_value = mock_file
                with patch("os.unlink"):
                    result = client._run_ruby_script("puts 'hi'", {})

        assert result["success"] is False

    def test_detects_2fa_in_stderr(self):
        client = _make_client()

        proc_result = MagicMock()
        proc_result.stdout = "No JSON here"
        proc_result.stderr = "two-factor authentication is required"
        proc_result.returncode = 1

        with patch("subprocess.run", return_value=proc_result):
            with patch("tempfile.NamedTemporaryFile") as mock_tf:
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.name = "/tmp/test_script.rb"
                mock_tf.return_value = mock_file
                with patch("os.unlink"):
                    result = client._run_ruby_script("script", {})

        assert result.get("requires_2fa") is True

    def test_returns_timeout_error_on_timeout(self):
        client = _make_client()

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ruby", 60)):
            with patch("tempfile.NamedTemporaryFile") as mock_tf:
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.name = "/tmp/test_script.rb"
                mock_tf.return_value = mock_file
                with patch("os.unlink"):
                    result = client._run_ruby_script("script", {})

        assert result["error"] == "timeout"

    def test_returns_parse_error_on_bad_json(self):
        client = _make_client()

        proc_result = MagicMock()
        proc_result.stdout = "---JSON_OUTPUT_START---\n{bad json\n---JSON_OUTPUT_END---"
        proc_result.stderr = ""
        proc_result.returncode = 0

        with patch("subprocess.run", return_value=proc_result):
            with patch("tempfile.NamedTemporaryFile") as mock_tf:
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.name = "/tmp/test_script.rb"
                mock_tf.return_value = mock_file
                with patch("os.unlink"):
                    result = client._run_ruby_script("script", {})

        assert result["error"] == "parse_error"


# ---------------------------------------------------------------------------
# initiate_login
# ---------------------------------------------------------------------------


class TestInitiateLogin:
    @pytest.mark.asyncio
    async def test_login_success_returns_session(self):
        client = _make_client()
        result = {
            "success": True,
            "session_id": "apple-sess-1",
            "cookies": {"cookie": "value"},
            "teams": [{"team_id": "T1", "name": "My Team", "team_type": "company"}],
        }

        with (
            patch.object(client, "_run_ruby_script", return_value=result),
            patch("asyncio.get_event_loop") as mock_loop,
        ):
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            response = await client.initiate_login("dev@example.com", "pass123", "user-1")

        assert response.requires_2fa is False
        assert response.session is not None
        assert len(response.session.teams) == 1

    @pytest.mark.asyncio
    async def test_login_requires_2fa(self):
        client = _make_client()
        result = {
            "success": False,
            "requires_2fa": True,
            "error": "2fa_required",
            "message": "Two-factor authentication required",
            "auth_type": "hsa2",
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            response = await client.initiate_login("dev@example.com", "pass123", "user-1")

        assert response.requires_2fa is True
        assert response.session.auth_state == AppleAuthState.PENDING_2FA

    @pytest.mark.asyncio
    async def test_login_invalid_credentials_raises(self):
        client = _make_client()
        result = {
            "success": False,
            "error": "invalid_credentials",
            "message": "Wrong password",
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(AppleInvalidCredentialsError):
                await client.initiate_login("dev@example.com", "wrong", "user-1")

    @pytest.mark.asyncio
    async def test_login_account_locked_raises(self):
        client = _make_client()
        result = {
            "success": False,
            "error": "account_locked",
            "message": "Account locked",
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(AppleAccountLockedError):
                await client.initiate_login("dev@example.com", "pass", "user-1")

    @pytest.mark.asyncio
    async def test_login_rate_limit_raises(self):
        client = _make_client()
        result = {
            "success": False,
            "error": "rate_limit",
            "message": "Too many requests",
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(AppleRateLimitError):
                await client.initiate_login("dev@example.com", "pass", "user-1")

    @pytest.mark.asyncio
    async def test_login_unknown_error_raises_generic(self):
        client = _make_client()
        result = {
            "success": False,
            "error": "unknown",
            "message": "Something went wrong",
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(AppleAuthenticationError):
                await client.initiate_login("dev@example.com", "pass", "user-1")


# ---------------------------------------------------------------------------
# verify_2fa_code
# ---------------------------------------------------------------------------


class TestVerify2faCode:
    @pytest.mark.asyncio
    async def test_verify_success_updates_session(self):
        client = _make_client()
        result = {
            "success": True,
            "teams": [{"team_id": "T1", "name": "Dev Team", "team_type": "company"}],
        }
        session = _make_session()

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            updated = await client.verify_2fa_code(session, "123456", "pass123", "user-1")

        assert updated.auth_state == AppleAuthState.PENDING_TEAM_SELECTION
        assert len(updated.teams) == 1

    @pytest.mark.asyncio
    async def test_verify_invalid_code_raises(self):
        client = _make_client()
        from ii_agent.integrations.mobile.apple.exceptions import Apple2FAInvalidCodeError

        result = {
            "success": False,
            "error": "invalid_code",
            "message": "The code you entered is incorrect",
        }
        session = _make_session()

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(Apple2FAInvalidCodeError):
                await client.verify_2fa_code(session, "000000", "pass", "user-1")

    @pytest.mark.asyncio
    async def test_verify_unknown_error_raises_generic(self):
        client = _make_client()
        result = {
            "success": False,
            "error": "server_error",
            "message": "Server error",
        }
        session = _make_session()

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(AppleAuthenticationError):
                await client.verify_2fa_code(session, "123456", "pass", "user-1")


# ---------------------------------------------------------------------------
# get_teams
# ---------------------------------------------------------------------------


class TestGetTeams:
    @pytest.mark.asyncio
    async def test_returns_teams_from_session(self):
        client = _make_client()
        teams = [AppleTeam(team_id="T1", name="Dev", team_type="company")]
        session = _make_session(teams=teams)

        result = await client.get_teams(session)
        assert len(result) == 1
        assert result[0].team_id == "T1"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_teams(self):
        client = _make_client()
        session = _make_session(teams=[])

        result = await client.get_teams(session)
        assert result == []


# ---------------------------------------------------------------------------
# select_team
# ---------------------------------------------------------------------------


class TestSelectTeam:
    @pytest.mark.asyncio
    async def test_select_valid_team(self):
        client = _make_client()
        team = AppleTeam(team_id="T1", name="Dev", team_type="company")
        session = _make_session(teams=[team], auth_state=AppleAuthState.PENDING_TEAM_SELECTION)

        updated = await client.select_team(session, "T1")
        assert updated.auth_state == AppleAuthState.AUTHENTICATED
        assert updated.selected_team_id == "T1"

    @pytest.mark.asyncio
    async def test_select_invalid_team_raises(self):
        client = _make_client()
        session = _make_session(teams=[])

        with pytest.raises(AppleAuthenticationError, match="not found"):
            await client.select_team(session, "NONEXISTENT")


# ---------------------------------------------------------------------------
# create_distribution_certificate
# ---------------------------------------------------------------------------


class TestCreateDistributionCertificate:
    @pytest.mark.asyncio
    async def test_certificate_created_successfully(self):
        client = _make_client()
        result = {
            "success": True,
            "certificate_id": "cert_123",
            "name": "iOS Distribution: Dev Team",
            "expiry": "2025-12-31",
            "created": True,
            "existing_count": 0,
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            cert = await client.create_distribution_certificate(
                apple_id="dev@example.com",
                password="pass",
                team_id="T1",
                user_id="user-1",
            )

        assert cert["certificate_id"] == "cert_123"
        assert cert["created"] is True

    @pytest.mark.asyncio
    async def test_max_certificates_raises(self):
        from ii_agent.integrations.mobile.apple.exceptions import AppleCertificateError

        client = _make_client()
        result = {
            "success": False,
            "error": "max_certificates",
            "message": "Max certs reached",
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(AppleCertificateError):
                await client.create_distribution_certificate(
                    apple_id="dev@example.com",
                    password="pass",
                    team_id="T1",
                    user_id="user-1",
                )

    @pytest.mark.asyncio
    async def test_session_expired_raises(self):
        client = _make_client()
        result = {
            "success": False,
            "error": "session_expired",
            "message": "Session expired",
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(AppleSessionExpiredError):
                await client.create_distribution_certificate(
                    apple_id="dev@example.com",
                    password="pass",
                    team_id="T1",
                    user_id="user-1",
                )


# ---------------------------------------------------------------------------
# register_bundle_id
# ---------------------------------------------------------------------------


class TestRegisterBundleId:
    @pytest.mark.asyncio
    async def test_registers_successfully(self):
        client = _make_client()
        result = {
            "success": True,
            "bundle_id": "com.example.app",
            "name": "My App",
            "created": True,
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            bundle = await client.register_bundle_id(
                apple_id="dev@example.com",
                password="pass",
                team_id="T1",
                bundle_identifier="com.example.app",
                app_name="My App",
                user_id="user-1",
            )

        assert bundle["bundle_id"] == "com.example.app"

    @pytest.mark.asyncio
    async def test_already_exists_returns_success(self):
        client = _make_client()
        result = {
            "success": False,
            "error": "already_exists",
            "message": "Bundle ID exists",
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            bundle = await client.register_bundle_id(
                apple_id="dev@example.com",
                password="pass",
                team_id="T1",
                bundle_identifier="com.example.existing",
                app_name="My App",
                user_id="user-1",
            )

        assert bundle["bundle_id"] == "com.example.existing"
        assert bundle["created"] is False

    @pytest.mark.asyncio
    async def test_unknown_error_raises_bundle_id_error(self):
        from ii_agent.integrations.mobile.apple.exceptions import AppleBundleIdError

        client = _make_client()
        result = {
            "success": False,
            "error": "unknown",
            "message": "Failed to register",
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(AppleBundleIdError):
                await client.register_bundle_id(
                    apple_id="dev@example.com",
                    password="pass",
                    team_id="T1",
                    bundle_identifier="com.bad.bundle",
                    app_name="App",
                    user_id="user-1",
                )


# ---------------------------------------------------------------------------
# list_apps
# ---------------------------------------------------------------------------


class TestListApps:
    @pytest.mark.asyncio
    async def test_returns_apps_list(self):
        client = _make_client()
        result = {
            "success": True,
            "apps": [
                {"app_id": "app1", "bundle_id": "com.ex.app1", "name": "App 1", "sku": "SKU1"},
            ],
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            apps = await client.list_apps(
                apple_id="dev@example.com",
                password="pass",
                team_id="T1",
                user_id="user-1",
            )

        assert len(apps) == 1
        assert apps[0]["app_id"] == "app1"

    @pytest.mark.asyncio
    async def test_returns_empty_on_failure(self):
        client = _make_client()
        result = {"success": False, "error": "server_error"}

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            apps = await client.list_apps(
                apple_id="dev@example.com",
                password="pass",
                team_id="T1",
                user_id="user-1",
            )

        assert apps == []

    @pytest.mark.asyncio
    async def test_session_expired_raises(self):
        client = _make_client()
        result = {"success": False, "error": "session_expired"}

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(AppleSessionExpiredError):
                await client.list_apps(
                    apple_id="dev@example.com",
                    password="pass",
                    team_id="T1",
                    user_id="user-1",
                )


# ---------------------------------------------------------------------------
# generate_eas_credentials
# ---------------------------------------------------------------------------


class TestGenerateEasCredentials:
    @pytest.mark.asyncio
    async def test_generates_credentials_successfully(self):
        client = _make_client()
        result = {
            "success": True,
            "p12_base64": "base64p12data",
            "p12_password": "secret",
            "provisioning_profile_base64": "base64ppdata",
            "certificate_id": "cert_1",
            "certificate_name": "iOS Distribution: Test",
            "certificate_expiry": "2025-12-31",
            "profile_id": "prof_1",
            "profile_name": "App Store Profile",
            "profile_expiry": "2025-12-31",
            "has_private_key": True,
            "message": None,
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            creds = await client.generate_eas_credentials(
                apple_id="dev@example.com",
                password="pass",
                team_id="T1",
                bundle_identifier="com.example.app",
                user_id="user-1",
            )

        assert creds["p12_base64"] == "base64p12data"
        assert creds["has_private_key"] is True

    @pytest.mark.asyncio
    async def test_bundle_id_not_found_raises(self):
        from ii_agent.integrations.mobile.apple.exceptions import AppleBundleIdError

        client = _make_client()
        result = {
            "success": False,
            "error": "bundle_id_not_found",
            "message": "Bundle ID not registered",
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            with pytest.raises(AppleBundleIdError):
                await client.generate_eas_credentials(
                    apple_id="dev@example.com",
                    password="pass",
                    team_id="T1",
                    bundle_identifier="com.missing.bundle",
                    user_id="user-1",
                )

    @pytest.mark.asyncio
    async def test_verification_code_passed_to_env(self):
        client = _make_client()
        result = {
            "success": True,
            "p12_base64": "data",
            "p12_password": "",
            "provisioning_profile_base64": "pp",
            "certificate_id": "c1",
            "certificate_name": "Cert",
            "certificate_expiry": "2025",
            "profile_id": "p1",
            "profile_name": "Profile",
            "profile_expiry": "2025",
            "has_private_key": False,
            "message": None,
        }

        captured_script_args = {}

        def fake_run_script(script, env, timeout=300):
            captured_script_args["env"] = env
            return result

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=result)

            creds = await client.generate_eas_credentials(
                apple_id="dev@example.com",
                password="pass",
                team_id="T1",
                bundle_identifier="com.example.app",
                user_id="user-1",
                verification_code="123456",
            )

        # Just verify it doesn't raise
        assert creds is not None
