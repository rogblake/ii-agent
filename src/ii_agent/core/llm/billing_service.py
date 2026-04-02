"""Centralised LLM billing — single path for agent and chat credit deductions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.pricing import ModelPricing
from ii_agent.core.llm.token_record import TokenRecord

if TYPE_CHECKING:
    from ii_agent.billing.credits.service import CreditService
    from ii_agent.core.config.settings import Settings

logger = logging.getLogger(__name__)

# 100 credits = $1.5 USD  →  1 USD = 100/1.5 credits ≈ 66.67
USD_TO_CREDITS_MULTIPLIER = 100 / 1.5


class LLMBillingService:
    """Calculate token costs, deduct credits, and record session usage."""

    def __init__(
        self,
        *,
        credit_service: CreditService,
        config: Settings,
    ) -> None:
        self._credit_service = credit_service
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def deduct_for_llm_usage(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        session_id: str,
        token_record: TokenRecord,
        is_user_model: bool = False,
    ) -> float:
        """Deduct credits for an LLM call.

        Returns the number of credits charged (0.0 when skipped).
        """
        if is_user_model:
            logger.debug(
                "Skipping billing for user-provided model, session=%s", session_id
            )
            return 0.0

        pricing = ModelPricing.get_default_pricing(token_record.model_id)
        credits = self._calculate(token_record, pricing)

        if credits <= 0:
            return 0.0

        await self._credit_service.deduct(db, user_id, credits)
        await self._credit_service.accumulate_session_usage(
            db, session_id, -credits  # negative = consumption
        )

        logger.info(
            "Deducted %.4f credits for model %s (user=%s, session=%s) — "
            "in=%d out=%d cr=%d cw=%d direct_cost=%.6f",
            credits,
            token_record.model_id,
            user_id,
            session_id,
            token_record.input_tokens,
            token_record.output_tokens,
            token_record.cache_read_tokens,
            token_record.cache_write_tokens,
            token_record.direct_cost,
        )
        return credits

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate(record: TokenRecord, pricing: ModelPricing) -> float:
        """Pure math — USD cost converted to credits.

        Mirrors the formula in ``engine/v1/utils/credit.py``.
        """
        input_cost = (
            record.input_tokens / 1_000_000
        ) * pricing.input_price_per_million

        output_cost = (
            record.output_tokens / 1_000_000
        ) * pricing.output_price_per_million

        cache_write_cost = (
            record.cache_write_tokens / 1_000_000
        ) * pricing.cache_write_price_per_million

        cache_read_cost = (
            record.cache_read_tokens / 1_000_000
        ) * pricing.cache_read_price_per_million

        total_usd = (
            input_cost + output_cost + cache_write_cost
            + cache_read_cost + record.direct_cost
        )

        return total_usd * USD_TO_CREDITS_MULTIPLIER / 1.5
