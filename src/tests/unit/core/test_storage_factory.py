import pytest

from ii_agent.core.storage import factory


def test_create_storage_client_returns_gcs(monkeypatch):
    class FakeGCS:
        def __init__(self, project_id, bucket_name, custom_domain):
            self.project_id = project_id
            self.bucket_name = bucket_name
            self.custom_domain = custom_domain

    monkeypatch.setattr(factory, "GCS", FakeGCS)

    client = factory.create_storage_client(
        "gcs", "project", "bucket", custom_domain="cdn.local"
    )

    assert isinstance(client, FakeGCS)
    assert client.project_id == "project"
    assert client.bucket_name == "bucket"
    assert client.custom_domain == "cdn.local"


def test_create_storage_client_raises_for_unknown_provider():
    with pytest.raises(ValueError, match="not supported"):
        factory.create_storage_client("unknown", "p", "b")
