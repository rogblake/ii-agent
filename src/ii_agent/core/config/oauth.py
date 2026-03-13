"""OAuth 2.0 provider configurations."""

import secrets
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OAuth2Settings(BaseSettings):
    """OAuth 2.0 provider configurations for authentication.

    Environment variables (no prefix):
        GOOGLE_CLIENT_ID: Google OAuth client ID
        GOOGLE_CLIENT_SECRET: Google OAuth client secret
        GOOGLE_REDIRECT_URI: Google OAuth redirect URI
        GITHUB_CLIENT_ID: GitHub OAuth client ID
        GITHUB_CLIENT_SECRET: GitHub OAuth client secret
        II_CLIENT_ID: II OAuth client ID
        SESSION_SECRET_KEY: Secret key for session encryption

    Example .env:
        GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
        GOOGLE_CLIENT_SECRET=your-client-secret
        GOOGLE_REDIRECT_URI=http://localhost:8000/auth/oauth/google/callback
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google OAuth configuration
    google_client_id: str = Field(
        default="",
        description="Google OAuth 2.0 client ID",
    )

    google_client_secret: str = Field(
        default="",
        description="Google OAuth 2.0 client secret",
    )

    google_redirect_uri: str = Field(
        default="http://localhost:8000/auth/oauth/google/callback",
        description="Google OAuth 2.0 redirect URI",
    )

    google_picker_developer_key: str = Field(
        default="",
        description="Google Picker API developer key",
    )

    # GitHub OAuth/App configuration
    github_client_id: str = Field(
        default="",
        description="GitHub OAuth client ID",
    )

    github_client_secret: str = Field(
        default="",
        description="GitHub OAuth client secret",
    )

    github_redirect_uri: str = Field(
        default="http://localhost:1420/auth/oauth/github/callback",
        description="GitHub OAuth redirect URI",
    )

    github_app_name: str = Field(
        default="",
        description="GitHub App name",
    )

    github_app_id: str = Field(
        default="",
        description="GitHub App ID (numeric identifier)",
    )

    github_app_private_key: str = Field(
        default="",
        description="GitHub App private key in PEM format (use \\n for newlines)",
    )

    # RevenueCat OAuth configuration
    revenuecat_client_id: str = Field(
        default="",
        description="RevenueCat OAuth client ID",
    )

    revenuecat_client_secret: str = Field(
        default="",
        description="RevenueCat OAuth client secret",
    )

    revenuecat_redirect_uri: str = Field(
        default="http://localhost:1420/auth/oauth/revenuecat/callback",
        description="RevenueCat OAuth redirect URI",
    )

    # II OAuth configuration (Hydra)
    ii_client_id: str = Field(
        default="",
        description="II OAuth client ID",
    )

    ii_redirect_uri: str = Field(
        default="http://localhost:8000/auth/oauth/ii/callback",
        description="II OAuth redirect URI",
    )

    ii_auth_base: str = Field(
        default="https://ii.inc/hydra",
        description="II OAuth authorization server base URL",
    )

    ii_scope: str = Field(
        default="openid offline profile email",
        description="II OAuth scopes",
    )

    ii_use_userinfo: bool = Field(
        default=False,
        description="Use userinfo endpoint for II OAuth",
    )

    ii_userinfo_url: Optional[str] = Field(
        default=None,
        description="II OAuth userinfo endpoint URL",
    )

    # Session management
    session_secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret key for session cookie encryption (auto-generated if not provided)",
    )

    def has_google_oauth(self) -> bool:
        """Check if Google OAuth is configured."""
        return bool(self.google_client_id and self.google_client_secret)

    def has_github_oauth(self) -> bool:
        """Check if GitHub OAuth is configured."""
        return bool(self.github_client_id and self.github_client_secret)

    def has_github_app(self) -> bool:
        """Check if GitHub App is configured."""
        return bool(self.github_app_id and self.github_app_private_key)

    def has_revenuecat_oauth(self) -> bool:
        """Check if RevenueCat OAuth is configured.

        RevenueCat supports both confidential clients (client secret) and
        public PKCE clients (no client secret). The client ID is the only
        required value for the authorization flow to start.
        """
        return bool(self.revenuecat_client_id)

    def has_ii_oauth(self) -> bool:
        """Check if II OAuth is configured."""
        return bool(self.ii_client_id)
