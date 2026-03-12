"""Subdomain management API endpoints.

These endpoints allow users to check availability and select
subdomains on your platform's domain (e.g., *.iiapp.dev).

Uses Cloudflare KV for subdomain routing instead of DNS CNAME records.
"""

from fastapi import APIRouter, Query

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.core.exceptions import IIAgentError, PermissionDeniedError, ValidationError
from ii_agent.core.logger import logger
from ii_agent.projects.exceptions import ProjectNotFoundError
from ii_agent.projects.subdomains.exceptions import SubdomainNotFoundError, SubdomainServiceUnavailableError
from ii_agent.projects.subdomains.dependencies import (
    BaseDomainDep,
    CloudflareKVServiceDep,
    SubdomainServiceDep,
)
from ii_agent.projects.subdomains.schemas import (
    CheckAvailabilityRequest,
    CheckAvailabilityResponse,
    ClaimSubdomainRequest,
    ClaimSubdomainResponse,
    ReservedSubdomainsResponse,
    SubdomainListResponse,
    SubdomainResponse,
)
from ii_agent.projects.subdomains.utils import RESERVED_SUBDOMAINS, SubdomainResult

router = APIRouter(prefix="/subdomains", tags=["Subdomains"])


@router.post("/check-availability", response_model=CheckAvailabilityResponse)
async def check_subdomain_availability(
    request: CheckAvailabilityRequest,
    current_user: CurrentUser,
    kv_service: CloudflareKVServiceDep,
    base_domain: BaseDomainDep,
) -> CheckAvailabilityResponse:
    """Check if a subdomain is available."""
    subdomain = request.subdomain.lower().strip()

    try:
        is_available, error = await kv_service.check_availability(subdomain)

        response = CheckAvailabilityResponse(
            subdomain=subdomain,
            available=is_available,
            full_domain=f"{subdomain}.{base_domain}" if is_available else None,
            error=error,
        )

        # If not available, suggest alternatives
        if not is_available and "taken" in (error or "").lower():
            suggestions = []
            for i in range(1, 4):
                alt = f"{subdomain}{i}"
                alt_available, _ = await kv_service.check_availability(alt)
                if alt_available:
                    suggestions.append(f"{alt}.{base_domain}")
                if len(suggestions) >= 3:
                    break

            for prefix in ["my", "the", "app"]:
                if len(suggestions) >= 3:
                    break
                alt = f"{prefix}-{subdomain}"
                alt_available, _ = await kv_service.check_availability(alt)
                if alt_available:
                    suggestions.append(f"{alt}.{base_domain}")

            response.suggestions = suggestions if suggestions else None

        return response

    except IIAgentError:
        raise
    except Exception as e:
        logger.exception(f"Failed to check subdomain availability: {subdomain}")
        raise SubdomainServiceUnavailableError(f"Failed to check availability: {str(e)}") from e
    finally:
        await kv_service.close()


@router.post("/claim", response_model=ClaimSubdomainResponse)
async def claim_subdomain(
    request: ClaimSubdomainRequest,
    current_user: CurrentUser,
    subdomain_service: SubdomainServiceDep,
    kv_service: CloudflareKVServiceDep,
    base_domain: BaseDomainDep,
    db: DBSession,
) -> ClaimSubdomainResponse:
    """Claim a custom subdomain for a deployed project.

    Fetches the Cloud Run URL from the project's deployment metadata,
    writes a KV entry for the Worker to route, and stores the custom
    domain in the project_custom_domains table.
    """
    subdomain = request.subdomain.lower().strip()
    project_id = request.project_id

    # Verify ownership
    project = await subdomain_service.get_user_project(db, project_id, str(current_user.id))
    if not project:
        raise ProjectNotFoundError("Project not found or you don't have access to it")

    # Get cloud_run_url from the latest deployment
    cloud_run_url = await subdomain_service.get_cloud_run_url(db, project_id)
    if not cloud_run_url:
        raise ValidationError(
            "Custom subdomains are only available for Cloud Run deployments. "
            "Please deploy your project to Cloud Run first."
        )

    try:
        # Check if project already has a custom domain
        existing = await subdomain_service.get_custom_domain_by_subdomain(db, subdomain)
        old_subdomain = None
        existing_for_project = await subdomain_service._subdomain_repo.get_by_project_id(
            db, project_id
        )
        if existing_for_project:
            old_subdomain = existing_for_project.subdomain
            if old_subdomain == subdomain:
                old_subdomain = None

        # Check availability
        is_available, error = await kv_service.check_availability(subdomain)
        if not is_available:
            return ClaimSubdomainResponse(
                success=False,
                subdomain=subdomain,
                error=error or f"Subdomain '{subdomain}' is not available",
            )

        # Create the subdomain route in KV
        result = await kv_service.create_subdomain(
            subdomain=subdomain,
            cloud_run_url=cloud_run_url,
            project_id=project_id,
            user_id=str(current_user.id),
        )

        if not result.success:
            return ClaimSubdomainResponse(
                success=False,
                subdomain=subdomain,
                error=result.error,
            )

        # Release old subdomain after successfully claiming the new one
        if old_subdomain:
            logger.info(
                f"Releasing old subdomain '{old_subdomain}' for project {project_id}"
            )
            try:
                await kv_service.delete_subdomain(old_subdomain)
            except Exception as delete_error:
                logger.warning(
                    f"Failed to release old subdomain '{old_subdomain}': {delete_error}"
                )

        full_domain_url = f"https://{subdomain}.{base_domain}"

        # Store custom domain in project_custom_domains table
        await subdomain_service.create_or_update_custom_domain(
            db,
            project_id=project_id,
            user_id=str(current_user.id),
            subdomain=subdomain,
            full_domain=full_domain_url,
            cloudflare_record_id=getattr(result, "record_id", None),
        )

        return ClaimSubdomainResponse(
            success=True,
            subdomain=subdomain,
            full_domain=f"{subdomain}.{base_domain}",
            production_url=full_domain_url,
        )

    except IIAgentError:
        raise
    except Exception as e:
        logger.exception(f"Failed to claim subdomain: {subdomain}")
        raise SubdomainServiceUnavailableError(f"Failed to claim subdomain: {str(e)}") from e
    finally:
        await kv_service.close()


