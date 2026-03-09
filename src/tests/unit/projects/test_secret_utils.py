from ii_agent.projects.secrets import utils as secret_utils


class FakeEncryptionManager:
    def __init__(self):
        self.last_encrypt = None
        self.last_decrypt = None

    def encrypt(self, value: str) -> str:
        self.last_encrypt = value
        return f"encrypted:{value}"

    def decrypt(self, value: str) -> str:
        self.last_decrypt = value
        return self._decrypted_payloads.get(value, "")


def test_encrypt_payload_wraps_json_for_encryption(monkeypatch):
    fake_manager = FakeEncryptionManager()
    monkeypatch.setattr(secret_utils, "encryption_manager", fake_manager)

    payload = {"A": "1", "B": 2}
    result = secret_utils._encrypt_secrets_payload(payload)

    assert result == {
        "encrypted_data": "encrypted:{\"A\": \"1\", \"B\": 2}"
    }
    assert fake_manager.last_encrypt == "{\"A\": \"1\", \"B\": 2}"


def test_decrypt_payload_returns_payload_when_not_encrypted():
    payload = {"foo": "bar"}
    assert secret_utils._decrypt_secrets_payload(payload) == payload


def test_decrypt_payload_returns_none_for_invalid_payload():
    assert secret_utils._decrypt_secrets_payload(None) is None


def test_decrypt_payload_returns_none_when_decryption_fails(monkeypatch):
    fake_manager = FakeEncryptionManager()
    fake_manager._decrypted_payloads = {}
    monkeypatch.setattr(secret_utils, "encryption_manager", fake_manager)

    assert secret_utils._decrypt_secrets_payload({"encrypted_data": "encrypted:bad"}) is None


def test_decrypt_payload_parses_decrypted_json(monkeypatch):
    fake_manager = FakeEncryptionManager()
    fake_manager._decrypted_payloads = {
        "encrypted:payload": "{\"A\": \"1\", \"B\": true}"
    }
    monkeypatch.setattr(secret_utils, "encryption_manager", fake_manager)

    assert secret_utils._decrypt_secrets_payload({"encrypted_data": "encrypted:payload"}) == {
        "A": "1",
        "B": True,
    }
