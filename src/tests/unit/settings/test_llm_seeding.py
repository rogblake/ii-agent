"""Unit tests for settings/llm/seeding.py.

Tests seed_admin_llm_settings and ensure_admin_llm_settings_seeded.

Strategy:
- Tests that need DB access mock the entire seed function.
- Tests that don't touch DB test pure logic (JSON parsing, early exits).
- ensure_admin_llm_settings_seeded wraps seed, so we mock seed there.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import ii_agent.settings.llm.seeding as seeding_module
from ii_agent.settings.llm.seeding import (
    ensure_admin_llm_settings_seeded,
    seed_admin_llm_settings,
)

# Import all related models to ensure SQLAlchemy mapper relationships are fully
# configured before any model is instantiated in tests.  The User model has
# forward-reference relationships to many other models; all must be imported
# before mapper.configure() is called.
import ii_agent.settings.mcp.models  # noqa: F401 -- MCPSetting
import ii_agent.settings.llm.models  # noqa: F401 -- LLMSetting
import ii_agent.files.models  # noqa: F401 -- FileUpload
import ii_agent.sessions.models  # noqa: F401 -- Session
import ii_agent.billing.models  # noqa: F401 -- BillingTransaction (if exists)
import ii_agent.users.models  # noqa: F401 -- User + APIKey etc


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_ctx_db():
    """
    Return (ctx_fn, db_mock) where ctx_fn() returns an async context manager
    that yields db_mock.  This mimics ``get_db_session_local()``.
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()

    @asynccontextmanager
    async def _inner():
        yield db

    def ctx():
        return _inner()

    return ctx, db


def _scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_result(values):
    scalars = MagicMock()
    scalars.all.return_value = values
    r = MagicMock()
    r.scalars.return_value = scalars
    return r


# ---------------------------------------------------------------------------
# Early-exit cases -- pure logic, no real DB
# ---------------------------------------------------------------------------


class TestSeedEarlyExit:
    """Tests where the function returns before touching the database."""

    async def test_no_llm_configs_json_returns_early(self):
        mock_settings = MagicMock()
        mock_settings.llm_configs_json = None

        with patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings):
            # Must not raise; must return without doing any DB work
            await seed_admin_llm_settings()

    async def test_empty_llm_configs_json_returns_early(self):
        mock_settings = MagicMock()
        mock_settings.llm_configs_json = ""

        with patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings):
            await seed_admin_llm_settings()

    async def test_invalid_json_returns_early(self):
        mock_settings = MagicMock()
        mock_settings.llm_configs_json = "not-valid-json"

        with patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings):
            # Should log error and return, not raise
            await seed_admin_llm_settings()


# ---------------------------------------------------------------------------
# With valid JSON -- mock full DB interaction
# ---------------------------------------------------------------------------


