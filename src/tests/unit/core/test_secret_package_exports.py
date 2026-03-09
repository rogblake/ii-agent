import ii_agent.core.secrets as secrets


def test_secret_package_exports_expected_members():
    for expected in [
        "SecretKey",
        "SecretProvider",
        "EnvSecretProvider",
        "GCPSecretProvider",
        "load_secrets",
        "ALL_SECRETS",
        "DATABASE_SECRETS",
        "OAUTH_SECRETS",
        "BILLING_SECRETS",
        "LLM_SECRETS",
        "TOOL_SERVER_SECRETS",
        "COMPOSIO_SECRETS",
        "EncryptionManager",
        "encryption_manager",
    ]:
        assert hasattr(secrets, expected)

    assert "SecretKey" in secrets.__all__
