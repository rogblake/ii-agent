from ii_agent.core.secrets.keys import ALL_SECRETS, SecretKey
from ii_agent.core.secrets.loader import load_secrets


class FakeSecretProvider:
    def __init__(self):
        self.seen_keys = None

    def get_secrets(self, keys):
        self.seen_keys = keys
        return {
            SecretKey.DATABASE_URL: "postgres://localhost/db",
            SecretKey.REDIS_SESSION_URL: "redis://127.0.0.1",
        }


def test_load_secrets_uses_loader_with_full_secret_set():
    provider = FakeSecretProvider()

    result = load_secrets(provider)

    assert provider.seen_keys == ALL_SECRETS
    assert result == {
        SecretKey.DATABASE_URL: "postgres://localhost/db",
        SecretKey.REDIS_SESSION_URL: "redis://127.0.0.1",
    }
