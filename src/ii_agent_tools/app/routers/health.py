"""Health check endpoints for liveness and readiness probes."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from ii_agent_tools.app.deps import get_storage, get_llm_client
from ii_agent_tools.logger import get_logger
from ii_agent_tools.storage import BaseStorage
from ii_agent_tools.llm import LLMClient

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health")
async def health_check_liveness():
    """
    Liveness probe - is the application running?

    This is a simple check that the application is alive and can respond to requests.
    Used by container orchestrators (Kubernetes, etc.) to determine if the app needs to be restarted.

    Returns:
        200 OK if the application is running
    """
    return {"status": "ok"}


@router.get("/health/readiness")
async def health_check_readiness(
    storage: BaseStorage = Depends(get_storage),
    llm_client: LLMClient | None = Depends(get_llm_client),
):
    """
    Readiness probe - is the application ready to serve traffic?

    This checks that all critical dependencies are healthy and the app can handle requests.
    Used by container orchestrators and load balancers to determine if the app should receive traffic.

    Returns:
        200 OK if all dependencies are healthy
        503 Service Unavailable if any critical dependency is unhealthy
    """
    checks = {}
    all_healthy = True

    # Check storage
    try:
        # Try to access storage client - if it's configured and accessible
        if storage:
            checks["storage"] = "healthy"
        else:
            checks["storage"] = "not configured"
    except Exception as e:
        logger.error(f"Storage health check failed: {e}")
        checks["storage"] = f"unhealthy: {str(e)}"
        all_healthy = False

    # Check LLM client (optional dependency)
    try:
        if llm_client:
            checks["llm"] = "healthy"
        else:
            checks["llm"] = "not configured"
    except Exception as e:
        logger.warning(f"LLM health check failed: {e}")
        checks["llm"] = f"unhealthy: {str(e)}"
        # LLM is optional, so don't mark as unhealthy
        # all_healthy = False

    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={"status": "healthy" if all_healthy else "unhealthy", "checks": checks},
    )
