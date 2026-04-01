"""Unit tests for projects/schemas.py.

Tests SessionProjectResponse schema including field validation,
computed fields, and secret decryption.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from ii_agent.projects.schemas import SessionProjectResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_data(**overrides) -> dict:
    """Return a minimal valid dict for SessionProjectResponse."""
    base = {
        "id": "proj-123",
        "user_id": "user-456",
        "session_id": "sess-789",
        "name": "My Project",
        "description": "A test project",
        "status": "active",
        "current_build_status": "success",
        "framework": "nextjs",
        "project_path": "/workspaces/my-project",
        "production_url": "https://my-project.example.com",
        "database_json": None,
        "storage_json": None,
        "secrets_json": None,
        "current_production_deployment_id": "deploy-001",
        "created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


def _no_decrypt(v):
    """Identity function to mock secret decryption."""
    return v


# ---------------------------------------------------------------------------
# Basic field mapping
# ---------------------------------------------------------------------------


class TestSessionProjectResponseBasicFields:
    def test_id_field(self):
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data())
        assert schema.id == "proj-123"

    def test_user_id_field(self):
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data())
        assert schema.user_id == "user-456"

    def test_session_id_field(self):
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data())
        assert schema.session_id == "sess-789"

    def test_status_field(self):
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data())
        assert schema.status == "active"

    def test_current_build_status_field(self):
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data())
        assert schema.current_build_status == "success"

    def test_name_field(self):
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data())
        assert schema.name == "My Project"

    def test_created_at_field(self):
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data())
        assert schema.created_at is not None

    def test_optional_fields_can_be_none(self):
        data = _base_data(
            session_id=None,
            name=None,
            description=None,
            framework=None,
            project_path=None,
            production_url=None,
            current_production_deployment_id=None,
        )
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**data)
        assert schema.session_id is None
        assert schema.name is None
        assert schema.production_url is None


# ---------------------------------------------------------------------------
# Computed field: project_name
# ---------------------------------------------------------------------------


class TestSessionProjectResponseComputedField:
    def test_project_name_equals_name(self):
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data(name="Awesome App"))
        assert schema.project_name == "Awesome App"

    def test_project_name_none_when_name_none(self):
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data(name=None))
        assert schema.project_name is None


# ---------------------------------------------------------------------------
# Validation alias: database_json / storage_json / secrets_json
# ---------------------------------------------------------------------------


class TestSessionProjectResponseAliasFields:
    def test_database_populated_from_database_json(self):
        db_data = {"host": "localhost", "port": 5432}
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data(database_json=db_data))
        assert schema.database == db_data

    def test_storage_populated_from_storage_json(self):
        storage_data = {"bucket": "my-bucket"}
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data(storage_json=storage_data))
        assert schema.storage == storage_data

    def test_secrets_populated_from_secrets_json(self):
        secrets_data = {"API_KEY": "secret-value"}
        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse(**_base_data(secrets_json=secrets_data))
        # The secrets_data goes through decrypt_secrets first; since we mock identity:
        assert schema.secrets == secrets_data


# ---------------------------------------------------------------------------
# decrypt_secrets field_validator
# ---------------------------------------------------------------------------


class TestDecryptSecretsValidator:
    def test_decrypt_called_with_secrets_value(self):
        secrets_payload = {"DB_PASS": "encrypted_value"}

        with patch("ii_agent.projects.secrets.utils._decrypt_secrets_payload") as mock_decrypt:
            mock_decrypt.return_value = {"DB_PASS": "decrypted_value"}
            schema = SessionProjectResponse(**_base_data(secrets_json=secrets_payload))

        mock_decrypt.assert_called_once_with(secrets_payload)
        assert schema.secrets == {"DB_PASS": "decrypted_value"}

    def test_decrypt_called_with_none(self):
        with patch("ii_agent.projects.secrets.utils._decrypt_secrets_payload") as mock_decrypt:
            mock_decrypt.return_value = None
            schema = SessionProjectResponse(**_base_data(secrets_json=None))

        mock_decrypt.assert_called_once_with(None)
        assert schema.secrets is None


# ---------------------------------------------------------------------------
# from_attributes (ORM mode) mapping
# ---------------------------------------------------------------------------


class TestSessionProjectResponseFromAttributes:
    def test_from_orm_object(self):
        """Verify ConfigDict(from_attributes=True) works with an ORM-like object."""

        class FakeProject:
            id = "proj-orm"
            user_id = "user-orm"
            session_id = "sess-orm"
            name = "ORM Project"
            description = "From ORM"
            status = "active"
            current_build_status = "pending"
            framework = "react"
            project_path = "/path"
            production_url = None
            database_json = None
            storage_json = None
            secrets_json = None
            current_production_deployment_id = None
            created_at = datetime(2024, 3, 1, tzinfo=timezone.utc)
            updated_at = datetime(2024, 3, 2, tzinfo=timezone.utc)

        with patch(
            "ii_agent.projects.secrets.utils._decrypt_secrets_payload",
            side_effect=_no_decrypt,
        ):
            schema = SessionProjectResponse.model_validate(FakeProject())

        assert schema.id == "proj-orm"
        assert schema.name == "ORM Project"
        assert schema.project_name == "ORM Project"
