"""Custom SQLAlchemy column types."""

from __future__ import annotations

from sqlalchemy import String, TypeDecorator


class EncryptedString(TypeDecorator):
    """Column type that will encrypt/decrypt values transparently.

    Currently a pass-through — encryption implementation will be added
    when the key management service is integrated.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:  # noqa: ANN001
        # TODO: encrypt value before storing
        return value

    def process_result_value(self, value: str | None, dialect) -> str | None:  # noqa: ANN001
        # TODO: decrypt value after loading
        return value
