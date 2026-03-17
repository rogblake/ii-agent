"""Database base utilities.

This module provides core database infrastructure.
Models should be imported directly from their domain modules.

Import pattern:
    # For base utilities
    from ii_agent.core.db import Base, TimestampColumn

    # For session context manager
    from ii_agent.core.db.manager import get_db_session_local

    # For models - import from domain modules
    from ii_agent.sessions import Session
    from ii_agent.billing import BillingTransaction
    from ii_agent.auth.users.models import User
"""

from ii_agent.core.db.base import Base, TimestampColumn, get_session_factory
from ii_agent.core.db.repository import BaseRepository

__all__ = [
    "Base",
    "BaseRepository",
    "TimestampColumn",
    "get_session_factory",
]
