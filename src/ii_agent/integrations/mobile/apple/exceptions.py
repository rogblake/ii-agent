"""Custom exceptions for Apple API operations."""


class AppleAPIError(Exception):
    """Base exception for Apple API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AppleAuthenticationError(AppleAPIError):
    """Error during Apple ID authentication."""

    pass


class AppleInvalidCredentialsError(AppleAuthenticationError):
    """Invalid Apple ID or password."""

    def __init__(self, message: str = "Invalid Apple ID or password."):
        super().__init__(message, status_code=401)


class AppleAccountLockedError(AppleAuthenticationError):
    """Apple account is locked."""

    def __init__(
        self, message: str = "Apple account is locked. Please unlock via iforgot.apple.com."
    ):
        super().__init__(message, status_code=423)


class Apple2FARequiredError(AppleAuthenticationError):
    """Two-factor authentication is required."""

    def __init__(self, message: str = "Two-factor authentication required."):
        super().__init__(message, status_code=409)


class Apple2FAInvalidCodeError(AppleAuthenticationError):
    """Invalid 2FA verification code."""

    def __init__(self, message: str = "Invalid verification code. Please try again."):
        super().__init__(message, status_code=400)


class AppleSessionExpiredError(AppleAuthenticationError):
    """Apple session has expired."""

    def __init__(self, message: str = "Apple session has expired. Please sign in again."):
        super().__init__(message, status_code=401)


class AppleRateLimitError(AppleAPIError):
    """Rate limited by Apple API."""

    def __init__(self, message: str = "Too many requests. Please wait a moment and try again."):
        super().__init__(message, status_code=429)


class AppleTeamAccessError(AppleAPIError):
    """Error accessing Apple Developer team."""

    pass


class AppleBundleIdError(AppleAPIError):
    """Error with bundle identifier operations."""

    pass


class AppleBundleIdExistsError(AppleBundleIdError):
    """Bundle identifier already exists."""

    def __init__(self, bundle_id: str):
        super().__init__(f"Bundle identifier '{bundle_id}' already exists.", status_code=409)


class AppleCertificateError(AppleAPIError):
    """Error with certificate operations."""

    pass


class AppleProvisioningProfileError(AppleAPIError):
    """Error with provisioning profile operations."""

    pass


class AppleAppCreationError(AppleAPIError):
    """Error creating app in App Store Connect."""

    pass


class AppleAppNameTakenError(AppleAppCreationError):
    """App name is already taken on the App Store (globally unique).

    This happens when someone else has already used this app name on the App Store.
    The user needs to choose a different name.
    """

    def __init__(self, app_name: str, message: str | None = None):
        self.app_name = app_name
        msg = (
            message
            or f"The app name '{app_name}' is already taken on the App Store. Please choose a different name."
        )
        super().__init__(msg, status_code=409)


class AppleAppBundleIdTakenError(AppleAppCreationError):
    """Bundle ID is already registered by another developer.

    This happens when the bundle ID is already registered in App Store Connect
    by another developer account.
    """

    def __init__(self, bundle_id: str, message: str | None = None):
        self.bundle_id = bundle_id
        msg = (
            message
            or f"The bundle ID '{bundle_id}' is already registered by another developer. Please use a different bundle ID."
        )
        super().__init__(msg, status_code=409)
