"""Credit management service."""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import func, join, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.schemas import CreditBalance
from ii_agent.auth.users.models import User
from ii_agent.auth.users.repository import UserRepository

if TYPE_CHECKING:
    from ii_agent.billing.usage.repository import MetricsRepository

logger = logging.getLogger(__name__)


class CreditService:
    """Service for credit balance operations.

    All write methods use ``flush()`` only — the caller (FastAPI's
    ``DBSession`` dependency or ``get_db_session_local()``) is
    responsible for committing the transaction.
    """

    def __init__(
        self,
        *,
        user_repo: UserRepository,
        metrics_repo: Optional["MetricsRepository"] = None,
    ) -> None:
        self._user_repo = user_repo
        # Lazy-import default to avoid circular imports at module level
        if metrics_repo is None:
            from ii_agent.billing.usage.repository import MetricsRepository

            metrics_repo = MetricsRepository()
        self._metrics_repo = metrics_repo

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_balance(
        self, db: AsyncSession, user_id: str
    ) -> Optional[CreditBalance]:
        """Get the current credit balance for a user."""
        result = await db.execute(
            select(User.credits, User.bonus_credits, User.updated_at).where(
                User.id == user_id
            )
        )
        row = result.first()
        if not row:
            return None
        return CreditBalance(
            user_id=user_id,
            credits=row.credits,
            bonus_credits=row.bonus_credits,
            updated_at=row.updated_at,
        )

    async def has_sufficient(
        self, db: AsyncSession, user_id: str, amount: float
    ) -> bool:
        """Check if user has sufficient credits (regular + bonus) for *amount*."""
        balance = await self.get_balance(db, user_id)
        if not balance:
            return False
        return (balance.credits + balance.bonus_credits) >= amount

    # ------------------------------------------------------------------
    # Credit history
    # ------------------------------------------------------------------

    async def get_history(
        self, db: AsyncSession, user_id: str, *, page: int = 1, per_page: int = 20
    ) -> tuple[list[dict], int]:
        """Get paginated credit usage history for a user.

        Joins ``SessionMetrics`` with ``Session`` — these are imported
        lazily to avoid hard coupling at module level.
        """
        from ii_agent.sessions.models import Session
        from ii_agent.billing.usage.models import SessionMetrics

        base_query = (
            select(
                Session.id.label("session_id"),
                Session.name.label("session_title"),
                SessionMetrics.credits,
                SessionMetrics.updated_at,
            )
            .select_from(
                join(SessionMetrics, Session, SessionMetrics.session_id == Session.id)
            )
            .where(Session.user_id == user_id)
        )

        count_result = await db.execute(
            select(func.count())
            .select_from(
                join(SessionMetrics, Session, SessionMetrics.session_id == Session.id)
            )
            .where(Session.user_id == user_id)
        )
        total = count_result.scalar() or 0

        offset = (page - 1) * per_page
        result = await db.execute(
            base_query.order_by(SessionMetrics.updated_at.desc())
            .limit(per_page)
            .offset(offset)
        )

        history = [
            {
                "session_id": row.session_id,
                "session_title": row.session_title or "Untitled Session",
                "credits": row.credits,
                "updated_at": row.updated_at,
            }
            for row in result
        ]
        return history, total

    # ------------------------------------------------------------------
    # Mutations (no commit — caller manages the transaction)
    # ------------------------------------------------------------------

    async def deduct(
        self,
        db: AsyncSession,
        user_id: str,
        amount: float,
    ) -> bool:
        """Atomically deduct *amount* credits from a user.

        Bonus credits are consumed first; any remainder is taken from
        regular credits.  Returns ``False`` if insufficient balance or
        user not found.
        """
        try:
            updated = await self._user_repo.deduct_credits(db, user_id, amount)
            if updated:
                logger.info(
                    "Deducted %.4f credits from user %s. Balance: %.4f + %.4f bonus",
                    amount, user_id, updated[0], updated[1],
                )
                return True

            user = await self._user_repo.get_by_id(db, user_id)
            if not user:
                logger.error("User %s not found for credit deduction", user_id)
            else:
                total = user.credits + user.bonus_credits
                logger.warning(
                    "Insufficient credits for user %s: requested %.4f, available %.4f",
                    user_id, amount, total,
                )
            return False

        except SQLAlchemyError:
            logger.error("DB error deducting credits for %s", user_id, exc_info=True)
            raise

    async def add(
        self,
        db: AsyncSession,
        user_id: str,
        amount: float,
        *,
        is_bonus: bool = False,
    ) -> bool:
        """Atomically add *amount* credits to a user."""
        try:
            updated = await self._user_repo.add_credits(
                db, user_id, amount, is_bonus=is_bonus
            )
            if updated:
                logger.info(
                    "Added %.4f %s credits to user %s. Balance: %.4f + %.4f bonus",
                    amount, "bonus" if is_bonus else "regular",
                    user_id, updated[0], updated[1],
                )
                return True

            logger.error("User %s not found for credit addition", user_id)
            return False

        except SQLAlchemyError:
            logger.error("DB error adding credits for %s", user_id, exc_info=True)
            raise

    async def set_balance(
        self,
        db: AsyncSession,
        user_id: str,
        amount: float,
        *,
        bonus_amount: Optional[float] = None,
    ) -> bool:
        """Set a user's credit balance to exact amounts."""
        try:
            updated = await self._user_repo.set_credits(
                db, user_id, amount, bonus_amount=bonus_amount
            )
            if updated:
                logger.info(
                    "Set credits for user %s: %.4f + %.4f bonus",
                    user_id, updated[0], updated[1],
                )
                return True

            logger.error("User %s not found for set_balance", user_id)
            return False

        except SQLAlchemyError:
            logger.error("DB error setting credits for %s", user_id, exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Session usage tracking
    # ------------------------------------------------------------------

    async def accumulate_session_usage(
        self, db: AsyncSession, session_id: str, credits: float
    ) -> None:
        """Accumulate credits consumed for a session.

        Credits should be passed as **negative** values to represent
        consumption (the function uses ``+=``).
        """
        from datetime import datetime, timezone

        try:
            record = await self._metrics_repo.get_by_session_id(db, session_id)
            if record:
                record.credits += credits
                record.updated_at = datetime.now(timezone.utc)
            else:
                await self._metrics_repo.create(db, session_id, credits)
            logger.debug("Accumulated %.4f credits for session %s", credits, session_id)
        except Exception:
            logger.error(
                "Error accumulating session usage for %s", session_id, exc_info=True
            )
            raise

    async def get_session_usage(
        self, db: AsyncSession, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Return credit metrics for a session, or ``None``."""
        try:
            metrics = await self._metrics_repo.get_by_session_id(db, session_id)
            if metrics:
                return {
                    "session_id": metrics.session_id,
                    "credits": metrics.credits,
                    "created_at": metrics.created_at,
                    "updated_at": metrics.updated_at,
                }
            return None
        except Exception:
            logger.error(
                "Error getting session usage for %s", session_id, exc_info=True
            )
            raise

