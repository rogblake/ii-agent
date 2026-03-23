from ii_agent.core.secrets.keys import (
    ALL_SECRETS,
    BILLING_SECRETS,
    COMPOSIO_SECRETS,
    DATABASE_SECRETS,
    LLM_SECRETS,
    OAUTH_SECRETS,
    SecretKey,
    TOOL_SERVER_SECRETS,
)


def test_secret_key_to_gcp_name_uses_default_and_custom_prefix():
    assert SecretKey.DATABASE_URL.to_gcp_name() == "ii-agent-database-url"
    assert SecretKey.DATABASE_URL.to_gcp_name(prefix="prod") == "prod-database-url"


def test_secret_key_to_env_var_returns_name():
    assert SecretKey.SANDBOX_E2B_API_KEY.to_env_var() == "SANDBOX_E2B_API_KEY"


def test_secret_groups_contain_expected_members():
    assert SecretKey.DATABASE_URL in DATABASE_SECRETS
    assert SecretKey.REDIS_SESSION_URL in DATABASE_SECRETS
    assert SecretKey.GOOGLE_CLIENT_SECRET in OAUTH_SECRETS
    assert SecretKey.REVENUECAT_CLIENT_SECRET in OAUTH_SECRETS
    assert SecretKey.STRIPE_SECRET_KEY in BILLING_SECRETS
    assert SecretKey.JWT_SECRET_KEY in LLM_SECRETS
    assert SecretKey.SANDBOX_E2B_API_KEY in TOOL_SERVER_SECRETS
    assert SecretKey.COMPOSIO_WEBHOOK_SECRET in COMPOSIO_SECRETS


def test_all_secrets_union_covers_every_defined_group():
    expected = (
        DATABASE_SECRETS
        | OAUTH_SECRETS
        | BILLING_SECRETS
        | LLM_SECRETS
        | TOOL_SERVER_SECRETS
        | COMPOSIO_SECRETS
    )

    assert ALL_SECRETS == expected
