"""Skill loader for reading and syncing skills."""

from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.settings.skills.models import Skill, SkillSource
from ii_agent.agents.skills.builtin import get_builtin_skill_dirs
from ii_agent.agents.skills.skills_ref.parser import read_properties
from ii_agent.core.logger import logger

# Sandbox path template
SANDBOX_SKILLS_PATH = "/workspace/.skills"


def load_builtin_skills() -> list[dict]:
    """Load builtin skills from the codebase folder.

    Reads both:
    - SKILL.md content for fast prompt generation (stored in DB)
    - Directory path for sandbox loading on activation (storage_uri)

    Returns:
        List of skill dicts with properties, skill_md_content, and storage_uri.
    """
    skills = []

    for skill_dir in get_builtin_skill_dirs():
        try:
            props = read_properties(skill_dir)

            # Read SKILL.md content for DB storage (fast prompt generation)
            skill_md_path = skill_dir / "SKILL.md"
            skill_md_content = skill_md_path.read_text()

            # For builtin skills, use a relative URI pattern that can be resolved at runtime
            # This avoids storing absolute paths which don't work in distributed environments
            # IMPORTANT: Use the directory name (skill_dir.name), NOT props.name
            # The directory name is the actual folder in the filesystem (e.g., "expo-api-routes")
            # while props.name is the logical skill name from SKILL.md (e.g., "api-routes")
            storage_uri = f"builtin:{skill_dir.name}"

            skills.append(
                {
                    "name": props.name,
                    "description": props.description,
                    "skill_md_content": skill_md_content,  # For fast prompt generation
                    "license": props.license,
                    "compatibility": props.compatibility,
                    "allowed_tools": (props.allowed_tools.split() if props.allowed_tools else []),
                    "sandbox_path": f"{SANDBOX_SKILLS_PATH}/{props.name}",
                    "storage_uri": storage_uri,  # Resolved at runtime for builtin skills
                    "source": SkillSource.BUILTIN.value,
                }
            )
            logger.debug(f"Loaded builtin skill: {props.name}")
        except Exception as e:
            logger.error(f"Failed to load builtin skill from {skill_dir}: {e}")

    logger.info(f"Loaded {len(skills)} builtin skill metadata entries")
    return skills


async def sync_builtin_to_db(db: AsyncSession) -> int:
    """Sync builtin skills metadata from codebase to database.

    Uses upsert to update existing or insert new builtin skills.
    Only syncs skills where user_id is NULL (builtin).

    Args:
        db: Database session

    Returns:
        Number of skills synced
    """
    builtin_skills = load_builtin_skills()

    for skill_data in builtin_skills:
        # Use PostgreSQL upsert (INSERT ... ON CONFLICT)
        stmt = insert(Skill).values(
            user_id=None,  # Builtin skills have no user
            name=skill_data["name"],
            description=skill_data["description"],
            skill_md_content=skill_data["skill_md_content"],  # For fast prompt generation
            source=skill_data["source"],
            sandbox_path=skill_data["sandbox_path"],
            storage_uri=skill_data["storage_uri"],
            license=skill_data.get("license"),
            compatibility=skill_data.get("compatibility"),
            allowed_tools=skill_data.get("allowed_tools", []),
            is_enabled=True,
        )

        # On conflict on the partial index for builtin skills (user_id IS NULL)
        # Use index_elements with index_where for partial unique index
        stmt = stmt.on_conflict_do_update(
            index_elements=["name"],
            index_where=Skill.user_id.is_(None),
            set_={
                "description": skill_data["description"],
                "skill_md_content": skill_data["skill_md_content"],
                "sandbox_path": skill_data["sandbox_path"],
                "storage_uri": skill_data["storage_uri"],
                "license": skill_data.get("license"),
                "compatibility": skill_data.get("compatibility"),
                "allowed_tools": skill_data.get("allowed_tools", []),
            },
        )

        await db.execute(stmt)

    await db.commit()
    logger.info(f"Synced {len(builtin_skills)} builtin skills to database")
    return len(builtin_skills)


async def get_user_skills(db: AsyncSession, user_id: str, enabled_only: bool = True) -> list[Skill]:
    """Get skills available to a user, with user skills overriding builtins.

    IMPORTANT: Merge logic must happen BEFORE filtering by is_enabled.
    This ensures that if a user has disabled a builtin skill (via an override),
    the disabled override takes precedence over the enabled builtin.

    Args:
        db: Database session
        user_id: User ID
        enabled_only: Only return enabled skills

    Returns:
        List of Skill objects (builtin + user, with user overriding builtin by name)
    """
    # Query ALL builtin and user skills first (don't filter by is_enabled yet)
    query = select(Skill).where(
        or_(
            Skill.user_id.is_(None),  # Builtin skills
            Skill.user_id == user_id,  # User's own skills
        )
    )

    result = await db.execute(query)
    all_skills = result.scalars().all()

    # Merge: user skills override builtin by name
    builtin_skills = {s.name: s for s in all_skills if s.user_id is None}
    user_skills = {s.name: s for s in all_skills if s.user_id == user_id}

    # User skills take precedence (this includes user overrides for builtin skills)
    merged = {**builtin_skills, **user_skills}

    # NOW filter by is_enabled if requested
    if enabled_only:
        merged = {name: skill for name, skill in merged.items() if skill.is_enabled}

    logger.info(f"Loaded {len(merged)} skills for user {user_id} (enabled_only={enabled_only})")

    return list(merged.values())


async def get_skill_by_name(db: AsyncSession, user_id: str, skill_name: str) -> Optional[Skill]:
    """Get a specific skill by name, preferring user's version over builtin.

    IMPORTANT: If user has an override for a builtin skill (e.g., to disable it),
    the user's version takes precedence. If the override is disabled, return None.

    Args:
        db: Database session
        user_id: User ID
        skill_name: Skill name to find

    Returns:
        Skill object or None if not found or disabled
    """
    # First check if user has an override for this skill
    result = await db.execute(
        select(Skill).where(
            Skill.user_id == user_id,
            Skill.name == skill_name,
        )
    )
    user_skill = result.scalar_one_or_none()

    if user_skill:
        # User has a skill/override - check if it's enabled
        if user_skill.is_enabled:
            return user_skill
        else:
            # User has explicitly disabled this skill
            logger.info(f"Skill '{skill_name}' is disabled by user")
            return None

    # No user override - fall back to builtin
    result = await db.execute(
        select(Skill).where(
            Skill.user_id.is_(None),
            Skill.name == skill_name,
            Skill.is_enabled == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()