class TestSeedWithExistingAdmin:
    """When admin user already exists (admin found in DB), no create path is taken."""

    async def test_existing_admin_and_settings_commits(self):
        mock_settings = MagicMock()
        configs = {
            "model-1": {
                "model": "claude-3-5-sonnet-20241022",
                "api_type": "anthropic",
                "api_key": None,
                "base_url": None,
                "max_retries": 5,
                "max_message_chars": 20000,
                "temperature": 0.5,
            }
        }
        mock_settings.llm_configs_json = json.dumps(configs)

        ctx, db = _make_ctx_db()

        # Admin user found, has existing settings
        mock_admin_user = MagicMock()
        mock_admin_user.id = "admin"
        mock_existing_setting = MagicMock()
        mock_existing_setting.id = "model-1"

        db.execute = AsyncMock(
            side_effect=[
                _scalar_result(mock_admin_user),  # admin user found
                _scalars_result([mock_existing_setting]),  # existing LLM setting
            ]
        )

        with (
            patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings),
            patch("ii_agent.core.db.manager.get_db_session_local", new=ctx),
        ):
            await seed_admin_llm_settings()

        db.commit.assert_called_once()

    async def test_existing_admin_no_settings_count_logged(self):
        """Admin exists and has one existing setting (update path, no new ORM objects created)."""
        mock_settings = MagicMock()
        # Config matches an existing setting -- update path, no LLMSetting() constructor called
        configs = {
            "existing-model": {
                "model": "gpt-4o-mini",
                "api_type": "openai",
                "api_key": None,
                "base_url": None,
                "max_retries": 3,
                "max_message_chars": 10000,
                "temperature": 0.0,
            }
        }
        mock_settings.llm_configs_json = json.dumps(configs)

        ctx, db = _make_ctx_db()

        mock_admin_user = MagicMock()
        mock_admin_user.id = "admin"

        # Existing setting with the same ID as in configs, so update path is taken
        mock_existing_setting = MagicMock()
        mock_existing_setting.id = "existing-model"

        db.execute = AsyncMock(
            side_effect=[
                _scalar_result(mock_admin_user),  # admin found
                _scalars_result([mock_existing_setting]),  # one existing setting
            ]
        )

        with (
            patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings),
            patch("ii_agent.core.db.manager.get_db_session_local", new=ctx),
        ):
            await seed_admin_llm_settings()

        db.commit.assert_called_once()
        # Update path: db.add should NOT be called (existing setting is updated in-place)
        db.add.assert_not_called()

    async def test_exception_propagates_on_db_error(self):
        """If an error occurs inside the DB block, rollback handled by get_db_session_local."""
        mock_settings = MagicMock()
        mock_settings.llm_configs_json = json.dumps(
            {"m": {"model": "x", "api_type": "openai", "api_key": None}}
        )

        ctx, db = _make_ctx_db()
        db.execute = AsyncMock(side_effect=RuntimeError("DB error"))

        with (
            patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings),
            patch("ii_agent.core.db.manager.get_db_session_local", new=ctx),
        ):
            with pytest.raises(RuntimeError, match="DB error"):
                await seed_admin_llm_settings()

    async def test_api_key_encrypted_when_provided(self):
        """When config has an api_key, the encryption manager is called.

        Uses an existing setting (update path) to avoid LLMSetting() constructor.
        """
        mock_settings = MagicMock()
        configs = {
            "keyed-model": {
                "model": "gpt-4o",
                "api_type": "openai",
                "api_key": "sk-real-key",
            }
        }
        mock_settings.llm_configs_json = json.dumps(configs)

        ctx, db = _make_ctx_db()

        mock_admin_user = MagicMock()
        mock_admin_user.id = "admin"

        # Return an existing setting that matches the model ID so the update
        # path is taken (avoids calling LLMSetting() constructor)
        mock_existing_setting = MagicMock()
        mock_existing_setting.id = "keyed-model"

        db.execute = AsyncMock(
            side_effect=[
                _scalar_result(mock_admin_user),
                _scalars_result([mock_existing_setting]),
            ]
        )

        mock_enc = MagicMock()
        mock_enc.encrypt.return_value = "enc_sk"

        with (
            patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings),
            patch("ii_agent.core.db.manager.get_db_session_local", new=ctx),
            patch("ii_agent.core.secrets.encryption.encryption_manager", mock_enc),
        ):
            await seed_admin_llm_settings()

        mock_enc.encrypt.assert_called_once_with("sk-real-key")


# ---------------------------------------------------------------------------
# ensure_admin_llm_settings_seeded
# ---------------------------------------------------------------------------


class TestEnsureAdminLLMSettingsSeeded:
    """Tests for the once-only guard wrapper."""

    async def test_runs_seed_on_first_call(self):
        seeding_module._seeding_done = False

        with patch(
            "ii_agent.settings.llm.seeding.seed_admin_llm_settings",
            new_callable=AsyncMock,
        ) as mock_seed:
            await ensure_admin_llm_settings_seeded()
            mock_seed.assert_called_once()

        assert seeding_module._seeding_done is True

    async def test_skips_seed_when_already_done(self):
        seeding_module._seeding_done = True

        with patch(
            "ii_agent.settings.llm.seeding.seed_admin_llm_settings",
            new_callable=AsyncMock,
        ) as mock_seed:
            await ensure_admin_llm_settings_seeded()
            mock_seed.assert_not_called()

        seeding_module._seeding_done = False  # cleanup

    async def test_error_in_seed_does_not_set_done_flag(self):
        seeding_module._seeding_done = False

        with patch(
            "ii_agent.settings.llm.seeding.seed_admin_llm_settings",
            new_callable=AsyncMock,
            side_effect=Exception("seed error"),
        ):
            # Should NOT propagate; errors are caught and logged
            await ensure_admin_llm_settings_seeded()

        assert seeding_module._seeding_done is False

    async def test_done_flag_set_after_successful_seed(self):
        seeding_module._seeding_done = False

        with patch(
            "ii_agent.settings.llm.seeding.seed_admin_llm_settings",
            new_callable=AsyncMock,
        ):
            await ensure_admin_llm_settings_seeded()

        assert seeding_module._seeding_done is True
        seeding_module._seeding_done = False  # cleanup

    async def test_seed_idempotent_multiple_calls(self):
        """Calling ensure multiple times should only run seed once."""
        seeding_module._seeding_done = False

        with patch(
            "ii_agent.settings.llm.seeding.seed_admin_llm_settings",
            new_callable=AsyncMock,
        ) as mock_seed:
            await ensure_admin_llm_settings_seeded()
            await ensure_admin_llm_settings_seeded()
            await ensure_admin_llm_settings_seeded()
            mock_seed.assert_called_once()

        seeding_module._seeding_done = False  # cleanup
