from cryptography.fernet import Fernet

from ii_agent.core.secrets.encryption import EncryptionManager


def test_encrypt_decrypt_roundtrip():
    manager = EncryptionManager(Fernet.generate_key().decode())

    encrypted = manager.encrypt("secret-value")

    assert encrypted
    assert manager.decrypt(encrypted) == "secret-value"


def test_encrypt_raw_decrypt_raw_roundtrip():
    manager = EncryptionManager(Fernet.generate_key().decode())

    encrypted_raw = manager.encrypt_raw("raw-secret")

    assert encrypted_raw.startswith("gAAAA")
    assert manager.decrypt_raw(encrypted_raw) == "raw-secret"


def test_decrypt_invalid_ciphertext_returns_empty_string():
    manager = EncryptionManager(Fernet.generate_key().decode())

    assert manager.decrypt("not-valid-base64") == ""
    assert manager.decrypt_raw("not-a-fernet-token") == ""


def test_is_encrypted_heuristic_detects_raw_tokens():
    manager = EncryptionManager(Fernet.generate_key().decode())

    token = manager.encrypt_raw("value")

    assert manager.is_encrypted(token) is True
    assert manager.is_encrypted("plain-text") is False
