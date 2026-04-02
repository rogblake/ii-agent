"""Repository layer for users domain - data access only."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import case, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.auth.users.models import APIKey, User


class UserRepository:
    """Data access layer for User model."""

    async def get_by_id(self, db: AsyncSession, user_id: str) -> Optional[User]:
        """Get a user by their ID."""
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """Get a user by their email (case-insensitive)."""
        result = await db.execute(
            select(User).where(func.lower(User.email) == email.lower())
        )
        return result.scalar_one_or_none()

    async def lookup_by_customer_id(self, db: AsyncSession, customer_id: str) -> Optional[str]:
        """Look up a user ID by their Stripe customer ID."""
        result = await db.execute(
            select(User.id).where(User.stripe_customer_id == customer_id)
        )
        row = result.first()
        return row[0] if row else None

    async def create(
        self,
        db: AsyncSession,
        *,
        email: str,
        first_name: str = "",
        last_name: str = "",
        avatar: Optional[str] = None,
        email_verified: bool = False,
        credits: float = 0.0,
        bonus_credits: float = 0.0,
        subscription_plan: Optional[str] = None,
        login_provider: Optional[str] = None,
    ) -> User:
        """Create a new user and persist it."""
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            first_name=first_name,
            last_name=last_name,
            avatar=avatar,
            role="user",
            is_active=True,
            email_verified=email_verified,
            credits=credits,
            bonus_credits=bonus_credits,
            last_login_at=datetime.now(timezone.utc),
            subscription_plan=subscription_plan,
            login_provider=login_provider,
        )
        db.add(user)
        await db.flush()
        return user

    async def update_fields(self, db: AsyncSession, user: User, **fields: Any) -> None:
        """Update arbitrary fields on a user and flush changes."""
        for key, value in fields.items():
            if value is not None:
                setattr(user, key, value)
        await db.flush()

    async def update_profile(
        self,
        db: AsyncSession,
        user: User,
        *,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        avatar: Optional[str] = None,
        email_verified: Optional[bool] = None,
        login_provider: Optional[str] = None,
    ) -> None:
        """Update user profile fields (only non-None values are applied)."""
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if avatar is not None:
            user.avatar = avatar
        if email_verified is not None:
            user.email_verified = user.email_verified or email_verified
        if login_provider is not None:
            user.login_provider = login_provider
        user.last_login_at = datetime.now(timezone.utc)
        await db.flush()

    async def update_subscription(
        self,
        db: AsyncSession,
        user: User,
        *,
        subscription_plan: Optional[str] = None,
        subscription_status: Optional[str] = None,
        subscription_billing_cycle: Optional[str] = ...,
        stripe_customer_id: Optional[str] = None,
        subscription_current_period_end: Optional[datetime] = None,
        credits: Optional[float] = None,
    ) -> None:
        """Update subscription-related fields on a user.

        Uses sentinel default ``...`` for ``subscription_billing_cycle`` so that
        callers can explicitly pass ``None`` to clear the value.
        """
        if subscription_plan is not None:
            user.subscription_plan = subscription_plan
        if subscription_status is not None:
            user.subscription_status = subscription_status
        if subscription_billing_cycle is not ...:
            user.subscription_billing_cycle = subscription_billing_cycle
        if stripe_customer_id is not None:
            user.stripe_customer_id = stripe_customer_id
        if subscription_current_period_end is not None:
            user.subscription_current_period_end = subscription_current_period_end
        if credits is not None:
            user.credits = credits
        await db.flush()

    async def set_active(self, db: AsyncSession, user: User, *, is_active: bool) -> None:
        """Activate or deactivate a user account."""
        user.is_active = is_active
        await db.flush()

    async def set_language(self, db: AsyncSession, user: User, language: str) -> None:
        """Update the user's preferred language."""
        user.language = language
        await db.flush()

    # ------------------------------------------------------------------
    # Credit operations (atomic SQL to prevent race conditions)
    # ------------------------------------------------------------------

    async def deduct_credits(
        self, db: AsyncSession, user_id: str, amount: float
    ) -> tuple[float, float] | None:
        """Atomically deduct credits (bonus first, then regular).

        Returns ``(credits, bonus_credits)`` after deduction, or ``None``
        if the user was not found or had insufficient balance.
        """
        result = await db.execute(
            update(User)
            .where(
                (User.id == user_id)
                & ((User.credits + User.bonus_credits) >= amount)
            )
            .values(
                bonus_credits=case(
                    (User.bonus_credits >= amount, User.bonus_credits - amount),
                    else_=0.0,
                ),
                credits=case(
                    (User.bonus_credits >= amount, User.credits),
                    else_=User.credits - (amount - User.bonus_credits),
                ),
                updated_at=datetime.now(timezone.utc),
            )
            .returning(User.credits, User.bonus_credits)
        )
        row = result.first()
        return (row.credits, row.bonus_credits) if row else None

    async def add_credits(
        self, db: AsyncSession, user_id: str, amount: float, *, is_bonus: bool = False
    ) -> tuple[float, float] | None:
        """Atomically add credits to a user.

        Returns ``(credits, bonus_credits)`` after addition, or ``None``
        if the user was not found.
        """
        if is_bonus:
            values: dict[str, Any] = {
                "bonus_credits": User.bonus_credits + amount,
                "updated_at": datetime.now(timezone.utc),
            }
        else:
            values = {
                "credits": User.credits + amount,
                "updated_at": datetime.now(timezone.utc),
            }

        result = await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(**values)
            .returning(User.credits, User.bonus_credits)
        )
        row = result.first()
        return (row.credits, row.bonus_credits) if row else None

    async def set_credits(
        self,
        db: AsyncSession,
        user_id: str,
        amount: float,
        *,
        bonus_amount: float | None = None,
    ) -> tuple[float, float] | None:
        """Set a user's credit balance to exact amounts.

        Returns ``(credits, bonus_credits)`` after update, or ``None``
        if the user was not found.
        """
        values: dict[str, Any] = {
            "credits": amount,
            "updated_at": datetime.now(timezone.utc),
        }
        if bonus_amount is not None:
            values["bonus_credits"] = bonus_amount

        result = await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(**values)
            .returning(User.credits, User.bonus_credits)
        )
        row = result.first()
        return (row.credits, row.bonus_credits) if row else None


class APIKeyRepository:
    """Data access layer for APIKey model."""

    async def get_active_for_user(self, db: AsyncSession, user_id: str) -> Optional[str]:
        """Get the active API key string for a user.

        Returns the most recently created active API key, or None.
        """
        result = await db.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id, APIKey.is_active)
            .order_by(desc(APIKey.created_at))
        )
        api_key_obj = result.scalar_one_or_none()
        return api_key_obj.api_key if api_key_obj else None

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        api_key: str,
    ) -> APIKey:
        """Create a new API key for a user."""
        key = APIKey(
            id=str(uuid.uuid4()),
            user_id=user_id,
            api_key=api_key,
            is_active=True,
        )
        db.add(key)
        await db.flush()
        return key
