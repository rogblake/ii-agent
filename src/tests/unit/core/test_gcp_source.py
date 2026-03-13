import ii_agent.core.secrets.provider as provider_module
import pytest

from ii_agent.core.config.gcp_source import GCPSecretManagerSource
from ii_agent.core.config.settings import Settings
from ii_agent.core.secrets.keys import SecretKey


def test_gcp_source_returns_empty_when_project_id_missing(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)

    source = GCPSecretManagerSource(Settings)

    assert source._load_secrets() == {}
    assert source() == {}


def test_gcp_source_get_field_value_returns_no_direct_value(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    source = GCPSecretManagerSource(Settings)

    assert source.get_field_value(field=None, field_name="jwt_secret_key") == (
        None,
        "jwt_secret_key",
        False,
    )


def test_gcp_source_maps_nested_and_top_level_fields(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")
    monkeypatch.setenv("GCP_SECRET_PREFIX", "custom-prefix")

    class FakeProvider:
        init_args = None
        seen_keys = None

        def __init__(self, project_id, prefix):
            FakeProvider.init_args = (project_id, prefix)

        def get_secrets(self, keys):
            FakeProvider.seen_keys = keys
            return {
                SecretKey.DATABASE_URL: "postgresql://db",
                SecretKey.REVENUECAT_CLIENT_SECRET: "rc-secret",
                SecretKey.JWT_SECRET_KEY: "jwt-123",
                SecretKey.ENCRYPTION_KEY: "not-mapped",
            }

    monkeypatch.setattr(provider_module, "GCPSecretProvider", FakeProvider)

    source = GCPSecretManagerSource(Settings)
    settings_values = source()

    assert FakeProvider.init_args == ("project-1", "custom-prefix")
    assert SecretKey.DATABASE_URL in FakeProvider.seen_keys
    assert settings_values == {
        "database": {"url": "postgresql://db"},
        "oauth": {"revenuecat_client_secret": "rc-secret"},
        "jwt_secret_key": "jwt-123",
    }


def test_gcp_source_caches_loaded_secrets(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")

    class FakeProvider:
        calls = 0

        def __init__(self, project_id, prefix):
            return None

        def get_secrets(self, keys):
            FakeProvider.calls += 1
            return {SecretKey.JWT_SECRET_KEY: "jwt-123"}

    monkeypatch.setattr(provider_module, "GCPSecretProvider", FakeProvider)

    source = GCPSecretManagerSource(Settings)

    first = source()
    second = source()

    assert first == {"jwt_secret_key": "jwt-123"}
    assert second == {"jwt_secret_key": "jwt-123"}
    assert FakeProvider.calls == 1


def test_gcp_source_handles_import_error(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")

    class ImportErrorProvider:
        def __init__(self, project_id, prefix):
            raise ImportError("missing dependency")

    monkeypatch.setattr(provider_module, "GCPSecretProvider", ImportErrorProvider)

    source = GCPSecretManagerSource(Settings)

    assert source._load_secrets() == {}
    assert source() == {}


def test_gcp_source_handles_runtime_exception(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "project-1")

    class ErrorProvider:
        def __init__(self, project_id, prefix):
            return None

        def get_secrets(self, keys):
            raise RuntimeError("boom")

    monkeypatch.setattr(provider_module, "GCPSecretProvider", ErrorProvider)

    source = GCPSecretManagerSource(Settings)

    assert source._load_secrets() == {}
    assert source() == {}
