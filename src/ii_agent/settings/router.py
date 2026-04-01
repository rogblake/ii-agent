"""Parent router for user settings (LLM, MCP, Skills)."""

from fastapi import APIRouter

from ii_agent.settings.llm.router import router as llm_router
from ii_agent.settings.mcp.router import router as mcp_router
from ii_agent.settings.skills.router import router as skills_router

router = APIRouter(prefix="/user-settings", tags=["User Settings"])
router.include_router(llm_router)
router.include_router(mcp_router)
router.include_router(skills_router)
