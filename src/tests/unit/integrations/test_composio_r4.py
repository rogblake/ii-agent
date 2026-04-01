"""Unit tests for composio toolkit, cache service, and router (r4)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# composio/cache_service.py - ComposioCacheService
# ===========================================================================


class TestComposioCacheServiceGetAllToolkits:
    @pytest.mark.asyncio
    async def test_returns_none_when_cache_miss(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=None),
        ):
            result = await ComposioCacheService.get_all_toolkits()
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_on_cache_hit(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        cached_data = {"toolkits": [], "success": True}
        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=cached_data),
        ):
            result = await ComposioCacheService.get_all_toolkits()
            assert result == cached_data

    @pytest.mark.asyncio
    async def test_parses_json_string_from_cache(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        data = {"toolkits": [{"slug": "gmail"}], "success": True}
        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=json.dumps(data)),
        ):
            result = await ComposioCacheService.get_all_toolkits()
            assert result == data

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(side_effect=Exception("redis error")),
        ):
            result = await ComposioCacheService.get_all_toolkits()
            assert result is None


class TestComposioCacheServiceSetAllToolkits:
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.set",
            AsyncMock(return_value=True),
        ):
            result = await ComposioCacheService.set_all_toolkits({"toolkits": []})
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.set",
            AsyncMock(side_effect=Exception("redis error")),
        ):
            result = await ComposioCacheService.set_all_toolkits({"toolkits": []})
            assert result is False


class TestComposioCacheServiceGetToolkitDetails:
    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=None),
        ):
            result = await ComposioCacheService.get_toolkit_details("gmail")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_on_cache_hit(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        toolkit_data = {"slug": "gmail", "name": "Gmail"}
        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=toolkit_data),
        ):
            result = await ComposioCacheService.get_toolkit_details("gmail")
            assert result == toolkit_data


class TestComposioCacheServiceSetToolkitDetails:
    @pytest.mark.asyncio
    async def test_stores_with_correct_key(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        mock_set = AsyncMock(return_value=True)
        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.set",
            mock_set,
        ):
            await ComposioCacheService.set_toolkit_details("gmail", {"slug": "gmail"})
            args, kwargs = mock_set.call_args
            assert "composio:toolkit:gmail" in args or "composio:toolkit:gmail" == kwargs.get(
                "key", args[0] if args else ""
            )


class TestComposioCacheServiceGetToolkitActions:
    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=None),
        ):
            result = await ComposioCacheService.get_toolkit_actions("gmail")
            assert result is None


class TestComposioCacheServiceSetToolkitActions:
    @pytest.mark.asyncio
    async def test_stores_actions_with_categories(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        mock_set = AsyncMock(return_value=True)
        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.set",
            mock_set,
        ):
            result = await ComposioCacheService.set_toolkit_actions(
                "gmail", [{"name": "GMAIL_SEND_EMAIL"}], categories=["email"]
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_handles_none_categories(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        mock_set = AsyncMock(return_value=True)
        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.set",
            mock_set,
        ):
            result = await ComposioCacheService.set_toolkit_actions(
                "gmail", [{"name": "GMAIL_SEND_EMAIL"}], categories=None
            )
            # categories=None should default to []
            _, kwargs = mock_set.call_args
            call_data = mock_set.call_args[0][1]
            assert call_data["categories"] == []


class TestComposioCacheServiceGetToolkitIcon:
    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=None),
        ):
            result = await ComposioCacheService.get_toolkit_icon("gmail")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_icon_url_from_cache(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        cached_data = {"icon_url": "https://example.com/gmail.png"}
        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=cached_data),
        ):
            result = await ComposioCacheService.get_toolkit_icon("gmail")
            assert result == "https://example.com/gmail.png"


class TestComposioCacheServiceSetToolkitIcon:
    @pytest.mark.asyncio
    async def test_stores_icon_url(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        mock_set = AsyncMock(return_value=True)
        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.set",
            mock_set,
        ):
            result = await ComposioCacheService.set_toolkit_icon(
                "gmail", "https://example.com/gmail.png"
            )
            assert result is True


class TestComposioCacheServiceGetCategories:
    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=None),
        ):
            result = await ComposioCacheService.get_categories()
            assert result is None


class TestComposioCacheServiceInvalidateToolkit:
    @pytest.mark.asyncio
    async def test_evicts_multiple_keys(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        evicted_keys = []

        async def mock_evict(key):
            evicted_keys.append(key)

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.evict",
            side_effect=mock_evict,
        ):
            result = await ComposioCacheService.invalidate_toolkit("gmail")
            assert result is True
            # Should have evicted toolkit key, actions key, icon key, and all toolkits
            assert any("gmail" in k for k in evicted_keys)

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.evict",
            side_effect=Exception("redis error"),
        ):
            result = await ComposioCacheService.invalidate_toolkit("gmail")
            assert result is False


class TestComposioCacheServiceInvalidateAll:
    @pytest.mark.asyncio
    async def test_evicts_all_toolkits_and_categories(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        evicted_keys = []

        async def mock_evict(key):
            evicted_keys.append(key)

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.evict",
            side_effect=mock_evict,
        ):
            result = await ComposioCacheService.invalidate_all()
            assert result is True
            assert "composio:toolkits:all" in evicted_keys
            assert "composio:categories:all" in evicted_keys


class TestComposioCacheServiceGetActionDisplayName:
    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=None),
        ):
            result = await ComposioCacheService.get_action_display_name("GMAIL_SEND_EMAIL")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_display_name_from_cache(self):
        from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService

        cached_data = {"display_name": "Send Email"}
        with patch(
            "ii_agent.integrations.connectors.composio.cache_service.entity_cache.get",
            AsyncMock(return_value=cached_data),
        ):
            result = await ComposioCacheService.get_action_display_name("GMAIL_SEND_EMAIL")
            assert result == "Send Email"


# ===========================================================================
# composio/toolkit_service.py - ToolkitService helpers
# ===========================================================================


class TestToDict:
    def test_dict_returned_as_is(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import _to_dict

        d = {"key": "value"}
        assert _to_dict(d) is d

    def test_pydantic_model_converted(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import _to_dict
        from pydantic import BaseModel

        class TestModel(BaseModel):
            key: str = "value"

        result = _to_dict(TestModel())
        assert result == {"key": "value"}

    def test_object_with_dict_attr(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import _to_dict

        class Obj:
            def __init__(self):
                self.__dict__ = {"a": 1}

        result = _to_dict(Obj())
        assert result.get("a") == 1

    def test_non_dict_non_model_returns_empty(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import _to_dict

        result = _to_dict("not_a_dict")
        assert result == {}


class TestGetAttr:
    def test_gets_from_dict(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import _get_attr

        assert _get_attr({"key": "value"}, "key") == "value"

    def test_default_when_missing(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import _get_attr

        assert _get_attr({}, "key", "default") == "default"

    def test_gets_from_object(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import _get_attr

        obj = MagicMock()
        obj.key = "obj_value"
        assert _get_attr(obj, "key") == "obj_value"


class TestRequiresSandbox:
    def test_googledrive_requires_sandbox(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        assert ToolkitService.requires_sandbox("googledrive") is True
        assert ToolkitService.requires_sandbox("GOOGLEDRIVE") is True

    def test_gmail_does_not_require_sandbox(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        assert ToolkitService.requires_sandbox("gmail") is False

    def test_unknown_toolkit_does_not_require_sandbox(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        assert ToolkitService.requires_sandbox("unknown_toolkit") is False


class TestToolRequiresSandbox:
    def test_calls_toolkit_service(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import tool_requires_sandbox

        assert tool_requires_sandbox("googledrive") is True
        assert tool_requires_sandbox("github") is False


class TestSlugifyToDisplayName:
    def test_known_slug_returns_mapped_name(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        mock_client = MagicMock()
        svc = ToolkitService.__new__(ToolkitService)
        svc.client = mock_client

        assert svc._slugify_to_display_name("gmail") == "Gmail"
        assert svc._slugify_to_display_name("github") == "GitHub"

    def test_unknown_slug_with_underscore_capitalized(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        mock_client = MagicMock()
        svc = ToolkitService.__new__(ToolkitService)
        svc.client = mock_client

        result = svc._slugify_to_display_name("some_tool_name")
        # Should be capitalized words
        assert "Some" in result

    def test_removes_tool_suffix(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        mock_client = MagicMock()
        svc = ToolkitService.__new__(ToolkitService)
        svc.client = mock_client

        result = svc._slugify_to_display_name("browser_tool")
        assert "_tool" not in result


class TestExtractToolkitInfo:
    def _make_service(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        svc = ToolkitService.__new__(ToolkitService)
        svc.client = MagicMock()
        return svc

    def test_returns_none_for_no_auth_apps(self):
        svc = self._make_service()
        item = {"no_auth": True, "key": "some_app", "name": "Some App"}
        result = svc._extract_toolkit_info(item)
        assert result is None

    def test_returns_none_for_apps_not_in_display_name_map(self):
        svc = self._make_service()
        item = {"no_auth": False, "key": "unknown_app", "name": "Unknown App", "meta": {}}
        result = svc._extract_toolkit_info(item)
        assert result is None

    def test_returns_toolkit_info_for_known_app(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitInfo

        svc = self._make_service()
        item = {
            "no_auth": False,
            "key": "gmail",
            "name": "Gmail",
            "meta": {},
            "auth_schemes": ["OAUTH2"],
        }
        result = svc._extract_toolkit_info(item)
        assert result is not None
        assert isinstance(result, ToolkitInfo)
        assert result.slug == "gmail"


class TestListToolkits:
    @pytest.mark.asyncio
    async def test_returns_cached_result_when_available(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        cached = {"success": True, "toolkits": [], "categories": []}

        with patch(
            "ii_agent.integrations.connectors.composio.toolkit_service.ComposioCacheService.get_all_toolkits",
            AsyncMock(return_value=cached),
        ):
            svc = ToolkitService.__new__(ToolkitService)
            svc.client = MagicMock()
            result = await svc.list_toolkits()
            assert result == cached

    @pytest.mark.asyncio
    async def test_fetches_from_client_when_no_cache(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        mock_toolkits_client = MagicMock()
        mock_toolkits_client.get.return_value = []

        mock_client = MagicMock()
        mock_client.toolkits = mock_toolkits_client

        with (
            patch(
                "ii_agent.integrations.connectors.composio.toolkit_service.ComposioCacheService.get_all_toolkits",
                AsyncMock(return_value=None),
            ),
            patch(
                "ii_agent.integrations.connectors.composio.toolkit_service.ComposioCacheService.set_all_toolkits",
                AsyncMock(return_value=True),
            ),
        ):
            svc = ToolkitService.__new__(ToolkitService)
            svc.client = mock_client
            result = await svc.list_toolkits()
            assert result["success"] is True
            assert "toolkits" in result


class TestSearchToolkits:
    @pytest.mark.asyncio
    async def test_filters_by_query_string(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        toolkits = [
            {"slug": "gmail", "name": "Gmail", "description": "Email tool", "categories_info": []},
            {"slug": "slack", "name": "Slack", "description": "Messaging", "categories_info": []},
        ]
        mock_response = {"success": True, "toolkits": toolkits}

        svc = ToolkitService.__new__(ToolkitService)
        svc.client = MagicMock()

        with patch.object(svc, "list_toolkits", AsyncMock(return_value=mock_response)):
            result = await svc.search_toolkits("gmail")

        assert result["success"] is True
        assert len(result["toolkits"]) == 1
        assert result["toolkits"][0]["slug"] == "gmail"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_match(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        toolkits = [
            {"slug": "slack", "name": "Slack", "description": "Messaging", "categories_info": []}
        ]
        mock_response = {"success": True, "toolkits": toolkits}

        svc = ToolkitService.__new__(ToolkitService)
        svc.client = MagicMock()

        with patch.object(svc, "list_toolkits", AsyncMock(return_value=mock_response)):
            result = await svc.search_toolkits("github")

        assert result["total_items"] == 0

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        toolkits = [
            {"slug": f"app{i}", "name": f"App{i}", "description": "test app", "categories_info": []}
            for i in range(10)
        ]
        mock_response = {"success": True, "toolkits": toolkits}

        svc = ToolkitService.__new__(ToolkitService)
        svc.client = MagicMock()

        with patch.object(svc, "list_toolkits", AsyncMock(return_value=mock_response)):
            result = await svc.search_toolkits("app", limit=3)

        assert len(result["toolkits"]) <= 3


class TestMatchesSearch:
    def _make_service(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        svc = ToolkitService.__new__(ToolkitService)
        svc.client = MagicMock()
        return svc

    def test_matches_name(self):
        svc = self._make_service()
        toolkit = {"name": "Gmail", "description": None, "categories_info": []}
        assert svc._matches_search(toolkit, "gmail") is True

    def test_matches_description(self):
        svc = self._make_service()
        toolkit = {"name": "App", "description": "Email and calendar app", "categories_info": []}
        assert svc._matches_search(toolkit, "email") is True

    def test_matches_category(self):
        svc = self._make_service()
        toolkit = {
            "name": "App",
            "description": None,
            "categories_info": [{"name": "productivity"}],
        }
        assert svc._matches_search(toolkit, "productivity") is True

    def test_no_match_returns_false(self):
        svc = self._make_service()
        toolkit = {"name": "Slack", "description": "Messaging", "categories_info": []}
        assert svc._matches_search(toolkit, "github") is False

    def test_case_insensitive(self):
        svc = self._make_service()
        toolkit = {"name": "Gmail", "description": None, "categories_info": []}
        assert svc._matches_search(toolkit, "GMAIL") is True


class TestParseAuthConfigField:
    def _make_service(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        svc = ToolkitService.__new__(ToolkitService)
        svc.client = MagicMock()
        return svc

    def test_parses_field_from_dict(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import AuthConfigField

        svc = self._make_service()

        field_data = {
            "name": "api_key",
            "display_name": "API Key",
            "type": "string",
            "required": True,
        }
        result = svc._parse_auth_config_field(field_data)
        assert isinstance(result, AuthConfigField)
        assert result.name == "api_key"
        assert result.required is True


class TestGetToolkitBySlug:
    @pytest.mark.asyncio
    async def test_returns_toolkit_when_found(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        toolkits = [{"slug": "gmail"}, {"slug": "slack"}]

        svc = ToolkitService.__new__(ToolkitService)
        svc.client = MagicMock()

        with patch.object(svc, "list_toolkits", AsyncMock(return_value={"toolkits": toolkits})):
            result = await svc.get_toolkit_by_slug("gmail")
            assert result is not None
            assert result["slug"] == "gmail"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService

        svc = ToolkitService.__new__(ToolkitService)
        svc.client = MagicMock()

        with patch.object(svc, "list_toolkits", AsyncMock(return_value={"toolkits": []})):
            result = await svc.get_toolkit_by_slug("nonexistent")
            assert result is None


# ===========================================================================
# connectors/router.py - Helper functions
# ===========================================================================


class TestCreateStateToken:
    def test_creates_token_with_user_id(self):
        import sys
        from ii_agent.integrations.connectors.router import _create_state_token

        router_module = sys.modules["ii_agent.integrations.connectors.router"]
        mock_settings = MagicMock()
        mock_settings.oauth.session_secret_key = "test-secret-key"

        with patch.object(router_module, "get_settings", return_value=mock_settings):
            token = _create_state_token("user-1", "github")
            assert isinstance(token, str)
            assert len(token) > 0

    def test_token_includes_frontend_url(self):
        import sys
        from ii_agent.integrations.connectors.router import _create_state_token
        from itsdangerous import URLSafeSerializer

        router_module = sys.modules["ii_agent.integrations.connectors.router"]
        secret_key = "test-secret-key"
        mock_settings = MagicMock()
        mock_settings.oauth.session_secret_key = secret_key

        with patch.object(router_module, "get_settings", return_value=mock_settings):
            token = _create_state_token("user-1", "github", frontend_url="https://app.com")

        serializer = URLSafeSerializer(secret_key)
        data = serializer.loads(token)
        assert data.get("frontend_url") == "https://app.com"


class TestVerifyStateToken:
    def test_verifies_valid_token(self):
        import sys
        from ii_agent.integrations.connectors.router import _create_state_token, _verify_state_token

        router_module = sys.modules["ii_agent.integrations.connectors.router"]
        secret_key = "test-secret-key"
        mock_settings = MagicMock()
        mock_settings.oauth.session_secret_key = secret_key

        with patch.object(router_module, "get_settings", return_value=mock_settings):
            token = _create_state_token("user-1", "github")
            data = _verify_state_token(token, "user-1")
            assert data["user_id"] == "user-1"

    def test_raises_on_wrong_user_id(self):
        import sys
        from ii_agent.integrations.connectors.router import _create_state_token, _verify_state_token
        from ii_agent.integrations.connectors.exceptions import ConnectorStateError

        router_module = sys.modules["ii_agent.integrations.connectors.router"]
        secret_key = "test-secret-key"
        mock_settings = MagicMock()
        mock_settings.oauth.session_secret_key = secret_key

        with patch.object(router_module, "get_settings", return_value=mock_settings):
            token = _create_state_token("user-1", "github")
            with pytest.raises(ConnectorStateError):
                _verify_state_token(token, "wrong-user")

    def test_raises_on_invalid_token(self):
        import sys
        from ii_agent.integrations.connectors.router import _verify_state_token
        from ii_agent.integrations.connectors.exceptions import ConnectorStateError

        router_module = sys.modules["ii_agent.integrations.connectors.router"]
        mock_settings = MagicMock()
        mock_settings.oauth.session_secret_key = "test-secret-key"

        with patch.object(router_module, "get_settings", return_value=mock_settings):
            with pytest.raises(ConnectorStateError):
                _verify_state_token("invalid.token.here", "user-1")


# ===========================================================================
# composio/router.py - HTTP endpoint logic
# ===========================================================================


class TestComposioRouterListToolkits:
    @pytest.mark.asyncio
    async def test_delegates_to_service(self):
        from ii_agent.integrations.connectors.composio.router import list_composio_toolkits

        mock_svc = MagicMock()
        mock_svc.list_toolkits = AsyncMock(return_value={"toolkits": []})
        mock_user = MagicMock()

        result = await list_composio_toolkits(
            current_user=mock_user,
            svc=mock_svc,
            search=None,
            category=None,
            limit=100,
        )
        mock_svc.list_toolkits.assert_called_once_with(search=None, category=None, limit=100)


class TestComposioRouterListProfiles:
    @pytest.mark.asyncio
    async def test_returns_profiles_list(self):
        from ii_agent.integrations.connectors.composio.router import list_composio_profiles

        mock_profile = MagicMock()
        mock_profile.model_dump.return_value = {"id": "p1"}

        mock_svc = MagicMock()
        mock_svc.get_profiles = AsyncMock(return_value=[mock_profile])

        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_db = MagicMock()

        result = await list_composio_profiles(
            current_user=mock_user,
            db=mock_db,
            svc=mock_svc,
            toolkit_slug=None,
        )
        assert "profiles" in result
        assert len(result["profiles"]) == 1


class TestComposioRouterCompleteOAuth:
    @pytest.mark.asyncio
    async def test_raises_error_when_status_not_success(self):
        from ii_agent.integrations.connectors.composio.router import complete_oauth_flow
        from ii_agent.integrations.connectors.composio.exceptions import ComposioOAuthError
        from ii_agent.integrations.connectors.composio.schemas import CompleteOAuthRequest

        mock_svc = MagicMock()
        mock_user = MagicMock()
        mock_db = MagicMock()

        request = CompleteOAuthRequest(
            status="failed",
            appName="gmail",
            connectedAccountId="acc-1",
        )

        with pytest.raises(ComposioOAuthError):
            await complete_oauth_flow(
                current_user=mock_user,
                db=mock_db,
                svc=mock_svc,
                request=request,
            )

    @pytest.mark.asyncio
    async def test_completes_oauth_on_success(self):
        from ii_agent.integrations.connectors.composio.router import complete_oauth_flow
        from ii_agent.integrations.connectors.composio.schemas import CompleteOAuthRequest

        mock_svc = MagicMock()
        mock_svc.complete_oauth = AsyncMock(return_value=True)
        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_db = MagicMock()

        request = CompleteOAuthRequest(
            status="success",
            appName="gmail",
            connectedAccountId="acc-1",
        )

        result = await complete_oauth_flow(
            current_user=mock_user,
            db=mock_db,
            svc=mock_svc,
            request=request,
        )
        assert result["success"] is True


class TestComposioRouterGetStatus:
    @pytest.mark.asyncio
    async def test_enabled_when_any_profile_enabled(self):
        from ii_agent.integrations.connectors.composio.router import get_composio_status

        mock_profile1 = MagicMock()
        mock_profile1.status = "enable"
        mock_profile1.model_dump.return_value = {"id": "p1", "status": "enable"}

        mock_svc = MagicMock()
        mock_svc.get_profiles = AsyncMock(return_value=[mock_profile1])
        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_db = MagicMock()

        result = await get_composio_status(
            current_user=mock_user,
            db=mock_db,
            svc=mock_svc,
            toolkit_slug="gmail",
        )
        assert result.status == "enable"

    @pytest.mark.asyncio
    async def test_disable_when_no_profiles(self):
        from ii_agent.integrations.connectors.composio.router import get_composio_status

        mock_svc = MagicMock()
        mock_svc.get_profiles = AsyncMock(return_value=[])
        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_db = MagicMock()

        result = await get_composio_status(
            current_user=mock_user,
            db=mock_db,
            svc=mock_svc,
            toolkit_slug="gmail",
        )
        assert result.status == "disable"
