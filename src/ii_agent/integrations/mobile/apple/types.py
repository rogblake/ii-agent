"""Type definitions for Apple API operations."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AppleAuthState(str, Enum):
    """Apple authentication flow states."""

    PENDING_LOGIN = "pending_login"
    PENDING_2FA = "pending_2fa"
    PENDING_TEAM_SELECTION = "pending_team_selection"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"


class TwoFactorMethod(str, Enum):
    """2FA delivery methods."""

    TRUSTED_DEVICE = "trusteddevice"
    SMS = "sms"
    PHONE_CALL = "phone"


class AppleTeam(BaseModel):
    """Apple Developer Team information."""

    team_id: str
    name: str
    team_type: str  # individual, organization, enterprise, in-house
    status: str | None = None  # active, expired, etc.

    class Config:
        extra = "allow"


class TrustedPhoneNumber(BaseModel):
    """Trusted phone number for SMS 2FA."""

    id: int
    number_with_dial_code: str
    push_mode: str | None = None
    obfuscated_number: str | None = None


class AppleSession(BaseModel):
    """Apple session data after authentication."""

    session_id: str
    scnt: str  # Session token from IDMSA
    x_apple_id_session_id: str
    auth_state: AppleAuthState
    apple_id: str  # User's Apple ID email

    # Authentication tokens/cookies
    cookies: dict[str, str] = Field(default_factory=dict)

    # Additional auth data
    auth_type: str | None = None  # hsa2, hsa, etc.
    trusted_phone_numbers: list[TrustedPhoneNumber] = Field(default_factory=list)

    # Team information (populated after auth)
    teams: list[AppleTeam] = Field(default_factory=list)
    selected_team_id: str | None = None

    # Session expiry
    expiry: datetime | None = None

    class Config:
        extra = "allow"


class TwoFactorRequest(BaseModel):
    """2FA verification request."""

    code: str = Field(..., min_length=6, max_length=6)
    method: TwoFactorMethod = TwoFactorMethod.TRUSTED_DEVICE


class BundleIdPlatform(str, Enum):
    """Platform for bundle identifier."""

    IOS = "IOS"
    MAC_OS = "MAC_OS"
    UNIVERSAL = "UNIVERSAL"


class BundleIdCapability(str, Enum):
    """iOS capabilities for bundle ID."""

    PUSH_NOTIFICATIONS = "PUSH_NOTIFICATIONS"
    ASSOCIATED_DOMAINS = "ASSOCIATED_DOMAINS"
    IN_APP_PURCHASE = "IN_APP_PURCHASE"
    GAME_CENTER = "GAME_CENTER"
    SIGN_IN_WITH_APPLE = "SIGN_IN_WITH_APPLE"
    APP_GROUPS = "APP_GROUPS"
    ICLOUD = "ICLOUD"
    ACCESS_WIFI_INFORMATION = "ACCESS_WIFI_INFORMATION"
    APPLE_PAY = "APPLE_PAY"
    SIRI = "SIRI"
    HEALTHKIT = "HEALTHKIT"
    HOMEKIT = "HOMEKIT"
    WALLET = "WALLET"
    NFC_TAG_READING = "NFC_TAG_READING"


class BundleId(BaseModel):
    """Bundle identifier information."""

    id: str  # Apple's internal ID
    identifier: str  # The actual bundle ID (e.g., com.example.app)
    name: str
    platform: BundleIdPlatform
    seed_id: str | None = None

    class Config:
        extra = "allow"


class CertificateType(str, Enum):
    """Certificate types."""

    IOS_DISTRIBUTION = "IOS_DISTRIBUTION"
    IOS_DEVELOPMENT = "IOS_DEVELOPMENT"
    MAC_APP_DISTRIBUTION = "MAC_APP_DISTRIBUTION"
    MAC_INSTALLER_DISTRIBUTION = "MAC_INSTALLER_DISTRIBUTION"
    DEVELOPER_ID_APPLICATION = "DEVELOPER_ID_APPLICATION"
    DEVELOPER_ID_INSTALLER = "DEVELOPER_ID_INSTALLER"


class Certificate(BaseModel):
    """Distribution certificate information."""

    id: str
    serial_number: str
    name: str
    certificate_type: CertificateType
    expiry_date: datetime
    certificate_content: str | None = None  # Base64 encoded .cer

    class Config:
        extra = "allow"


class ProfileType(str, Enum):
    """Provisioning profile types."""

    IOS_APP_STORE = "IOS_APP_STORE"
    IOS_APP_ADHOC = "IOS_APP_ADHOC"
    IOS_APP_DEVELOPMENT = "IOS_APP_DEVELOPMENT"
    IOS_APP_INHOUSE = "IOS_APP_INHOUSE"
    MAC_APP_STORE = "MAC_APP_STORE"
    MAC_APP_DEVELOPMENT = "MAC_APP_DEVELOPMENT"
    MAC_APP_DIRECT = "MAC_APP_DIRECT"


class ProvisioningProfile(BaseModel):
    """Provisioning profile information."""

    id: str
    name: str
    profile_type: ProfileType
    bundle_id: str  # The bundle identifier string
    expiry_date: datetime
    profile_content: str | None = None  # Base64 encoded .mobileprovision
    uuid: str | None = None

    class Config:
        extra = "allow"


class AppStoreApp(BaseModel):
    """App Store Connect app information."""

    id: str  # Apple's internal app ID
    bundle_id: str
    name: str
    sku: str
    primary_locale: str = "en-US"
    content_rights_declaration: str | None = None

    class Config:
        extra = "allow"


class AppStoreVersion(BaseModel):
    """App Store version information."""

    id: str
    version_string: str
    platform: str
    app_store_state: str
    created_date: datetime | None = None

    class Config:
        extra = "allow"


# Response types for API operations


class LoginResponse(BaseModel):
    """Response from Apple ID login."""

    session: AppleSession
    requires_2fa: bool
    auth_type: str | None = None


class TeamListResponse(BaseModel):
    """Response from team listing."""

    teams: list[AppleTeam]


class BundleIdResponse(BaseModel):
    """Response from bundle ID operations."""

    bundle_id: BundleId
    created: bool = False  # True if newly created


class CertificateListResponse(BaseModel):
    """Response from certificate listing."""

    certificates: list[Certificate]


class ProvisioningProfileResponse(BaseModel):
    """Response from provisioning profile operations."""

    profile: ProvisioningProfile
    created: bool = False


class AppSetupResult(BaseModel):
    """Result of complete app setup operation."""

    bundle_id: BundleId
    certificate: Certificate | None = None
    provisioning_profile: ProvisioningProfile | None = None
    app: AppStoreApp | None = None
    credentials_ready: bool = False
