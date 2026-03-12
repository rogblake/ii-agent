"""Targeted coverage tests for project routers and request/response wiring."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import AsyncMock

import pytest

from ii_agent.projects import router as project_router
from ii_agent.projects.databases.router import (
    get_project_database_records,
    get_project_database_schema,
)
from ii_agent.projects.databases.schemas import TableRecordsResult
from ii_agent.projects.deployments.exceptions import DeploymentNotFoundError
from ii_agent.projects.deployments.router import get_project_deployment
from ii_agent.projects.exceptions import ProjectNotFoundError
from ii_agent.projects.secrets.router import (
    get_session_project_secrets,
    set_session_project_secrets,
)
from ii_agent.projects.secrets.schemas import ProjectSecretsRequest
from ii_agent.projects.design.router import (
    ai_change,
    ai_iframe_plan,
    get_design_state,
    proxy_design_mode,
    save_design_state,
)
from ii_agent.projects.design.schemas import (
    AIChangeRequest,
    AIChangeResponse,
    DesignStateRequest,
    ElementInfoRequest,
    IframeAIPlanRequest,
    IframeAIPlanResponse,
    StyleChange,
)


def _user(user_id: str = "user-1") -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


def _project_for_session_response(
    *,
    project_id: str = "project-1",
    user_id: str = "user-1",
    session_id: str = "session-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=project_id,
        user_id=user_id,
        session_id=session_id,
        name="Demo Project",
        description=None,
        status="ready",
        current_build_status="idle",
        framework=None,
        project_path="/tmp/project",
        production_url=None,
        database_json={"url": "postgres://localhost"},
        storage_json=None,
        secrets_json={"env": "local"},
        current_production_deployment_id=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_router_get_session_project_forwards_to_service():
    service = AsyncMock()
    service.get_session_project.return_value = _project_for_session_response()

    result = await project_router.get_session_project(
        "session-1",
        _user("user-1"),
        service,
        None,
    )

    service.get_session_project.assert_awaited_once_with(
        None,
        session_id="session-1",
        user_id="user-1",
    )
    assert result.id == "project-1"


@pytest.mark.asyncio
async def test_databases_router_get_schema_success():
    database_service = AsyncMock()
    database_service.get_project_db_tables.return_value = ["users", "events"]

    result = await get_project_database_schema(
        "project-1",
        _user("user-1"),
        database_service,
        None,
    )

    database_service.get_project_db_tables.assert_awaited_once_with(
        None,
        project_id="project-1",
        user_id="user-1",
    )
    assert result.project_id == "project-1"
    assert result.tables == ["users", "events"]


@pytest.mark.asyncio
async def test_databases_router_get_schema_missing_project():
    database_service = AsyncMock()
    database_service.get_project_db_tables.return_value = None

    with pytest.raises(ProjectNotFoundError):
        await get_project_database_schema(
            "project-1",
            _user("user-1"),
            database_service,
            None,
        )


@pytest.mark.asyncio
async def test_databases_router_get_records_success():
    database_service = AsyncMock()
    database_service.get_project_db_records.return_value = TableRecordsResult(
        rows=[{"id": 1}],
        total=1,
    )

    result = await get_project_database_records(
        "project-1",
        _user("user-1"),
        database_service,
        None,
        table="users",
        limit=20,
        offset=5,
    )

    database_service.get_project_db_records.assert_awaited_once_with(
        None,
        project_id="project-1",
        user_id="user-1",
        table_name="users",
        limit=20,
        offset=5,
    )
    assert result.total == 1
    assert result.rows == [{"id": 1}]


@pytest.mark.asyncio
async def test_databases_router_get_records_missing_project():
    database_service = AsyncMock()
    database_service.get_project_db_records.return_value = None

    with pytest.raises(ProjectNotFoundError):
        await get_project_database_records(
            "project-1",
            _user("user-1"),
            database_service,
            None,
            table="users",
        )


@pytest.mark.asyncio
async def test_deployments_router_returns_deployment_on_success():
    service = AsyncMock()
    deployment = SimpleNamespace(id="dep-1", project_id="project-1", provider="aws")
    service.get_project_deployment.return_value = deployment

    result = await get_project_deployment(
        "project-1",
        _user("user-1"),
        service,
        None,
    )

    service.get_project_deployment.assert_awaited_once_with(
        None,
        user_id="user-1",
        project_id="project-1",
    )
    assert result.id == "dep-1"


@pytest.mark.asyncio
async def test_deployments_router_returns_empty_when_not_found():
    service = AsyncMock()
    service.get_project_deployment.side_effect = DeploymentNotFoundError("missing")
    result = await get_project_deployment("project-1", _user("user-1"), service, None)

    assert result.id is None
    assert result.project_id == "project-1"


@pytest.mark.asyncio
async def test_secrets_router_get_secrets_maps_project_payload():
    project = _project_for_session_response(session_id="00000000-0000-4000-8000-000000000001")
    service = AsyncMock()
    service.get_session_project.return_value = project

    result = await get_session_project_secrets(
        project.session_id,
        _user("user-1"),
        service,
        None,
    )

    service.get_session_project.assert_awaited_once_with(
        None,
        session_id=project.session_id,
        user_id="user-1",
    )
    assert result.session_id == project.session_id
    assert result.secrets == {"env": "local"}


@pytest.mark.asyncio
async def test_secrets_router_set_secrets_delegates_sync_and_returns_payload():
    project = _project_for_session_response(session_id="00000000-0000-4000-8000-000000000002")
    secret_service = AsyncMock()
    secret_service.replace_session_project_secrets.return_value = project

    sandbox_env_sync = AsyncMock()

    payload = ProjectSecretsRequest(secrets={"API_KEY": "abc"})
    result = await set_session_project_secrets(
        project.session_id,
        payload,
        _user("user-1"),
        secret_service,
        sandbox_env_sync,
        None,
    )

    secret_service.replace_session_project_secrets.assert_awaited_once_with(
        None,
        session_id=project.session_id,
        user_id="user-1",
        secrets={"API_KEY": "abc"},
    )
    sandbox_env_sync.sync_env_files.assert_awaited_once_with(
        None,
        session_id=UUID(project.session_id),
        secrets={"API_KEY": "abc"},
        project_path=project.project_path,
        database_url="postgres://localhost",
    )
    assert result.project_id == project.id


@pytest.mark.asyncio
async def test_design_router_proxy_returns_html_and_headers():
    service = AsyncMock()
    service.get_proxy_html.return_value = "<html/>"

    response = await proxy_design_mode(
        _user("user-1"),
        None,
        service,
        session_id="session-1",
        url="https://example.com",
    )

    service.get_proxy_html.assert_awaited_once_with(
        None,
        session_id="session-1",
        user_id="user-1",
        url="https://example.com",
    )
    assert response.body == b"<html/>"
    assert response.headers["Content-Security-Policy"] == "sandbox allow-scripts allow-forms allow-popups"


@pytest.mark.asyncio
async def test_design_router_ai_change_invokes_service():
    service = AsyncMock()
    service.ai_design_change.return_value = AIChangeResponse(changes=[], explanation="ok")
    request = AIChangeRequest(
        session_id="session-1",
        element_info=ElementInfoRequest(
            designId="d1",
            tagName="div",
            className="a",
            textContent="text",
            computedStyles={"color": "blue"},
            xpath="/html/body",
        ),
        user_request="make it red",
    )

    result = await ai_change(request, _user("user-1"), None, service)

    service.ai_design_change.assert_awaited_once_with(
        None,
        user_id="user-1",
        request=request,
    )
    assert result.explanation == "ok"


@pytest.mark.asyncio
async def test_design_router_ai_iframe_plan_invokes_service():
    service = AsyncMock()
    service.ai_iframe_plan.return_value = IframeAIPlanResponse(
        operations=[],
        explanation="plan-ready",
        document_snapshot=None,
    )
    request = IframeAIPlanRequest(
        session_id="session-1",
        user_request="adjust text",
        selected_element=None,
        document_snapshot={
            "version": 1,
            "generatedAt": None,
            "url": "https://example.com",
            "title": "x",
            "nodes": [],
        },
    )

    result = await ai_iframe_plan(request, _user("user-1"), None, service)
    service.ai_iframe_plan.assert_awaited_once_with(
        None,
        user_id="user-1",
        request=request,
    )
    assert result.explanation == "plan-ready"


@pytest.mark.asyncio
async def test_design_router_state_and_sync_routes_delegate():
    state_service = AsyncMock()
    state_service.get_design_state.return_value = DesignStateRequest(
        session_id="session-1",
        changes=[],
    )
    save_service = AsyncMock()
    save_service.save_design_state.return_value = DesignStateRequest(
        session_id="session-1",
        changes=[],
    )
    style_changes = [
        StyleChange(
            designId="d1",
            type="text",
            property="value",
            value={},
            timestamp=0,
        )
    ]
    state = await get_design_state(
        "session-1",
        _user("user-1"),
        None,
        state_service,
    )
    saved = await save_design_state(
        DesignStateRequest(
            session_id="session-1",
            changes=style_changes,
        ),
        _user("user-1"),
        None,
        save_service,
    )

    assert state is not None
    assert saved is not None
