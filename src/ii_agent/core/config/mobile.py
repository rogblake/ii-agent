"""Mobile domain configuration settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MobileSettings(BaseSettings):
    """Mobile app configuration.

    Environment variables:
        MOBILE_APPLE_WIDGET_KEY: Apple widget key for IDMSA authentication
    """

    model_config = SettingsConfigDict(
        env_prefix="MOBILE_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    apple_widget_key: str = Field(
        default="83545bf919730e51dbfba24e7e8a78d2",
        description=(
            "Apple widget key for IDMSA authentication "
            "(same key used by EAS CLI and fastlane)"
        ),
    )
