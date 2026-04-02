from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ii_agent_tools.app.deps import get_web_search_service, verify_api_key
from ii_agent_tools.integrations.web_search.base import WebSearchServiceType
from ii_agent_tools.integrations.web_search.exception import (
    WebSearchExhaustedError,
    WebSearchNetworkError,
    WebSearchProviderError,
)
from ii_agent_tools.logger import get_logger

router = APIRouter(tags=["web-search"])
logger = get_logger(__name__)


class BaseRequest(BaseModel):
    pass


class WebSearchRequest(BaseRequest):
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    max_results: int = Field(
        default=5, ge=1, le=50, description="Maximum number of results to return"
    )
    service_type: WebSearchServiceType | None = Field(
        None,
        description="Optional web search service type (defaults to serpapi)",
    )


class WebSearchResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]] | None = None
    error: str | None = None
    cost: float | None = None


@router.post("/web-search", response_model=WebSearchResponse)
async def web_search(
    request: WebSearchRequest,
    auth: dict = Depends(verify_api_key),
    search_service=Depends(get_web_search_service),
):
    """Perform web search using configured providers."""
    try:
        result = await search_service.search(
            request.query, request.max_results, request.service_type
        )
        response = WebSearchResponse(success=True, results=result.result, cost=result.cost)

        return response
    except WebSearchExhaustedError as e:
        logger.error(str(e))
        raise HTTPException(status_code=429, detail=str(e))
    except (WebSearchNetworkError, WebSearchProviderError) as e:
        logger.error(str(e))
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected error in web search: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class WebBatchSearchRequest(BaseRequest):
    queries: List[str] = Field(
        ..., min_length=1, max_length=10, description="List of search queries"
    )
    max_results: int = Field(
        default=6, ge=1, le=50, description="Maximum number of results per query"
    )
    service_type: WebSearchServiceType | None = Field(
        None,
        description="Optional web search service type (defaults to serpapi)",
    )


class WebBatchSearchResponse(BaseModel):
    success: bool
    results: List[List[Dict[str, Any]]] | None = None
    error: str | None = None
    cost: float | None = None


@router.post("/web-batch-search", response_model=WebBatchSearchResponse)
async def web_batch_search(
    request: WebBatchSearchRequest,
    auth: dict = Depends(verify_api_key),
    search_service=Depends(get_web_search_service),
):
    """Perform web search using configured providers."""
    try:
        results = await search_service.batch_search(
            request.queries, request.max_results, request.service_type
        )
        response = WebBatchSearchResponse(
            success=True,
            results=[result.result for result in results],
            cost=sum([result.cost for result in results]),
        )
        return response
    except WebSearchExhaustedError as e:
        logger.error(str(e))
        raise HTTPException(status_code=429, detail=str(e))
    except (WebSearchNetworkError, WebSearchProviderError) as e:
        logger.error(str(e))
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected error in web search: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
