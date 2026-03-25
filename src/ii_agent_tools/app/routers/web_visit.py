from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ii_agent_tools.app.deps import get_web_visit_service, verify_api_key
from ii_agent_tools.integrations.web_visit.base import WebVisitServiceType
from ii_agent_tools.logger import get_logger

router = APIRouter(tags=["web-visit"])
logger = get_logger(__name__)


class BaseRequest(BaseModel):
    pass


class WebVisitRequest(BaseRequest):
    url: str = Field(..., max_length=2048, description="URL to visit")
    prompt: str | None = Field(
        None, max_length=1000, description="Optional prompt for content extraction"
    )
    service_type: WebVisitServiceType | None = Field(
        None,
        description="Optional web visit service type (defaults to firecrawl)",
    )

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v: str) -> str:
        """Validate URL scheme is HTTP or HTTPS."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Only HTTP and HTTPS URLs are allowed")
        return v


class WebVisitResponse(BaseModel):
    success: bool
    content: str | None = None
    error: str | None = None
    cost: float | None = None


@router.post("/web-visit", response_model=WebVisitResponse)
async def web_visit(
    request: WebVisitRequest,
    auth: dict = Depends(verify_api_key),
    visit_service=Depends(get_web_visit_service),
):
    """Visit a web page and extract content."""
    try:
        result = await visit_service.visit(
            request.url, request.prompt, request.service_type
        )
    except Exception:
        logger.exception(
            "Failed to visit web page",
            extra={
                "url": request.url,
                "prompt_present": bool(request.prompt),
                "service_type": request.service_type,
            },
        )
        raise HTTPException(status_code=500, detail="Failed to visit web page")
    response = WebVisitResponse(success=True, content=result.content, cost=result.cost)
    return response


class ResearcherVisitRequest(BaseRequest):
    urls: List[str] = Field(
        ..., min_length=1, max_length=10, description="List of URLs to visit"
    )
    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Research query for content extraction",
    )

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, v: List[str]) -> List[str]:
        """Validate that all URLs have HTTP or HTTPS scheme."""
        for url in v:
            if not url.startswith(("http://", "https://")):
                raise ValueError(
                    f"Invalid URL scheme: {url}. Only HTTP and HTTPS URLs are allowed"
                )
        return v


class ResearcherVisitResponse(BaseModel):
    success: bool
    error: str | None
    content: str
    cost: float | None = None


@router.post("/researcher-web-visit", response_model=ResearcherVisitResponse)
async def researcher_web_visit(
    request: ResearcherVisitRequest,
    auth: dict = Depends(verify_api_key),
    visit_service=Depends(get_web_visit_service),
):
    """Visit web pages and extract content for a researcher query."""
    try:
        logger.info("Using batch visit with normal search")
        result = await visit_service.batch_visit(request.urls, request.query)
    except Exception:
        logger.exception(
            "Failed to visit web pages for researcher visit",
            extra={"urls_count": len(request.urls)},
        )
        raise HTTPException(status_code=500, detail="Failed to visit web pages")
    response = ResearcherVisitResponse(
        content=result.content, success=True, error=None, cost=result.cost
    )
    return response
