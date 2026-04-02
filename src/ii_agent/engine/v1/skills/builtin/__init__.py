"""Builtin skills shipped with ii-agent."""

from pathlib import Path

from upath import UPath

BUILTIN_SKILLS_DIR = Path(__file__).parent


def get_builtin_skill_dirs() -> list[Path]:
    """Get list of builtin skill directories."""
    return [d for d in BUILTIN_SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]


def get_builtin_skill_upath(skill_name: str) -> UPath:
    """Get UPath for a builtin skill directory.

    Args:
        skill_name: Name of the skill (e.g., "pdf")

    Returns:
        UPath pointing to the skill directory
    """
    return UPath(BUILTIN_SKILLS_DIR / skill_name)
