from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.projects.subdomains.service import SubdomainService


def _domain(
    *,
    domain_id: str = "domain-1",
    project_id: str = "project-1",
    subdomain: str = "demo",
    full_domain: str = "demo.example.com",
):
    return SimpleNamespace(
        id=domain_id,
        project_id=project_id,
        subdomain=subdomain,
        full_domain=full_domain,
        deployment_id=None,
        dns_status="active",
        ssl_status="active",
        cloudflare_record_id=None,
        claimed_at=datetime.now(timezone.utc),
        claimed_by_user_id="user-1",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_create_custom_domain_creates_record_and_updates_project(settings_factory):
    subdomain_repo = AsyncMock()
    project_repo = AsyncMock()
    deployments_repo = AsyncMock()

    created = _domain()
    subdomain_repo.get_by_project_id.return_value = None
    subdomain_repo.create.return_value = created

    service = SubdomainService(
        subdomain_repo=subdomain_repo,
        project_repo=project_repo,
        deployments_repo=deployments_repo,
        config=settings_factory(),
    )

    result = await service.create_or_update_custom_domain(
        db=None,
        project_id="project-1",
        user_id="user-1",
        subdomain="demo",
        full_domain="demo.example.com",
        deployment_id="dep-1",
    )

    assert result.id == "domain-1"
    project_repo.update_custom_domain.assert_awaited_once_with(
        None,
        "project-1",
        "domain-1",
        "demo.example.com",
    )


@pytest.mark.asyncio
async def test_create_or_update_custom_domain_updates_existing_record(settings_factory):
    subdomain_repo = AsyncMock()
    project_repo = AsyncMock()
    deployments_repo = AsyncMock()

    existing = _domain(subdomain="old", full_domain="old.example.com")
    subdomain_repo.get_by_project_id.return_value = existing

    async def _update(db, domain):
        return domain

    subdomain_repo.update.side_effect = _update

    service = SubdomainService(
        subdomain_repo=subdomain_repo,
        project_repo=project_repo,
        deployments_repo=deployments_repo,
        config=settings_factory(),
    )

    result = await service.create_or_update_custom_domain(
        db=None,
        project_id="project-1",
        user_id="user-2",
        subdomain="new-subdomain",
        full_domain="new-subdomain.example.com",
        deployment_id="dep-2",
        cloudflare_record_id="cf-123",
    )

    assert result.subdomain == "new-subdomain"
    assert result.full_domain == "new-subdomain.example.com"
    assert existing.claimed_by_user_id == "user-2"
    assert existing.deployment_id == "dep-2"
    assert existing.cloudflare_record_id == "cf-123"


@pytest.mark.asyncio
async def test_delete_custom_domain_reverts_to_current_deployment_url(settings_factory):
    subdomain_repo = AsyncMock()
    project_repo = AsyncMock()
    deployments_repo = AsyncMock()

    project_repo.get_by_id_and_user.return_value = SimpleNamespace(
        current_production_deployment_id="dep-1"
    )
    subdomain_repo.get_by_project_id.return_value = _domain()
    deployments_repo.get_latest_deployment.return_value = SimpleNamespace(
        deployment_url="https://cloudrun.example.com"
    )

    service = SubdomainService(
        subdomain_repo=subdomain_repo,
        project_repo=project_repo,
        deployments_repo=deployments_repo,
        config=settings_factory(),
    )

    deleted = await service.delete_custom_domain(
        db=None,
        project_id="project-1",
        user_id="user-1",
    )

    assert deleted is True
    project_repo.update_custom_domain.assert_awaited_once_with(None, "project-1", None)
    project_repo.update_production_url.assert_awaited_once_with(
        None,
        "project-1",
        "https://cloudrun.example.com",
    )
    subdomain_repo.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_subdomain_record_enforces_non_admin_ownership(settings_factory):
    subdomain_repo = AsyncMock()
    project_repo = AsyncMock()
    deployments_repo = AsyncMock()

    domain = _domain(project_id="project-1", subdomain="my-app")
    subdomain_repo.get_by_subdomain.return_value = domain

    service = SubdomainService(
        subdomain_repo=subdomain_repo,
        project_repo=project_repo,
        deployments_repo=deployments_repo,
        config=settings_factory(),
    )

    admin_result = await service.get_subdomain_record(
        db=None,
        subdomain="  My-App  ",
        user_id="admin-user",
        is_admin=True,
    )

    project_repo.get_by_id_and_user.return_value = None
    denied_result = await service.get_subdomain_record(
        db=None,
        subdomain="my-app",
        user_id="other-user",
        is_admin=False,
    )

    project_repo.get_by_id_and_user.return_value = SimpleNamespace(id="project-1")
    owner_result = await service.get_subdomain_record(
        db=None,
        subdomain="my-app",
        user_id="owner-user",
        is_admin=False,
    )

    assert admin_result is domain
    assert denied_result is None
    assert owner_result is domain

    first_call = subdomain_repo.get_by_subdomain.await_args_list[0]
    assert first_call.args[1] == "my-app"
