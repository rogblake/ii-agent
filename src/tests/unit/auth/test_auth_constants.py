from ii_agent.auth import constants


def test_auth_constants_match_expected_values():
    assert constants.GOOGLE_OAUTH_PROVIDER == "google"
    assert constants.GITHUB_OAUTH_PROVIDER == "github"
    assert constants.II_OAUTH_PROVIDER == "ii"
    assert constants.ACCESS_TOKEN_TYPE == "access_token"
    assert constants.REFRESH_TOKEN_TYPE == "refresh_token"
    assert constants.ALGORITHM == "HS256"
    assert constants.ACCESS_TOKEN_EXPIRE_MINUTES == 30
    assert constants.REFRESH_TOKEN_EXPIRE_DAYS == 7


def test_auth_module_exports_constants():
    assert constants.GITHUB_OAUTH_PROVIDER is not None
