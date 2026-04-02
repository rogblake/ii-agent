from ii_agent.auth import api_key_utils


def test_generate_api_key_length_and_charset(monkeypatch):
    monkeypatch.setattr(api_key_utils.secrets, "choice", lambda alphabet: "A")

    key = api_key_utils.generate_api_key(length=16)

    assert key == "A" * 16


def test_generate_prefixed_api_key_uses_prefix_and_minimum_length(monkeypatch):
    monkeypatch.setattr(api_key_utils, "generate_api_key", lambda length: "x" * length)

    key = api_key_utils.generate_prefixed_api_key(prefix="ii", length=10)

    assert key.startswith("ii_")
    assert len(key.split("_", 1)[1]) >= 8
