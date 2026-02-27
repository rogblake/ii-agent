"""Unit tests for v1 tool implementations.

Covers: web tools, plan tools, productivity tools, media tools, dev tools,
browser tools, file system tools, and base tool patterns.
The tests let internal logic run; only external I/O is mocked.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_deps(**kwargs):
    """Minimal ToolDependencies stub."""
    deps = SimpleNamespace(
        tool_client=MagicMock(),
        session_service=MagicMock(),
        project_service=MagicMock(),
        **kwargs,
    )
    return deps


def _make_search_response(results, cost=0.0):
    resp = SimpleNamespace(result=results, cost=cost)
    return resp


def _make_visit_response(content, cost=0.0):
    return SimpleNamespace(content=content, cost=cost)


# ===========================================================================
# Web tools
# ===========================================================================


class TestWebSearchTool:
    """Tests for WebSearchTool.execute()."""

    async def _run(self, tool_input, *, search_response=None, side_effect=None):
        from ii_agent.engine.v1.tools.web.web_search_tool import WebSearchTool

        tool = WebSearchTool()
        deps = _make_tool_deps()
        if side_effect is not None:
            deps.tool_client.web_search = AsyncMock(side_effect=side_effect)
        else:
            deps.tool_client.web_search = AsyncMock(return_value=search_response)
        tool.dependencies = deps
        return await tool.execute(tool_input)

    async def test_returns_results_on_success(self):
        results = [{"title": "A", "url": "http://a.com", "content": "snippet"}]
        resp = _make_search_response(results, cost=0.01)
        result = await self._run({"query": "python"}, search_response=resp)
        assert result.is_error is not True
        assert "A" in result.llm_content or "http://a.com" in result.llm_content

    async def test_is_error_on_exception(self):
        result = await self._run(
            {"query": "fail"}, side_effect=Exception("network error")
        )
        assert result.is_error is True
        assert "network error" in result.llm_content

    async def test_empty_results_returns_not_error(self):
        resp = _make_search_response([], cost=0.0)
        result = await self._run({"query": "noresults"}, search_response=resp)
        # Empty results should not be an error per source code
        assert result.is_error is False

    async def test_empty_results_message_contains_query(self):
        resp = _make_search_response([], cost=0.0)
        result = await self._run({"query": "mysearchterm"}, search_response=resp)
        assert "mysearchterm" in result.llm_content

    async def test_results_truncated_to_max(self):
        # Create 20 results – MAX_RESULTS = 12, so only first 12 should be used
        results = [{"title": f"T{i}", "url": f"http://t{i}.com"} for i in range(20)]
        resp = _make_search_response(results, cost=0.0)
        result = await self._run({"query": "many"}, search_response=resp)
        data = json.loads(result.llm_content)
        assert len(data) <= 12

    async def test_cost_propagated(self):
        results = [{"title": "X"}]
        resp = _make_search_response(results, cost=0.05)
        result = await self._run({"query": "q"}, search_response=resp)
        assert result.cost == 0.05

    async def test_tool_attributes(self):
        from ii_agent.engine.v1.tools.web.web_search_tool import WebSearchTool

        t = WebSearchTool()
        assert t.name == "web_search"
        assert t.read_only is True


class TestWebVisitTool:
    """Tests for WebVisitTool.execute()."""

    async def _run(self, tool_input, *, visit_response=None, side_effect=None):
        from ii_agent.engine.v1.tools.web.web_visit_tool import WebVisitTool

        tool = WebVisitTool()
        deps = _make_tool_deps()
        if side_effect is not None:
            deps.tool_client.web_visit = AsyncMock(side_effect=side_effect)
        else:
            deps.tool_client.web_visit = AsyncMock(return_value=visit_response)
        tool.dependencies = deps
        return await tool.execute(tool_input)

    async def test_success_returns_content(self):
        resp = _make_visit_response("page content here", cost=0.02)
        result = await self._run({"url": "http://example.com"}, visit_response=resp)
        assert result.llm_content == "page content here"
        assert result.is_error is not True

    async def test_empty_content_returns_error(self):
        resp = _make_visit_response("", cost=0.0)
        result = await self._run({"url": "http://example.com"}, visit_response=resp)
        assert result.is_error is True

    async def test_none_content_returns_error(self):
        resp = _make_visit_response(None, cost=0.0)
        result = await self._run({"url": "http://example.com"}, visit_response=resp)
        assert result.is_error is True

    async def test_whitespace_only_content_returns_error(self):
        resp = _make_visit_response("   \n  ", cost=0.0)
        result = await self._run({"url": "http://example.com"}, visit_response=resp)
        assert result.is_error is True

    async def test_exception_returns_error(self):
        result = await self._run(
            {"url": "http://example.com"}, side_effect=Exception("timeout")
        )
        assert result.is_error is True
        assert "timeout" in result.llm_content

    async def test_arxiv_abs_url_rewritten(self):
        """arxiv.org/abs URLs should be rewritten to /html/."""
        captured_url = {}

        async def mock_visit(url, prompt=None):
            captured_url["url"] = url
            return _make_visit_response("content", 0.0)

        from ii_agent.engine.v1.tools.web.web_visit_tool import WebVisitTool

        tool = WebVisitTool()
        deps = _make_tool_deps()
        deps.tool_client.web_visit = mock_visit
        tool.dependencies = deps

        await tool.execute({"url": "https://arxiv.org/abs/2301.12345"})
        assert "html" in captured_url["url"]
        assert "abs" not in captured_url["url"]

    async def test_cost_propagated(self):
        resp = _make_visit_response("data", cost=0.08)
        result = await self._run({"url": "http://example.com"}, visit_response=resp)
        assert result.cost == 0.08

    async def test_optional_prompt_passed(self):
        captured = {}

        async def mock_visit(url, prompt=None):
            captured["prompt"] = prompt
            return _make_visit_response("ok", 0.0)

        from ii_agent.engine.v1.tools.web.web_visit_tool import WebVisitTool

        tool = WebVisitTool()
        deps = _make_tool_deps()
        deps.tool_client.web_visit = mock_visit
        tool.dependencies = deps

        await tool.execute({"url": "http://x.com", "prompt": "summarize"})
        assert captured["prompt"] == "summarize"


class TestWebBatchSearchTool:
    """Tests for WebBatchSearchTool.execute()."""

    async def _run(self, tool_input, *, responses=None, side_effect=None):
        from ii_agent.engine.v1.tools.web.web_batch_search_tool import WebBatchSearchTool

        tool = WebBatchSearchTool()
        deps = _make_tool_deps()
        if side_effect is not None:
            deps.tool_client.web_batch_search = AsyncMock(side_effect=side_effect)
        else:
            deps.tool_client.web_batch_search = AsyncMock(return_value=responses)
        tool.dependencies = deps
        return await tool.execute(tool_input)

    async def test_success_returns_formatted_output(self):
        items = [{"title": "R1", "url": "http://r1.com", "content": "snippet1"}]
        responses = [SimpleNamespace(result=items, cost=0.01)]
        result = await self._run(
            {"queries": ["query1"]}, responses=responses
        )
        assert "query1" in result.llm_content
        assert result.is_error is not True

    async def test_exception_returns_error(self):
        result = await self._run(
            {"queries": ["q"]}, side_effect=Exception("fail")
        )
        assert result.is_error is True

    async def test_empty_results_returns_no_results_message(self):
        responses = []
        result = await self._run({"queries": ["q1", "q2"]}, responses=responses)
        # When results is empty (len 0), it goes into the empty branch
        assert result.is_error is False

    async def test_multiple_queries_formatted(self):
        items_a = [{"title": "A", "url": "http://a.com", "content": "ca"}]
        items_b = [{"title": "B", "url": "http://b.com", "content": "cb"}]
        responses = [
            SimpleNamespace(result=items_a, cost=0.0),
            SimpleNamespace(result=items_b, cost=0.0),
        ]
        result = await self._run(
            {"queries": ["first query", "second query"]}, responses=responses
        )
        assert "first query" in result.llm_content
        assert "second query" in result.llm_content


class TestWebVisitCompressTool:
    """Tests for WebVisitCompressTool.execute()."""

    async def _run(self, tool_input, *, visit_response=None, side_effect=None):
        from ii_agent.engine.v1.tools.web.web_visit_compress import WebVisitCompressTool

        tool = WebVisitCompressTool()
        deps = _make_tool_deps()
        if side_effect is not None:
            deps.tool_client.researcher_web_visit = AsyncMock(side_effect=side_effect)
        else:
            deps.tool_client.researcher_web_visit = AsyncMock(return_value=visit_response)
        tool.dependencies = deps
        return await tool.execute(tool_input)

    async def test_success_returns_content(self):
        resp = SimpleNamespace(content="compressed data", cost=0.03)
        result = await self._run(
            {"urls": ["http://x.com"], "query": "info"},
            visit_response=resp,
        )
        assert result.llm_content == "compressed data"
        assert result.is_error is not True

    async def test_arxiv_abs_rewritten(self):
        captured = {}

        async def mock_visit(urls, query):
            captured["urls"] = urls
            return SimpleNamespace(content="ok", cost=0.0)

        from ii_agent.engine.v1.tools.web.web_visit_compress import WebVisitCompressTool

        tool = WebVisitCompressTool()
        deps = _make_tool_deps()
        deps.tool_client.researcher_web_visit = mock_visit
        tool.dependencies = deps

        await tool.execute({"urls": ["https://arxiv.org/abs/1234"], "query": "q"})
        assert "html" in captured["urls"][0]

    async def test_exception_returns_error(self):
        result = await self._run(
            {"urls": ["http://x.com"], "query": "q"},
            side_effect=Exception("network error"),
        )
        assert result.is_error is True

    async def test_cost_propagated(self):
        resp = SimpleNamespace(content="data", cost=0.07)
        result = await self._run(
            {"urls": ["http://x.com"], "query": "q"}, visit_response=resp
        )
        assert result.cost == 0.07


# ===========================================================================
# Plan tools
# ===========================================================================


class TestMilestoneTool:
    """Tests for MilestoneTool.execute()."""

    def _make_tool(self, *, on_plan_submit=None, event_stream=None):
        from ii_agent.engine.v1.tools.plan.milestone import MilestoneTool

        session_svc = MagicMock()
        event_svc = MagicMock()
        return MilestoneTool(
            session_id=uuid.uuid4(),
            session_service=session_svc,
            event_service=event_svc,
            on_plan_submit=on_plan_submit,
            event_stream=event_stream,
        )

    async def test_uses_callback_when_no_event_stream(self):
        callback_called_with = {}

        async def mock_callback(plan_data):
            callback_called_with.update(plan_data)

        tool = self._make_tool(on_plan_submit=mock_callback)
        result = await tool.execute(
            {
                "summary": "Build app",
                "milestones": [{"id": "m1", "content": "Step 1", "details": "Details"}],
            }
        )
        assert result.is_error is False
        assert callback_called_with["summary"] == "Build app"

    async def test_raises_when_neither_provided(self):
        tool = self._make_tool()
        result = await tool.execute(
            {
                "summary": "Oops",
                "milestones": [{"id": "m1", "content": "c", "details": "d"}],
            }
        )
        # Should return an error because no event_stream or on_plan_submit
        assert result.is_error is True

    async def test_milestones_get_pending_status(self):
        collected = {}

        async def collect(plan_data):
            collected.update(plan_data)

        tool = self._make_tool(on_plan_submit=collect)
        await tool.execute(
            {
                "summary": "Plan",
                "milestones": [
                    {"id": "m1", "content": "M1", "details": "d1"},
                    {"id": "m2", "content": "M2", "details": "d2"},
                ],
            }
        )
        for m in collected["milestones"]:
            assert m["status"] == "pending"

    async def test_existing_status_not_overwritten(self):
        collected = {}

        async def collect(plan_data):
            collected.update(plan_data)

        tool = self._make_tool(on_plan_submit=collect)
        await tool.execute(
            {
                "summary": "Plan",
                "milestones": [
                    {
                        "id": "m1",
                        "content": "M1",
                        "details": "d1",
                        "status": "completed",
                    }
                ],
            }
        )
        assert collected["milestones"][0]["status"] == "completed"

    async def test_success_result_has_display_content(self):
        async def collect(_):
            pass

        tool = self._make_tool(on_plan_submit=collect)
        result = await tool.execute(
            {"summary": "S", "milestones": [{"id": "1", "content": "c", "details": "d"}]}
        )
        assert isinstance(result.user_display_content, dict)
        assert "summary" in result.user_display_content

    async def test_is_interrupted_on_success(self):
        async def collect(_):
            pass

        tool = self._make_tool(on_plan_submit=collect)
        result = await tool.execute(
            {"summary": "S", "milestones": [{"id": "1", "content": "c", "details": "d"}]}
        )
        # MilestoneTool sets is_interrupted=True on success
        assert result.is_interrupted is True

    async def test_uses_event_stream_when_provided(self):
        event_stream = AsyncMock()
        event_stream.publish = AsyncMock()

        session_svc = MagicMock()
        session_svc.get_session_by_id = AsyncMock(return_value=None)

        from ii_agent.engine.v1.tools.plan.milestone import MilestoneTool
        import ii_agent.core.db.manager as db_manager_module

        tool = MilestoneTool(
            session_id=uuid.uuid4(),
            session_service=session_svc,
            event_service=MagicMock(),
            event_stream=event_stream,
        )

        with patch.object(db_manager_module, "get_db_session_local") as mock_db_local:
            mock_ctx = MagicMock()
            mock_db = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_db_local.return_value = mock_ctx

            result = await tool.execute(
                {
                    "summary": "Plan with stream",
                    "milestones": [{"id": "m1", "content": "C", "details": "D"}],
                }
            )

        assert result.is_error is False


class TestPlanModificationSuggestionsTool:
    """Tests for PlanModificationSuggestionsTool.execute()."""

    def _make_tool(self, event_stream=None):
        from ii_agent.engine.v1.tools.plan.suggestion import (
            PlanModificationSuggestionsTool,
        )

        return PlanModificationSuggestionsTool(
            session_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_stream=event_stream,
        )

    async def test_success_with_event_stream(self):
        event_stream = AsyncMock()
        event_stream.publish = AsyncMock()
        tool = self._make_tool(event_stream=event_stream)

        result = await tool.execute(
            {
                "message": "How do you want to change?",
                "suggestions": [
                    {
                        "id": "s1",
                        "label": "Add auth",
                        "description": "Add authentication",
                        "prompt_template": "Add auth",
                    }
                ],
            }
        )
        assert result.is_error is False
        event_stream.publish.assert_called_once()

    async def test_success_without_event_stream(self):
        tool = self._make_tool()
        result = await tool.execute(
            {
                "message": "Modify?",
                "suggestions": [
                    {
                        "id": "s1",
                        "label": "X",
                        "description": "Desc",
                        "prompt_template": "P",
                    }
                ],
            }
        )
        # No error even without event_stream
        assert result.is_error is False

    async def test_default_message_when_not_provided(self):
        tool = self._make_tool()
        result = await tool.execute({"suggestions": []})
        assert "modify" in result.llm_content.lower() or result.is_error is False

    async def test_display_content_contains_suggestions(self):
        tool = self._make_tool()
        suggestions = [
            {"id": "s1", "label": "L", "description": "D", "prompt_template": "P"}
        ]
        result = await tool.execute({"message": "M", "suggestions": suggestions})
        assert result.user_display_content["suggestions"] == suggestions

    async def test_exception_returns_error(self):
        event_stream = AsyncMock()
        event_stream.publish = AsyncMock(side_effect=Exception("stream error"))
        tool = self._make_tool(event_stream=event_stream)
        result = await tool.execute(
            {"message": "M", "suggestions": [{"id": "1", "label": "L", "description": "D", "prompt_template": "P"}]}
        )
        assert result.is_error is True

    async def test_stop_after_tool_call_is_true(self):
        from ii_agent.engine.v1.tools.plan.suggestion import (
            PlanModificationSuggestionsTool,
        )

        assert PlanModificationSuggestionsTool.stop_after_tool_call is True


# ===========================================================================
# Productivity tools
# ===========================================================================


class TestValidateTodos:
    """Tests for _validate_todos() function."""

    def _validate(self, todos):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        _validate_todos(todos)

    def test_valid_single_todo(self):
        self._validate(
            [{"id": "1", "content": "Do something", "status": "pending", "priority": "high"}]
        )

    def test_invalid_not_a_list(self):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        with pytest.raises(ValueError, match="list"):
            _validate_todos("not a list")

    def test_invalid_todo_not_dict(self):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        with pytest.raises(ValueError):
            _validate_todos(["a string"])

    def test_missing_content_raises(self):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        with pytest.raises(ValueError, match="content"):
            _validate_todos([{"id": "1", "status": "pending", "priority": "high"}])

    def test_missing_status_raises(self):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        with pytest.raises(ValueError, match="status"):
            _validate_todos([{"id": "1", "content": "c", "priority": "high"}])

    def test_missing_priority_raises(self):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        with pytest.raises(ValueError, match="priority"):
            _validate_todos([{"id": "1", "content": "c", "status": "pending"}])

    def test_missing_id_raises(self):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        with pytest.raises(ValueError, match="id"):
            _validate_todos([{"content": "c", "status": "pending", "priority": "high"}])

    def test_invalid_status_raises(self):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        with pytest.raises(ValueError, match="status"):
            _validate_todos(
                [{"id": "1", "content": "c", "status": "INVALID", "priority": "high"}]
            )

    def test_invalid_priority_raises(self):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        with pytest.raises(ValueError, match="priority"):
            _validate_todos(
                [{"id": "1", "content": "c", "status": "pending", "priority": "INVALID"}]
            )

    def test_empty_content_raises(self):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        with pytest.raises(ValueError, match="empty"):
            _validate_todos(
                [{"id": "1", "content": "  ", "status": "pending", "priority": "low"}]
            )

    def test_multiple_in_progress_raises(self):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import _validate_todos

        with pytest.raises(ValueError, match="in_progress"):
            _validate_todos(
                [
                    {
                        "id": "1",
                        "content": "A",
                        "status": "in_progress",
                        "priority": "high",
                    },
                    {
                        "id": "2",
                        "content": "B",
                        "status": "in_progress",
                        "priority": "low",
                    },
                ]
            )

    def test_single_in_progress_ok(self):
        self._validate(
            [
                {"id": "1", "content": "A", "status": "in_progress", "priority": "high"},
                {"id": "2", "content": "B", "status": "pending", "priority": "low"},
            ]
        )

    def test_all_completed_ok(self):
        self._validate(
            [
                {"id": "1", "content": "A", "status": "completed", "priority": "high"},
                {"id": "2", "content": "B", "status": "completed", "priority": "medium"},
            ]
        )


class TestTodoWriteTool:
    """Tests for TodoWriteTool.execute()."""

    def _make_tool(self, session_id="sess-1"):
        from ii_agent.engine.v1.tools.productivity.todo_write_tool import TodoWriteTool

        tool = TodoWriteTool()
        tool._session_id = session_id
        return tool

    def _make_deps_with_session(self, session):
        deps = _make_tool_deps()
        deps.session_service.get_session_by_id = AsyncMock(return_value=session)
        return deps

    async def test_no_session_id_returns_error(self):
        tool = self._make_tool(session_id=None)
        deps = _make_tool_deps()
        tool.dependencies = deps

        result = await tool.execute(
            {"todos": [{"id": "1", "content": "c", "status": "pending", "priority": "high"}]}
        )
        assert result.is_error is True

    async def test_session_not_found_returns_error(self):
        tool = self._make_tool()
        deps = self._make_deps_with_session(None)
        tool.dependencies = deps

        with patch(
            "ii_agent.engine.v1.tools.productivity.todo_write_tool.get_db_session_local"
        ) as mock_db:
            mock_ctx = MagicMock()
            mock_db_session = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_ctx

            result = await tool.execute(
                {"todos": [{"id": "1", "content": "c", "status": "pending", "priority": "high"}]}
            )
        assert result.is_error is True

    async def test_invalid_todos_returns_error(self):
        tool = self._make_tool()
        deps = _make_tool_deps()
        tool.dependencies = deps

        result = await tool.execute({"todos": "not a list"})
        assert result.is_error is True

    async def test_success_returns_success_message(self):
        session = SimpleNamespace(session_metadata={})
        tool = self._make_tool()
        deps = self._make_deps_with_session(session)
        tool.dependencies = deps

        with patch(
            "ii_agent.engine.v1.tools.productivity.todo_write_tool.get_db_session_local"
        ) as mock_db:
            mock_ctx = MagicMock()
            mock_db_session = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_ctx

            result = await tool.execute(
                {
                    "todos": [
                        {"id": "1", "content": "Task 1", "status": "pending", "priority": "high"}
                    ]
                }
            )
        assert result.is_error is False
        assert "success" in result.llm_content.lower() or "modified" in result.llm_content.lower()


class TestTodoReadTool:
    """Tests for TodoReadTool.execute()."""

    def _make_tool(self, session_id="sess-1"):
        from ii_agent.engine.v1.tools.productivity.todo_read_tool import TodoReadTool

        tool = TodoReadTool()
        tool._session_id = session_id
        return tool

    async def test_no_session_id_returns_error(self):
        tool = self._make_tool(session_id=None)
        deps = _make_tool_deps()
        tool.dependencies = deps

        result = await tool.execute({})
        assert result.is_error is True

    async def test_session_not_found_returns_error(self):
        tool = self._make_tool()
        deps = _make_tool_deps()
        deps.session_service.get_session_by_id = AsyncMock(return_value=None)
        tool.dependencies = deps

        with patch(
            "ii_agent.engine.v1.tools.productivity.todo_read_tool.get_db_session_local"
        ) as mock_db:
            mock_ctx = MagicMock()
            mock_db_session = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_ctx

            result = await tool.execute({})
        assert result.is_error is True

    async def test_empty_todos_returns_empty_message(self):
        session = SimpleNamespace(session_metadata={})
        tool = self._make_tool()
        deps = _make_tool_deps()
        deps.session_service.get_session_by_id = AsyncMock(return_value=session)
        tool.dependencies = deps

        with patch(
            "ii_agent.engine.v1.tools.productivity.todo_read_tool.get_db_session_local"
        ) as mock_db:
            mock_ctx = MagicMock()
            mock_db_session = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_ctx

            result = await tool.execute({})
        assert result.is_error is False
        assert "No todos" in result.llm_content

    async def test_todos_returned_on_success(self):
        todos = [{"id": "1", "content": "Task", "status": "pending", "priority": "high"}]
        session = SimpleNamespace(session_metadata={"todos": todos})
        tool = self._make_tool()
        deps = _make_tool_deps()
        deps.session_service.get_session_by_id = AsyncMock(return_value=session)
        tool.dependencies = deps

        with patch(
            "ii_agent.engine.v1.tools.productivity.todo_read_tool.get_db_session_local"
        ) as mock_db:
            mock_ctx = MagicMock()
            mock_db_session = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_ctx

            result = await tool.execute({})
        assert result.is_error is False
        assert "Task" in result.llm_content

    async def test_non_list_todos_returns_empty_message(self):
        session = SimpleNamespace(session_metadata={"todos": "invalid"})
        tool = self._make_tool()
        deps = _make_tool_deps()
        deps.session_service.get_session_by_id = AsyncMock(return_value=session)
        tool.dependencies = deps

        with patch(
            "ii_agent.engine.v1.tools.productivity.todo_read_tool.get_db_session_local"
        ) as mock_db:
            mock_ctx = MagicMock()
            mock_db_session = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_ctx

            result = await tool.execute({})
        assert result.is_error is False
        assert "No todos" in result.llm_content


# ===========================================================================
# Media tools
# ===========================================================================


class TestImageGenerateTool:
    """Tests for ImageGenerateTool.execute()."""

    def _make_tool(self, session_id="sess-1"):
        from ii_agent.engine.v1.tools.media.image_generate import ImageGenerateTool

        tool = ImageGenerateTool()
        tool.session_id = session_id
        tool.sandbox = AsyncMock()
        tool.sandbox.write_file = AsyncMock()
        return tool

    async def test_non_png_output_path_returns_error(self):
        tool = self._make_tool()
        deps = _make_tool_deps()
        tool.dependencies = deps

        result = await tool.execute(
            {"prompt": "A cat", "output_path": "/workspace/image.jpg"}
        )
        assert result.is_error is True
        assert ".png" in result.llm_content

    async def test_exception_from_generate_returns_error(self):
        tool = self._make_tool()
        deps = _make_tool_deps()
        deps.tool_client.generate_image = AsyncMock(side_effect=Exception("API down"))
        tool.dependencies = deps

        result = await tool.execute(
            {"prompt": "A cat", "output_path": "/workspace/image.png"}
        )
        assert result.is_error is True
        assert "API down" in result.llm_content

    async def test_no_url_returns_error(self):
        tool = self._make_tool()
        deps = _make_tool_deps()
        img_resp = SimpleNamespace(
            url=None, mime_type=None, size=0, search_results=[]
        )
        deps.tool_client.generate_image = AsyncMock(return_value=img_resp)
        tool.dependencies = deps

        result = await tool.execute(
            {"prompt": "A cat", "output_path": "/workspace/image.png"}
        )
        assert result.is_error is True

    async def test_no_url_with_search_results_writes_summary(self):
        tool = self._make_tool()
        deps = _make_tool_deps()
        search_results = [{"title": "Cat", "source": "Google", "image_url": "http://cat.jpg"}]
        img_resp = SimpleNamespace(
            url=None, mime_type=None, size=0, search_results=search_results
        )
        deps.tool_client.generate_image = AsyncMock(return_value=img_resp)
        tool.dependencies = deps

        result = await tool.execute(
            {"prompt": "A cat", "output_path": "/workspace/image.png"}
        )
        # Should NOT be error - it writes a summary instead
        assert result.is_error is not True

    async def test_write_search_summary_formats_correctly(self):
        tool = self._make_tool()
        tool.sandbox.write_file = AsyncMock()
        await tool._write_search_summary(
            output_path="/workspace/image.png",
            prompt="A dog",
            search_results=[
                {"title": "Dog", "source": "Bing", "image_url": "http://dog.jpg"},
                {"title": None, "source": None, "url": "http://dog2.jpg"},
            ],
        )
        written_content = tool.sandbox.write_file.call_args[0][1]
        assert "Dog" in written_content
        assert "DuckDuckGo" in written_content

    async def test_success_returns_markdown_image(self):
        import httpx

        tool = self._make_tool()
        deps = _make_tool_deps()
        img_resp = SimpleNamespace(
            url="http://img.example.com/img.png",
            mime_type="image/png",
            size=12345,
            search_results=[],
            cost=0.02,
        )
        deps.tool_client.generate_image = AsyncMock(return_value=img_resp)
        tool.dependencies = deps

        # Mock httpx download
        mock_http_resp = MagicMock()
        mock_http_resp.raise_for_status = MagicMock()
        mock_http_resp.content = b"PNG data"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_http_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await tool.execute(
                {"prompt": "A cat", "output_path": "/workspace/image.png"}
            )

        assert "![" in result.llm_content
        assert result.cost == 0.02


# ===========================================================================
# Dev tools – basic attribute checks
# ===========================================================================


class TestDevToolAttributes:
    """Verify dev tool class attributes are properly defined."""

    def test_restart_server_tool_name(self):
        from ii_agent.engine.v1.tools.dev.restart_server import RestartServerTool

        assert RestartServerTool.name == "restart_fullstack_servers"
        assert RestartServerTool.read_only is False

    def test_get_server_status_tool_name(self):
        from ii_agent.engine.v1.tools.dev.server_status import GetServerStatusTool

        assert GetServerStatusTool.name == "get_server_status"
        assert GetServerStatusTool.read_only is True

    def test_save_checkpoint_tool_name(self):
        from ii_agent.engine.v1.tools.dev.save_checkpoint import SaveCheckpointTool

        assert SaveCheckpointTool.name == "save_checkpoint"
        assert SaveCheckpointTool.read_only is False

    def test_save_checkpoint_required_fields(self):
        from ii_agent.engine.v1.tools.dev.save_checkpoint import SaveCheckpointTool

        required = SaveCheckpointTool.input_schema["required"]
        assert "project_directory" in required
        assert "commit_message" in required


class TestRegisterPort:
    """Tests for RegisterPort.execute()."""

    async def test_no_sandbox_returns_error(self):
        from ii_agent.engine.v1.tools.dev.register_port import RegisterPort

        tool = RegisterPort()
        tool.sandbox = None

        result = await tool.execute({"port": 3000})
        assert result.is_error is True
        assert "Sandbox" in result.llm_content

    async def test_no_port_returns_error(self):
        from ii_agent.engine.v1.tools.dev.register_port import RegisterPort

        tool = RegisterPort()
        tool.sandbox = AsyncMock()

        result = await tool.execute({})
        assert result.is_error is True
        assert "port" in result.llm_content

    async def test_success_returns_url(self):
        from ii_agent.engine.v1.tools.dev.register_port import RegisterPort

        tool = RegisterPort()
        tool.sandbox = AsyncMock()
        tool.sandbox.expose_port = AsyncMock(return_value="http://exposed.example.com")

        result = await tool.execute({"port": 3000})
        assert result.is_error is False
        assert "3000" in result.llm_content


# ===========================================================================
# Browser tool attributes
# ===========================================================================


class TestBrowserToolAttributes:
    """Verify browser tool class attribute correctness."""

    def test_browser_navigation_tool_name(self):
        from ii_agent.engine.v1.tools.browser.navigate import BrowserNavigationTool

        assert BrowserNavigationTool.name == "browser_navigation"
        assert BrowserNavigationTool.read_only is False

    def test_browser_restart_tool_name(self):
        from ii_agent.engine.v1.tools.browser.navigate import BrowserRestartTool

        assert BrowserRestartTool.name == "browser_restart"

    def test_browser_view_tool_name(self):
        from ii_agent.engine.v1.tools.browser.view import BrowserViewTool

        assert BrowserViewTool.name == "browser_view_interactive_elements"

    def test_browser_navigation_url_required(self):
        from ii_agent.engine.v1.tools.browser.navigate import BrowserNavigationTool

        assert "url" in BrowserNavigationTool.input_schema["required"]


# ===========================================================================
# Base tool – BaseAgentTool & AgentAsTool
# ===========================================================================


class TestBaseAgentTool:
    """Tests for BaseAgentTool abstract class methods."""

    def test_should_confirm_execute_returns_false_by_default(self):
        from ii_agent.engine.v1.tools.base import BaseAgentTool

        class MinimalTool(BaseAgentTool):
            name = "minimal"
            description = "minimal"
            input_schema = {}
            read_only = True
            display_name = "Minimal"

            async def execute(self, tool_input):
                pass

        tool = MinimalTool()
        assert tool.should_confirm_execute({}) is False

    async def test_on_tool_start_is_no_op(self):
        from ii_agent.engine.v1.tools.base import BaseAgentTool

        class MinimalTool(BaseAgentTool):
            name = "minimal"
            description = "minimal"
            input_schema = {}
            read_only = True
            display_name = "Minimal"

            async def execute(self, tool_input):
                pass

        tool = MinimalTool()
        # Should not raise
        await tool.on_tool_start(MagicMock(), MagicMock())

    async def test_on_tool_end_is_no_op(self):
        from ii_agent.engine.v1.tools.base import BaseAgentTool

        class MinimalTool(BaseAgentTool):
            name = "minimal"
            description = "minimal"
            input_schema = {}
            read_only = True
            display_name = "Minimal"

            async def execute(self, tool_input):
                pass

        tool = MinimalTool()
        # Should not raise
        await tool.on_tool_end(MagicMock(), MagicMock())


class TestAgentAsTool:
    """Tests for AgentAsTool wrapper."""

    async def test_execute_calls_agent_arun(self):
        from ii_agent.engine.v1.tools.base import AgentAsTool

        mock_agent = MagicMock()
        mock_agent.name = "sub_agent"
        mock_agent.description = "A sub-agent"
        mock_agent.session_id = "s1"
        mock_agent.user_id = "u1"
        mock_agent.arun = AsyncMock(
            return_value=SimpleNamespace(content="agent output")
        )

        tool = AgentAsTool(
            agent_instance=mock_agent,
            input_schema={"type": "object", "properties": {}},
        )
        result = await tool.execute({"prompt": "do something"})
        assert result.is_error is False
        assert "agent output" in result.llm_content

    async def test_execute_handles_agent_exception(self):
        from ii_agent.engine.v1.tools.base import AgentAsTool

        mock_agent = MagicMock()
        mock_agent.name = "broken_agent"
        mock_agent.description = "Broken"
        mock_agent.session_id = "s1"
        mock_agent.user_id = "u1"
        mock_agent.arun = AsyncMock(side_effect=Exception("agent crashed"))

        tool = AgentAsTool(
            agent_instance=mock_agent,
            input_schema={"type": "object", "properties": {}},
        )
        result = await tool.execute({"prompt": "do something"})
        assert result.is_error is True
        assert "agent crashed" in result.llm_content

    def test_name_defaults_to_agent_name(self):
        from ii_agent.engine.v1.tools.base import AgentAsTool

        mock_agent = MagicMock()
        mock_agent.name = "my_agent"
        mock_agent.description = "Desc"
        tool = AgentAsTool(agent_instance=mock_agent, input_schema={})
        assert tool.name == "my_agent"

    def test_custom_name_overrides_agent_name(self):
        from ii_agent.engine.v1.tools.base import AgentAsTool

        mock_agent = MagicMock()
        mock_agent.name = "original"
        mock_agent.description = "Desc"
        tool = AgentAsTool(agent_instance=mock_agent, input_schema={}, name="custom")
        assert tool.name == "custom"
