from fastapi import APIRouter
from .test import router as test_agent_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(test_agent_router)
