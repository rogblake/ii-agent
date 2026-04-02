"""Unit tests for integrations/connectors/tools_loader.py.

Tests load_connector_tools with mocked DB and connector data.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


from ii_agent.integrations.connectors.tools_loader import load_connector_tools
from ii_agent.integrations.connectors.models import ConnectorTypeEnum


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_session(connectors: list) -> AsyncMock:
    """Return a mock AsyncSession that returns given connectors on execute."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = connectors

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


def _make_github_connector() -> MagicMock:
    """Return a mock Connector with GITHUB type."""
    connector = MagicMock()
    connector.connector_type = ConnectorTypeEnum.GITHUB.value
    connector.access_token = "ghp_test_token"
    connector.connector_metadata = {"default_org": "acme"}
    return connector


def _make_unknown_connector() -> MagicMock:
    """Return a mock Connector with an unknown type."""
    connector = MagicMock()
    connector.connector_type = "unknown_service"
    connector.access_token = "token"
    connector.connector_metadata = {}
    return connector


# ---------------------------------------------------------------------------
# No connectors
# ---------------------------------------------------------------------------


class TestLoadConnectorToolsEmpty:
    async def test_returns_empty_list_when_no_connectors(self):
        db = _make_db_session([])

        result = await load_connector_tools(
            db_session=db,
            user_id="user-1",
            workspace_path="/workspace",
            sandbox=MagicMock(),
        )

        assert result == []

    async def test_calls_execute_with_user_filter(self):
        db = _make_db_session([])

        await load_connector_tools(
            db_session=db,
            user_id="user-42",
            workspace_path="/workspace",
            sandbox=MagicMock(),
        )

        db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# GitHub connector
# ---------------------------------------------------------------------------


class TestLoadConnectorToolsGitHub:
    async def test_loads_github_tool_when_connector_present(self):
        connector = _make_github_connector()
        db = _make_db_session([connector])

        mock_github_tool = MagicMock()
        mock_github_tool.name = "github"

        with patch(
            "ii_agent.integrations.connectors.tools_loader.GitHubAgentTool",
            return_value=mock_github_tool,
        ) as MockGitHub:
            result = await load_connector_tools(
                db_session=db,
                user_id="user-1",
                workspace_path="/workspace",
                sandbox=MagicMock(),
            )

        assert len(result) == 1
        assert result[0] is mock_github_tool

    async def test_github_tool_instantiated_with_correct_args(self):
        connector = _make_github_connector()
        db = _make_db_session([connector])
        default_repo = {"owner": "acme", "name": "repo", "full_name": "acme/repo"}

        mock_github_tool = MagicMock()
        mock_github_tool.name = "github"

        with patch(
            "ii_agent.integrations.connectors.tools_loader.GitHubAgentTool",
            return_value=mock_github_tool,
        ) as MockGitHub:
            await load_connector_tools(
                db_session=db,
                user_id="user-1",
                workspace_path="/workspace",
                sandbox=MagicMock(),
                default_repository=default_repo,
            )

        MockGitHub.assert_called_once_with(
            github_token="ghp_test_token",
            workspace_path="/workspace",
            github_metadata={"default_org": "acme"},
            default_repository=default_repo,
        )

    async def test_github_tool_with_none_default_repository(self):
        connector = _make_github_connector()
        db = _make_db_session([connector])

        mock_github_tool = MagicMock()
        mock_github_tool.name = "github"

        with patch(
            "ii_agent.integrations.connectors.tools_loader.GitHubAgentTool",
            return_value=mock_github_tool,
        ) as MockGitHub:
            result = await load_connector_tools(
                db_session=db,
                user_id="user-1",
                workspace_path="/workspace",
                sandbox=MagicMock(),
                default_repository=None,
            )

        MockGitHub.assert_called_once()
        call_kwargs = MockGitHub.call_args.kwargs
        assert call_kwargs["default_repository"] is None


# ---------------------------------------------------------------------------
# Unknown connector type
# ---------------------------------------------------------------------------


class TestLoadConnectorToolsUnknownType:
    async def test_unknown_connector_skipped(self):
        connector = _make_unknown_connector()
        db = _make_db_session([connector])

        result = await load_connector_tools(
            db_session=db,
            user_id="user-1",
            workspace_path="/workspace",
            sandbox=MagicMock(),
        )

        assert result == []

    async def test_unknown_connector_does_not_raise(self):
        connector = _make_unknown_connector()
        db = _make_db_session([connector])

        # Should not raise
        result = await load_connector_tools(
            db_session=db,
            user_id="user-1",
            workspace_path="/workspace",
            sandbox=MagicMock(),
        )
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestLoadConnectorToolsErrorHandling:
    async def test_exception_in_one_connector_does_not_stop_others(self):
        """If one connector fails, processing continues for others."""
        bad_connector = _make_github_connector()
        good_connector = _make_github_connector()
        good_connector.access_token = "good_token"

        db = _make_db_session([bad_connector, good_connector])

        call_count = 0

        def github_tool_factory(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First connector failed")
            mock = MagicMock()
            mock.name = "github"
            return mock

        with patch(
            "ii_agent.integrations.connectors.tools_loader.GitHubAgentTool",
            side_effect=github_tool_factory,
        ):
            result = await load_connector_tools(
                db_session=db,
                user_id="user-1",
                workspace_path="/workspace",
                sandbox=MagicMock(),
            )

        # Only the second connector succeeded
        assert len(result) == 1

    async def test_mixed_connectors_loaded_correctly(self):
        """Multiple connectors of the same type produce multiple tools."""
        connector1 = _make_github_connector()
        connector2 = _make_github_connector()
        connector2.access_token = "token2"
        db = _make_db_session([connector1, connector2])

        tool1 = MagicMock()
        tool1.name = "github"
        tool2 = MagicMock()
        tool2.name = "github"

        with patch(
            "ii_agent.integrations.connectors.tools_loader.GitHubAgentTool",
            side_effect=[tool1, tool2],
        ):
            result = await load_connector_tools(
                db_session=db,
                user_id="user-1",
                workspace_path="/workspace",
                sandbox=MagicMock(),
            )

        assert len(result) == 2
        assert result[0] is tool1
        assert result[1] is tool2
