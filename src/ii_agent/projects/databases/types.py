"""Database domain enums."""

from enum import StrEnum


class DatabaseSource(StrEnum):
    """Source/provider of a project database."""

    NEONDB = "neondb"
    USER = "user"
    SUPABASE = "supabase"
