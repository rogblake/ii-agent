"""Apple mobile platform integration exports."""

from ii_agent.integrations.mobile.apple.exceptions import (
    Apple2FAInvalidCodeError,
    Apple2FARequiredError,
    AppleAccountLockedError,
    AppleAPIError,
    AppleAppBundleIdTakenError,
    AppleAppCreationError,
    AppleAppNameTakenError,
    AppleAuthenticationError,
    AppleBundleIdError,
    AppleBundleIdExistsError,
    AppleCertificateError,
    AppleInvalidCredentialsError,
    AppleProvisioningProfileError,
    AppleRateLimitError,
    AppleSessionExpiredError,
    AppleTeamAccessError,
)
from ii_agent.integrations.mobile.apple.fastlane_auth import FastlaneAuthClient
from ii_agent.integrations.mobile.apple.models import AppleAuthState, AppleCredential
from ii_agent.integrations.mobile.apple.repository import AppleCredentialRepository
from ii_agent.integrations.mobile.apple.service import AppleCredentialService, AppleCredentials
from ii_agent.integrations.mobile.apple.types import AppleAuthState, AppleSession, AppleTeam

__all__ = [
    "AppleAPIError",
    "AppleAuthenticationError",
    "AppleInvalidCredentialsError",
    "AppleAccountLockedError",
    "Apple2FARequiredError",
    "Apple2FAInvalidCodeError",
    "AppleSessionExpiredError",
    "AppleRateLimitError",
    "AppleTeamAccessError",
    "AppleBundleIdError",
    "AppleBundleIdExistsError",
    "AppleCertificateError",
    "AppleProvisioningProfileError",
    "AppleAppCreationError",
    "AppleAppNameTakenError",
    "AppleAppBundleIdTakenError",
    "FastlaneAuthClient",
    "AppleAuthState",
    "AppleSession",
    "AppleTeam",
    "AppleAuthState",
    "AppleCredential",
    "AppleCredentialRepository",
    "AppleCredentialService",
    "AppleCredentials",
]
