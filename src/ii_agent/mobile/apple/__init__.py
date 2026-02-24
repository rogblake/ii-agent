"""Apple mobile auth/TestFlight domain exports."""

from ii_agent.mobile.apple.exceptions import (
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
from ii_agent.mobile.apple.fastlane_auth import FastlaneAuthClient
from ii_agent.mobile.apple.models import AppleAuthStateEnum, AppleCredential
from ii_agent.mobile.apple.repository import AppleCredentialRepository
from ii_agent.mobile.apple.service import AppleCredentialService, AppleCredentials
from ii_agent.mobile.apple.types import AppleAuthState, AppleSession, AppleTeam

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
    "AppleAuthStateEnum",
    "AppleCredential",
    "AppleCredentialRepository",
    "AppleCredentialService",
    "AppleCredentials",
]
