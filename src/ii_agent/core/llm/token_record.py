"""Unified token record for LLM billing across agent and chat paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ii_agent.engine.v1.models.metrics import Metrics
    from ii_agent.billing.usage.models import TokenUsage


@dataclass(frozen=True)
class TokenRecord:
    """Provider-agnostic snapshot of token consumption for one LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    model_id: str = ""
    direct_cost: float = 0.0


class TokenTracker:
    """Factory methods that normalise different source formats into TokenRecord."""

    @staticmethod
    def from_agent_metrics(metrics: Metrics, model_id: str) -> TokenRecord:
        """Create a TokenRecord from a v1 engine ``Metrics`` dataclass."""
        return TokenRecord(
            input_tokens=metrics.input_tokens,
            output_tokens=metrics.output_tokens,
            cache_read_tokens=metrics.cache_read_tokens,
            cache_write_tokens=metrics.cache_write_tokens,
            reasoning_tokens=metrics.reasoning_tokens,
            model_id=model_id,
            direct_cost=metrics.cost or 0.0,
        )

    @staticmethod
    def from_chat_usage(usage: TokenUsage) -> TokenRecord:
        """Create a TokenRecord from a chat ``TokenUsage`` Pydantic model."""
        return TokenRecord(
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            reasoning_tokens=0,
            model_id=usage.model_name or "",
        )
