"""Helpers for translating A2A RequestContext metadata into ii-agent inputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

from a2a.server.agent_execution.context import RequestContext

from ii_agent.integrations.a2a.constants import (
    METADATA_ROOT_KEYS,
    SANDBOX_KEYS,
    TOOL_ARGS_KEYS,
    USER_KEYS,
)

logger = logging.getLogger(__name__)


@dataclass
class SandboxPreferences:
    """Sandbox reuse and lifecycle hints provided by the caller."""

    reuse: bool = False
    timeout_seconds: Optional[int] = None
    template_id: Optional[str] = None
    sandbox_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserAuth:
    """External credentials that may be required to service the request."""

    user_id: Optional[str] = None
    api_key: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class A2ARequestPayload:
    """Normalized payload that ii-agent downstream components can consume."""

    tool_args: Dict[str, Any] = field(default_factory=dict)
    sandbox: SandboxPreferences = field(default_factory=SandboxPreferences)
    user: UserAuth = field(default_factory=UserAuth)
    metadata: Dict[str, Any] = field(default_factory=dict)
    configuration: Dict[str, Any] = field(default_factory=dict)


def extract_request_payload(context: RequestContext) -> A2ARequestPayload:
    """Convert A2A RequestContext into a structured payload.

    The extractor looks at (in order):
        1. Top-level RequestContext metadata
        2. Message-level metadata
        3. Individual message part metadata
        4. Message content field as a fallback (when metadata absent)

    The caller can provide an ``"ii-agent"`` section containing:
        - ``tool_args``: forwarded to ii-agent tool configuration
        - ``sandbox``: preferences for sandbox reuse/timeout/template
        - ``user``: credential hints for sandbox auth or downstream services

    Args:
        context: Incoming request context from the A2A SDK.

    Returns:
        A normalized ``A2ARequestPayload`` instance.
    """

    aggregated_metadata: Dict[str, Any] = {}
    for candidate in _iter_metadata_candidates(context):
        _deep_merge(aggregated_metadata, candidate)

    payload_section = _pick_first_key(aggregated_metadata, METADATA_ROOT_KEYS)
    if payload_section is None:
        payload_section = {}
    elif not isinstance(payload_section, Mapping):
        logger.warning(
            "Unexpected metadata format for ii-agent payload: %s", type(payload_section)
        )
        payload_section = {}

    tool_args = _extract_mapping(payload_section, TOOL_ARGS_KEYS)
    sandbox_section = _extract_mapping(payload_section, SANDBOX_KEYS)
    user_section = _extract_mapping(payload_section, USER_KEYS)

    sandbox = SandboxPreferences(
        reuse=_as_bool(sandbox_section.pop("reuse", False)),
        timeout_seconds=_as_int(sandbox_section.pop("timeout", None)),
        template_id=_as_str(sandbox_section.pop("template_id", None))
        or _as_str(sandbox_section.pop("templateId", None)),
        sandbox_id=_as_str(sandbox_section.pop("sandbox_id", None))
        or _as_str(sandbox_section.pop("sandboxId", None)),
        extra=dict(sandbox_section),
    )

    user = UserAuth(
        user_id=_as_str(user_section.pop("user_id", None))
        or _as_str(user_section.pop("id", None)),
        api_key=_as_str(user_section.pop("api_key", None))
        or _as_str(user_section.pop("apiKey", None)),
        extra=dict(user_section),
    )

    configuration = _safe_model_dump(context.configuration)

    payload = A2ARequestPayload(
        tool_args=dict(tool_args),
        sandbox=sandbox,
        user=user,
        metadata=aggregated_metadata,
        configuration=configuration,
    )

    if payload.user.user_id:
        logger.info(
            "A2A payload resolved user_id from metadata: %s",
            payload.user.user_id,
        )
    else:
        logger.debug("A2A payload missing user_id override in metadata.")

    return payload


def _iter_metadata_candidates(context: RequestContext):
    """Yield metadata dictionaries in priority order."""
    if context.metadata:
        yield context.metadata

    message = context.message
    if not message:
        return

    if getattr(message, "metadata", None):
        yield message.metadata  # type: ignore[attr-defined]

    for part in getattr(message, "parts", []) or []:
        meta = getattr(part, "metadata", None)
        if meta:
            yield meta

    # fallback: when no metadata provided, allow message.content if dict-like
    content = getattr(message, "content", None)
    if isinstance(content, Mapping):
        yield content


def _pick_first_key(data: Mapping[str, Any], keys) -> Optional[Mapping[str, Any]]:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _extract_mapping(source: Mapping[str, Any], keys) -> Dict[str, Any]:
    """Extract a nested mapping (if present) under any alias provided."""
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _deep_merge(target: Dict[str, Any], source: Mapping[str, Any]) -> None:
    """Recursively merge ``source`` into ``target``."""
    for key, value in source.items():
        if (
            key in target
            and isinstance(target[key], Mapping)
            and isinstance(value, Mapping)
        ):
            _deep_merge(target[key], value)  # type: ignore[arg-type]
        else:
            target[key] = value


def _safe_model_dump(model: Any) -> Dict[str, Any]:
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return dict(model.model_dump())
    if hasattr(model, "dict"):
        return dict(model.dict())  # type: ignore[call-arg]
    if isinstance(model, Mapping):
        return dict(model)
    return {}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return bool(value)


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:  # pragma: no cover - defensive
        return None
