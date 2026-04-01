"""Utility functions for auth domain."""

import secrets
import string

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def generate_api_key(length: int = 32) -> str:
    """Generate a secure random API key."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_prefixed_api_key(prefix: str = "ii", length: int = 32) -> str:
    """Generate a prefixed API key (e.g. ``ii_abc123...``)."""
    remaining_length = max(8, length - len(prefix) - 1)
    random_part = generate_api_key(remaining_length)
    return f"{prefix}_{random_part}"
