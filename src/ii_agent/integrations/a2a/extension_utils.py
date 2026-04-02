"""Shared helpers for A2A extension metadata handling."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set


def append_extension_issue(
    extension_info: Optional[Dict[str, Any]],
    *,
    uri: str,
    code: str,
    detail: Optional[str] = None,
) -> None:
    """Attach a diagnostic entry describing extension negotiation problems."""

    if extension_info is None:
        return

    issues = extension_info.setdefault("issues", [])
    if not isinstance(issues, list):
        issues = []
        extension_info["issues"] = issues

    record: Dict[str, Any] = {"uri": uri, "code": code}
    if detail:
        record["detail"] = detail
    issues.append(record)


def collect_requested_extensions(context: Any) -> set[str]:
    """Gather requested extension URIs from both headers and message payload."""

    extensions: Set[str] = set()

    call_context = getattr(context, "call_context", None)
    requested = (
        getattr(call_context, "requested_extensions", None)
        if call_context is not None
        else None
    )
    _accumulate_extensions(extensions, requested)

    message = getattr(context, "message", None)
    message_extensions = getattr(message, "extensions", None)
    _accumulate_extensions(extensions, message_extensions)

    return extensions


def _accumulate_extensions(bucket: Set[str], values: Any) -> None:
    if not values:
        return

    iterable: Iterable[Any]
    if isinstance(values, (set, list, tuple)):
        iterable = values
    else:
        try:
            iterable = list(values)
        except TypeError:
            return

    for item in iterable:
        if not isinstance(item, (str, int, float)):
            continue
        value = str(item).strip()
        if value:
            bucket.add(value)
