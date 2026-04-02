"""Constants for auth domain."""

# OAuth providers
GOOGLE_OAUTH_PROVIDER = "google"
GITHUB_OAUTH_PROVIDER = "github"
II_OAUTH_PROVIDER = "ii"

# Token types
ACCESS_TOKEN_TYPE = "access_token"
REFRESH_TOKEN_TYPE = "refresh_token"

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# TODO: Add more constants from server/auth/
