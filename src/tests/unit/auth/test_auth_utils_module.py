import importlib
import sys
import types


def _import_auth_utils_with_fake_passlib(monkeypatch):
    fake_passlib = types.ModuleType("passlib")
    fake_context_module = types.ModuleType("passlib.context")

    class FakeCryptContext:
        def __init__(self, *args, **kwargs):
            return None

        def verify(self, plain_password, hashed_password):
            return hashed_password == f"hashed::{plain_password}"

        def hash(self, password):
            return f"hashed::{password}"

    fake_context_module.CryptContext = FakeCryptContext

    monkeypatch.setitem(sys.modules, "passlib", fake_passlib)
    monkeypatch.setitem(sys.modules, "passlib.context", fake_context_module)
    sys.modules.pop("ii_agent.auth.utils", None)
    return importlib.import_module("ii_agent.auth.utils")


def test_password_hash_and_verify_round_trip(monkeypatch):
    auth_utils = _import_auth_utils_with_fake_passlib(monkeypatch)

    plain_password = "test-password-123"
    hashed_password = auth_utils.get_password_hash(plain_password)

    assert hashed_password == "hashed::test-password-123"
    assert auth_utils.verify_password(plain_password, hashed_password) is True
    assert auth_utils.verify_password("wrong-password", hashed_password) is False
