"""API routes for skills domain."""

import logging

from fastapi import APIRouter, Query

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.content.skills.dependencies import SkillServiceDep
from ii_agent.content.skills.exceptions import SkillNotFoundError
from ii_agent.content.skills.schemas import (
    GitHubSkillRequest,
    SkillToggleRequest,
    SkillInfo,
    SkillList,
    SkillDeleteResponse,
)
from ii_agent.core.exceptions import ValidationError as CoreValidationError
from ii_agent.core.storage.client import storage
from ii_agent.engine.v1.skills.github import GitHubSkillError
from ii_agent.engine.v1.skills.skills_ref.errors import ParseError, ValidationError

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/user-settings/skills", tags=["User Skills Management"])


@router.post("/github", response_model=SkillInfo, status_code=201)
async def add_github_skill(
    request: GitHubSkillRequest,
    current_user: CurrentUser,
    service: SkillServiceDep,
    db: DBSession,
):
    """Add a skill from a GitHub URL."""
    try:
        return await service.add_skill_from_github(
            db,
            user_id=str(current_user.id),
            github_url=request.github_url,
            storage=storage,
            github_token=None,
        )
    except (GitHubSkillError, ParseError, ValidationError) as e:
        raise CoreValidationError(str(e)) from e


@router.get("", response_model=SkillList)
async def list_user_skills(
    current_user: CurrentUser,
    service: SkillServiceDep,
    db: DBSession,
    include_builtin: bool = Query(
        default=True,
        description="Whether to include built-in skills in the list",
    ),
):
    """List all skills available to the user."""
    return await service.list_skills(
        db,
        user_id=str(current_user.id),
        include_builtin=include_builtin,
    )


@router.get("/{skill_id}", response_model=SkillInfo)
async def get_skill_by_id(
    skill_id: str,
    current_user: CurrentUser,
    service: SkillServiceDep,
    db: DBSession,
):
    """Get details of a specific skill by ID."""
    skill_info = await service.get_skill(
        db,
        skill_id=skill_id,
        user_id=str(current_user.id),
    )

    if not skill_info:
        raise SkillNotFoundError("Skill not found")

    return skill_info


@router.patch("/{skill_id}/toggle", response_model=SkillInfo)
async def toggle_skill_enabled(
    skill_id: str,
    request: SkillToggleRequest,
    current_user: CurrentUser,
    service: SkillServiceDep,
    db: DBSession,
):
    """Enable or disable a skill."""
    try:
        skill_info = await service.toggle_skill(
            db,
            skill_id=skill_id,
            user_id=str(current_user.id),
            is_enabled=request.is_enabled,
        )

        if not skill_info:
            raise SkillNotFoundError("Skill not found")

        return skill_info

    except ValueError as e:
        raise CoreValidationError(str(e)) from e


@router.delete("/{skill_id}", response_model=SkillDeleteResponse)
async def delete_user_skill(
    skill_id: str,
    current_user: CurrentUser,
    service: SkillServiceDep,
    db: DBSession,
):
    """Delete a custom skill."""
    success = await service.delete_skill(
        db,
        skill_id=skill_id,
        user_id=str(current_user.id),
        storage=storage,
    )

    if not success:
        raise SkillNotFoundError("Skill not found")

    return SkillDeleteResponse(
        success=True,
        message="Skill deleted successfully",
    )
