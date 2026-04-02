from types import SimpleNamespace


from ii_agent.core.secrets.keys import ALL_SECRETS, SecretKey
from ii_agent.core.secrets.provider import EnvSecretProvider, GCPSecretProvider, SecretProvider


class DummyBaseProvider(SecretProvider):
    def __init__(self):
        self.keys = set()

    def get_secret(self, key: SecretKey):
        self.keys.add(key)
        if key == SecretKey.DATABASE_URL:
            return "postgres://localhost/db"
        return None


class FakeSecretManagerClient:
    def __init__(self, responses):
        self.responses = responses
        self.access_calls = []

    def access_secret_version(self, request):
        self.access_calls.append(request["name"])
        if request["name"] not in self.responses:
            raise RuntimeError(f"secret missing: {request['name']}")
        return SimpleNamespace(
            payload=SimpleNamespace(data=self.responses[request["name"]].encode("utf-8"))
        )


async def test_secret_provider_base_get_secrets_only_includes_found_values():
    provider = DummyBaseProvider()
    result = provider.get_secrets({SecretKey.DATABASE_URL, SecretKey.REDIS_SESSION_URL})

    assert provider.keys == {SecretKey.DATABASE_URL, SecretKey.REDIS_SESSION_URL}
    assert result == {SecretKey.DATABASE_URL: "postgres://localhost/db"}


def test_env_secret_provider_reads_from_environment(monkeypatch):
    monkeypatch.setenv(SecretKey.SESSION_SECRET_KEY.to_env_var(), "session-val")

    provider = EnvSecretProvider()

    assert provider.get_secret(SecretKey.SESSION_SECRET_KEY) == "session-val"


def test_env_secret_provider_returns_none_when_env_var_missing(monkeypatch):
    monkeypatch.delenv(SecretKey.SESSION_SECRET_KEY.to_env_var(), raising=False)

    provider = EnvSecretProvider()

    assert provider.get_secret(SecretKey.SESSION_SECRET_KEY) is None


def test_gcp_secret_provider_caches_successful_secret(monkeypatch):
    client = FakeSecretManagerClient(
        {
            "projects/my-project/secrets/ii-agent-database-url/versions/latest": "postgres://gcp",
        }
    )
    monkeypatch.setattr(
        GCPSecretProvider,
        "_get_client",
        lambda self: client,
    )

    provider = GCPSecretProvider(project_id="my-project")

    first = provider.get_secret(SecretKey.DATABASE_URL)
    second = provider.get_secret(SecretKey.DATABASE_URL)

    assert first == "postgres://gcp"
    assert second == "postgres://gcp"
    assert client.access_calls == [
        "projects/my-project/secrets/ii-agent-database-url/versions/latest",
    ]


def test_gcp_secret_provider_returns_and_caches_none_on_failure(monkeypatch):
    client = FakeSecretManagerClient({})
    monkeypatch.setattr(
        GCPSecretProvider,
        "_get_client",
        lambda self: client,
    )

    provider = GCPSecretProvider(project_id="my-project")

    first = provider.get_secret(SecretKey.DATABASE_URL)
    second = provider.get_secret(SecretKey.DATABASE_URL)

    assert first is None
    assert second is None
    assert client.access_calls == [
        "projects/my-project/secrets/ii-agent-database-url/versions/latest",
    ]


def test_gcp_secret_provider_filters_out_missing_values(monkeypatch):
    client = FakeSecretManagerClient(
        {
            "projects/my-project/secrets/ii-agent-database-url/versions/latest": "postgres://gcp",
            "projects/my-project/secrets/ii-agent-redis-url/versions/latest": "redis://cache",
        }
    )
    monkeypatch.setattr(
        GCPSecretProvider,
        "_get_client",
        lambda self: client,
    )
    provider = GCPSecretProvider(project_id="my-project", prefix="ii-agent")

    result = provider.get_secrets(
        {SecretKey.DATABASE_URL, SecretKey.REDIS_SESSION_URL, SecretKey.GOOGLE_CLIENT_SECRET}
    )

    assert result == {
        SecretKey.DATABASE_URL: "postgres://gcp",
        SecretKey.REDIS_SESSION_URL: "redis://cache",
    }
    assert len(client.access_calls) == 3


def test_loader_like_behavior_calls_all_mapped_secret_names():
    called = {}

    class ProviderSpy(SecretProvider):
        def get_secret(self, key):
            called[key] = True
            if key == SecretKey.DATABASE_URL:
                return "x"
            return None

    provider = ProviderSpy()
    loaded = provider.get_secrets(ALL_SECRETS)

    assert set(called.keys()) == ALL_SECRETS
    assert loaded == {SecretKey.DATABASE_URL: "x"}
