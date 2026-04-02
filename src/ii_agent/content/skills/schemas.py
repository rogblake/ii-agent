"""Pydantic schemas (DTOs) for skills domain."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class GitHubSkillRequest(BaseModel):
    """Request to add a skill from GitHub URL."""

    github_url: str = Field(
        ...,
        description="GitHub URL to skill folder containing SKILL.md",
        json_schema_extra={
            "examples": [
                "https://github.com/anthropics/skills/tree/main/skills/brand-guidelines"
            ]
        },
    )


class SkillToggleRequest(BaseModel):
    """Request to toggle skill enabled state."""

    is_enabled: bool = Field(..., description="Whether the skill should be enabled")


class SkillInfo(BaseModel):
    """Skill information response."""

    id: str = Field(..., description="Unique skill ID")
    name: str = Field(..., description="Skill name (kebab-case)")
    description: str = Field(..., description="What the skill does")
    source: str = Field(
        ..., description="Skill source type: 'builtin', 'github', or 'custom'"
    )
    source_url: Optional[str] = Field(
        None, description="GitHub URL for github-sourced skills"
    )
    is_enabled: bool = Field(..., description="Whether the skill is enabled")
    license: Optional[str] = Field(None, description="License information")
    compatibility: Optional[str] = Field(None, description="Compatibility information")
    created_at: datetime = Field(..., description="When the skill was added")
    updated_at: Optional[datetime] = Field(None, description="When the skill was last updated")

    class Config:
        from_attributes = True


class SkillList(BaseModel):
    """List of skills response."""

    skills: List[SkillInfo] = Field(..., description="List of skills")
    builtin_count: int = Field(..., description="Number of built-in skills")
    custom_count: int = Field(..., description="Number of custom skills")


class SkillDeleteResponse(BaseModel):
    """Response for skill deletion."""

    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Status message")