@router.get("/reserved", response_model=ReservedSubdomainsResponse)
async def get_reserved_subdomains(
    current_user: CurrentUser,
) -> ReservedSubdomainsResponse:
    """Get list of reserved subdomains that cannot be used."""
    return ReservedSubdomainsResponse(
        reserved=sorted(list(RESERVED_SUBDOMAINS))
    )


@router.get("/base-domain/info")
async def get_base_domain_info(
    current_user: CurrentUser,
    base_domain: BaseDomainDep,
) -> dict:
    """Get information about the base domain."""
    return {
        "base_domain": base_domain,
        "example": f"myapp.{base_domain}",
    }


@router.get("/{subdomain}", response_model=SubdomainResponse)
async def get_subdomain(
    subdomain: str,
    current_user: CurrentUser,
    subdomain_service: SubdomainServiceDep,
    kv_service: CloudflareKVServiceDep,
    db: DBSession,
) -> SubdomainResponse:
    """Get details of a subdomain."""
    subdomain = subdomain.lower().strip()
    is_admin = getattr(current_user, "role", None) == "admin"

    if not is_admin:
        record = await subdomain_service.get_subdomain_record(
            db, subdomain, user_id=str(current_user.id)
        )
        if not record:
            raise SubdomainNotFoundError("Subdomain not found")

    try:
        result: SubdomainResult = await kv_service.get_subdomain(subdomain)
        return SubdomainResponse(
            success=result.success,
            subdomain=result.subdomain,
            full_domain=result.full_domain,
            status=result.status.value if result.status else None,
            cloud_run_url=result.cloud_run_url,
            error=result.error,
        )

    except IIAgentError:
        raise
    except Exception as e:
        logger.exception(f"Failed to get subdomain: {subdomain}")
        raise SubdomainServiceUnavailableError(f"Failed to get subdomain: {str(e)}") from e
    finally:
        await kv_service.close()


@router.delete("/{subdomain}", response_model=SubdomainResponse)
async def delete_subdomain(
    subdomain: str,
    current_user: CurrentUser,
    subdomain_service: SubdomainServiceDep,
    kv_service: CloudflareKVServiceDep,
    db: DBSession,
) -> SubdomainResponse:
    """Delete a subdomain.

    Note: This removes the KV entry. The Cloud Run service is not affected.
    """
    subdomain = subdomain.lower().strip()
    is_admin = getattr(current_user, "role", None) == "admin"

    record = await subdomain_service.get_subdomain_record(
        db, subdomain, user_id=str(current_user.id), is_admin=is_admin
    )
    if not is_admin and not record:
        raise SubdomainNotFoundError("Subdomain not found")

    try:
        result: SubdomainResult = await kv_service.delete_subdomain(subdomain)

        if result.success and record:
            owner_user_id = str(current_user.id)
            if is_admin:
                owner_user_id = (
                    await subdomain_service.get_project_owner_user_id(db, record.project_id)
                    or owner_user_id
                )

            await subdomain_service.delete_custom_domain(
                db,
                project_id=record.project_id,
                user_id=owner_user_id,
            )

        return SubdomainResponse(
            success=result.success,
            subdomain=result.subdomain,
            full_domain=result.full_domain,
            status=result.status.value if result.status else None,
            cloud_run_url=result.cloud_run_url,
            error=result.error,
        )

    except IIAgentError:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete subdomain: {subdomain}")
        raise SubdomainServiceUnavailableError(f"Failed to delete subdomain: {str(e)}") from e
    finally:
        await kv_service.close()


@router.get("", response_model=SubdomainListResponse)
async def list_subdomains(
    current_user: CurrentUser,
    kv_service: CloudflareKVServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
) -> SubdomainListResponse:
    """List all subdomains (admin only)."""
    if getattr(current_user, "role", None) != "admin":
        raise PermissionDeniedError("Admin access required")

    try:
        subdomains, total = await kv_service.list_subdomains(page, per_page)

        return SubdomainListResponse(
            success=True,
            subdomains=[
                SubdomainResponse(
                    success=s.success,
                    subdomain=s.subdomain,
                    full_domain=s.full_domain,
                    status=s.status.value if s.status else None,
                    cloud_run_url=s.cloud_run_url,
                    error=s.error,
                )
                for s in subdomains
            ],
            total=total,
            page=page,
            per_page=per_page,
        )

    except IIAgentError:
        raise
    except Exception as e:
        logger.exception("Failed to list subdomains")
        raise SubdomainServiceUnavailableError(f"Failed to list subdomains: {str(e)}") from e
    finally:
        await kv_service.close()
