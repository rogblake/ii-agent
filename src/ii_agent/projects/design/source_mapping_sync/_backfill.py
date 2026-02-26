"""Backfill strategies for source-mapping sync."""

from __future__ import annotations

import bisect
import re
from typing import Any, Dict, List, Optional

from ii_agent.core.logger import logger
from ii_agent.projects.design.schemas import ElementContext, StyleChange
from ii_agent.projects.design.source_mapping_sync._tag_utils import (
    _extract_opening_tag_name,
    _find_matching_closing_tag_end,
    _find_tag_end,
    _normalize_whitespace_for_match,
)
from ii_agent.projects.design.source_mapping_sync._workspace import (
    _normalize_react_source_file_name,
    _normalize_workspace_file_path,
    _parse_search_paths,
    _read_file_with_workspace_fallback,
    _score_source_path,
    _search_workspace_for_fixed_string,
)


def _extract_anchor_snippets(ctx: Optional[ElementContext]) -> List[str]:
    if not ctx:
        return []

    def _split_anchor_candidates(value: str) -> List[str]:
        """
        Turn iframe-captured text (often `innerText`) into source-searchable anchors.

        Important: container elements' `innerText` concatenates descendant texts that are separated
        by tags in source, so we must split into smaller, atomic snippets (lines/sentences).
        """
        if not isinstance(value, str):
            return []
        text = value.strip()
        if not text or text.lower() == "n/a":
            return []

        parts: List[str] = [p.strip() for p in re.split(r"[\r\n]+", text) if p.strip()]
        if not parts:
            parts = [text]

        # If it's still a single long run, also split by sentence-ish boundaries so we can match
        # contiguous substrings that likely exist as literals in source.
        if len(parts) == 1 and len(parts[0]) > 80:
            sentence_parts = [
                p.strip()
                for p in re.split(r"(?<=[.!?])\s+", parts[0])
                if p and p.strip()
            ]
            if len(sentence_parts) > 1:
                parts = sentence_parts

        return parts

    raw_candidates: List[str] = []
    for value in (
        ctx.textContent,
        ctx.nextSiblingText,
        ctx.prevSiblingText,
        ctx.contextText,
    ):
        for part in _split_anchor_candidates(value):
            raw_candidates.append(part[:120])
            if len(raw_candidates) >= 8:
                break
        if len(raw_candidates) >= 8:
            break

    deduped: List[str] = []
    seen: set[str] = set()
    for snippet in raw_candidates:
        if snippet in seen:
            continue
        seen.add(snippet)
        deduped.append(snippet)
    return deduped


def _find_best_opening_tag_by_class_tokens(
    *,
    content: str,
    class_name: str,
    class_tokens: List[str],
    preferred_tag_name: Optional[str],
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(class_name, str) or not class_name.strip():
        return None
    if not isinstance(class_tokens, list) or not class_tokens:
        return None

    normalized_class = " ".join(class_name.split())
    preferred = (preferred_tag_name or "").strip().lower() or None

    best: Optional[tuple[tuple[int, int, int, int, int], int, int]] = None
    for m in re.finditer(r"<[A-Za-z][A-Za-z0-9:_-]*", content):
        tag_start = m.start()
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None:
            continue
        tag = content[tag_start : tag_end + 1]

        if "className" not in tag and "class" not in tag:
            continue

        full_match = 1 if normalized_class and normalized_class in tag else 0
        token_matches = 0
        for token in class_tokens:
            if token and token in tag:
                token_matches += 1

        if full_match == 0 and token_matches < (1 if len(class_tokens) == 1 else 2):
            continue

        tag_name_match = 0
        if preferred:
            name_match = re.match(r"<\s*(?P<name>[A-Za-z][A-Za-z0-9:_-]*)", tag)
            if name_match and (name_match.group("name") or "").lower() == preferred:
                tag_name_match = 1

        # Prefer elements that do NOT already have a data-design-id; we don't want to steal IDs.
        has_existing_id = 1 if "data-design-id" in tag else 0

        score = (
            -full_match,
            -token_matches,
            has_existing_id,
            -tag_name_match,
            tag_start,
        )
        if best is None or score < best[0]:
            best = (score, tag_start, tag_end)

    if not best:
        return None
    return best[1], best[2]


def _split_class_tokens(class_name: str) -> List[str]:
    if not isinstance(class_name, str):
        return []
    tokens = [t.strip() for t in re.split(r"\s+", class_name.strip()) if t.strip()]
    deduped: List[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def _class_token_distinctiveness(token: str) -> int:
    if not isinstance(token, str):
        return 0
    score = len(token)
    if any(ch in token for ch in "/[]():#%"):
        score += 25
    if any(ch.isdigit() for ch in token):
        score += 6
    if token.startswith("data-") or token.startswith("aria-"):
        score += 12
    return score


def _upsert_data_design_id_attribute(tag: str, design_id: str) -> Optional[str]:
    if not isinstance(tag, str) or not isinstance(design_id, str) or not design_id:
        return None

    # If a design id already exists, only treat it as a match when it is the same id.
    # If it is a different id, do NOT overwrite (we likely matched the wrong element).
    existing_match = re.search(
        r"\bdata-design-id\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", tag
    )
    if existing_match:
        existing_val = (existing_match.group("val") or "").strip()
        if existing_val == design_id:
            return tag
        return None
    if "data-design-id" in tag:
        # Unknown/unsupported form like data-design-id={...}; do not overwrite.
        return None

    insert_at = None
    if tag.rstrip().endswith("/>"):
        insert_at = tag.rfind("/>")
    else:
        insert_at = tag.rfind(">")
    if insert_at is None or insert_at == -1:
        return None
    insertion = f' data-design-id="{design_id}"'
    return tag[:insert_at] + insertion + tag[insert_at:]


async def _backfill_design_id_in_source_from_class_name(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    ctx = change.elementContext
    if not ctx:
        return None

    class_name = None
    if isinstance(ctx.className, str) and ctx.className.strip():
        class_name = " ".join(ctx.className.split())
    elif isinstance(ctx.outerHTML, str) and ctx.outerHTML:
        match = re.search(
            r"\bclass\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", ctx.outerHTML
        )
        if match and match.group("val").strip():
            class_name = " ".join(match.group("val").strip().split())

    if not class_name:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill (className) skipped: missing className/outerHTML for designId=%s",
            design_id,
        )
        return None

    class_tokens = _split_class_tokens(class_name)
    if not class_tokens:
        return None

    anchors = _extract_anchor_snippets(ctx)

    search_out = await _search_workspace_for_fixed_string(sandbox, class_name)
    candidates = _parse_search_paths(search_out)
    if candidates:
        ranked = sorted(candidates, key=_score_source_path)
        best_path = ranked[0]
        logger.info(
            "[DesignMode Sync] (source-mapping) Backfill (className) exact match: designId=%s files=%d best=%s",
            design_id,
            len(ranked),
            best_path,
        )
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, best_path
            )
        except Exception:
            content = None
            resolved_path = None

        if (
            isinstance(content, str)
            and content
            and isinstance(resolved_path, str)
            and resolved_path
        ):
            bounds = _find_best_opening_tag_by_class_tokens(
                content=content,
                class_name=class_name,
                class_tokens=class_tokens,
                preferred_tag_name=ctx.tagName,
            )
            if bounds:
                tag_start, tag_end = bounds
                tag = content[tag_start : tag_end + 1]
                updated_tag = _upsert_data_design_id_attribute(tag, design_id)
                if updated_tag and updated_tag != tag:
                    return (
                        resolved_path,
                        content[:tag_start] + updated_tag + content[tag_end + 1 :],
                    )
                if updated_tag == tag:
                    return resolved_path, content

    ranked_tokens = sorted(class_tokens, key=_class_token_distinctiveness, reverse=True)
    tokens_to_search = ranked_tokens[: min(8, len(ranked_tokens))]

    file_hits: Dict[str, int] = {}
    for token in tokens_to_search:
        out = await _search_workspace_for_fixed_string(sandbox, token)
        for path in _parse_search_paths(out):
            file_hits[path] = file_hits.get(path, 0) + 1

    if not file_hits:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill (className) failed: no token matches in /workspace for designId=%s",
            design_id,
        )
        return None

    ranked_files = sorted(
        file_hits.items(),
        key=lambda kv: (-kv[1], _score_source_path(kv[0])),
    )

    best_content: Optional[str] = None
    best_path: Optional[str] = None
    best_anchor_hits = -1
    best_token_hits = -1

    for path, token_hit_count in ranked_files[:5]:
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, path
            )
        except Exception:
            continue
        if not isinstance(content, str) or not content:
            continue

        anchor_hits = 0
        for anchor in anchors:
            if anchor and anchor in content:
                anchor_hits += 1

        if (
            anchor_hits > best_anchor_hits
            or (anchor_hits == best_anchor_hits and token_hit_count > best_token_hits)
            or (
                anchor_hits == best_anchor_hits
                and token_hit_count == best_token_hits
                and best_path
                and _score_source_path(resolved_path) < _score_source_path(best_path)
            )
        ):
            best_content = content
            best_path = resolved_path
            best_anchor_hits = anchor_hits
            best_token_hits = token_hit_count

    if not best_content or not best_path:
        return None

    logger.info(
        "[DesignMode Sync] (source-mapping) Backfill (className) candidate: designId=%s file=%s tokens=%d anchors=%d",
        design_id,
        best_path,
        best_token_hits,
        best_anchor_hits,
    )

    bounds = _find_best_opening_tag_by_class_tokens(
        content=best_content,
        class_name=class_name,
        class_tokens=class_tokens,
        preferred_tag_name=ctx.tagName,
    )
    if not bounds:
        return None
    tag_start, tag_end = bounds
    tag = best_content[tag_start : tag_end + 1]
    updated_tag = _upsert_data_design_id_attribute(tag, design_id)
    if not updated_tag:
        return None
    if updated_tag == tag:
        return best_path, best_content
    return (
        best_path,
        best_content[:tag_start] + updated_tag + best_content[tag_end + 1 :],
    )


def _find_best_component_callsite_opening_tag(
    *,
    content: str,
    component_name: str,
    anchors: List[str],
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(component_name, str) or not component_name:
        return None

    normalized_anchors = [
        _normalize_whitespace_for_match(a) for a in anchors if isinstance(a, str) and a
    ]
    normalized_anchors = [a for a in normalized_anchors if a]
    if not normalized_anchors:
        return None

    # Match `<Component ...` with a word-ish boundary afterwards.
    pattern = re.compile(r"<\s*" + re.escape(component_name) + r"(?![A-Za-z0-9:_.-])")

    best: Optional[tuple[int, int, int]] = None  # (-anchor_hits, has_id, tag_start)
    best_bounds: Optional[tuple[int, int]] = None

    for match in pattern.finditer(content):
        tag_start = match.start()
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None:
            continue
        tag = content[tag_start : tag_end + 1]

        span_start = tag_start
        span_end = tag_end + 1
        if not tag.rstrip().endswith("/>"):
            closing_end = _find_matching_closing_tag_end(
                content, tag_end + 1, component_name
            )
            if closing_end is None:
                continue
            span_end = closing_end + 1

        window = _normalize_whitespace_for_match(content[span_start:span_end])
        anchor_hits = 0
        for anchor in normalized_anchors:
            if anchor in window:
                anchor_hits += 1

        if anchor_hits <= 0:
            continue

        has_existing_id = 1 if "data-design-id" in tag else 0
        score = (-anchor_hits, has_existing_id, tag_start)
        if best is None or score < best:
            best = score
            best_bounds = (tag_start, tag_end)

    return best_bounds


def _infer_component_name_before_index(content: str, index: int) -> Optional[str]:
    """
    Best-effort: infer the nearest React component name defined above `index`.

    This is used when a runtime element's className is defined inside a reusable component
    (e.g., shadcn/ui `CardHeader`), but the callsite doesn't include the className literal.
    """
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(index, int) or index <= 0:
        return None

    window_start = max(0, index - 3000)
    window = content[window_start:index]

    patterns = (
        r"(?:export\s+)?const\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*React\.forwardRef",
        r"(?:export\s+)?const\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*forwardRef",
        r"(?:export\s+)?function\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
    )

    candidates: List[tuple[int, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, window):
            name = (match.group("name") or "").strip()
            if not name:
                continue
            candidates.append((match.start(), name))

    if not candidates:
        return None
    # Choose the nearest definition above index.
    return max(candidates, key=lambda t: t[0])[1]


async def _backfill_design_id_in_source_from_component_callsite(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    """
    Backfill `data-design-id` into a React component callsite when the runtime element's className
    comes from a reusable component definition (so the className literal isn't present at the callsite).

    Example: `CardHeader` renders a `<div className="flex flex-col ...">` internally. We infer the
    component name from the className definition file, then locate the correct callsite by anchor text.
    """
    ctx = change.elementContext
    if not ctx:
        return None

    class_name = None
    if isinstance(ctx.className, str) and ctx.className.strip():
        class_name = " ".join(ctx.className.split())
    elif isinstance(ctx.outerHTML, str) and ctx.outerHTML:
        match = re.search(
            r"\bclass\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", ctx.outerHTML
        )
        if match and match.group("val").strip():
            class_name = " ".join(match.group("val").strip().split())

    anchors = _extract_anchor_snippets(ctx)
    if not class_name or not anchors:
        return None

    # 1) Find definition files that contain the className literal.
    search_out = await _search_workspace_for_fixed_string(sandbox, class_name)
    definition_paths = sorted(_parse_search_paths(search_out), key=_score_source_path)
    if not definition_paths:
        return None

    component_names: List[str] = []
    for def_path in definition_paths[:5]:
        try:
            definition_content, _resolved_def_path = (
                await _read_file_with_workspace_fallback(sandbox, def_path)
            )
        except Exception:
            continue
        if not isinstance(definition_content, str) or not definition_content:
            continue

        for match in re.finditer(re.escape(class_name), definition_content):
            inferred = _infer_component_name_before_index(
                definition_content, match.start()
            )
            if inferred and inferred not in component_names:
                component_names.append(inferred)
        if component_names:
            break

    if not component_names:
        return None

    # 2) Use anchor snippets to find the callsite file (where text literals exist).
    anchor_queries = sorted(anchors, key=lambda s: (-len(s or ""), s or ""))[:3]
    callsite_candidates: List[str] = []
    for anchor in anchor_queries:
        out = await _search_workspace_for_fixed_string(sandbox, anchor)
        callsite_candidates.extend(_parse_search_paths(out))

    # De-dupe while preserving order, then rank.
    deduped: List[str] = []
    seen: set[str] = set()
    for p in callsite_candidates:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    ranked_callsite_paths = sorted(deduped, key=_score_source_path)
    for path in ranked_callsite_paths[:8]:
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, path
            )
        except Exception:
            continue
        if not isinstance(content, str) or not content or not resolved_path:
            continue

        for component_name in component_names:
            if f"<{component_name}" not in content:
                continue
            bounds = _find_best_component_callsite_opening_tag(
                content=content, component_name=component_name, anchors=anchor_queries
            )
            if not bounds:
                continue
            tag_start, tag_end = bounds
            tag = content[tag_start : tag_end + 1]
            updated_tag = _upsert_data_design_id_attribute(tag, design_id)
            if not updated_tag:
                continue
            if updated_tag == tag:
                return resolved_path, content
            updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]
            logger.info(
                "[DesignMode Sync] (source-mapping) Backfill (callsite) inferred component=%s file=%s designId=%s",
                component_name,
                resolved_path,
                design_id,
            )
            return resolved_path, updated_content

    return None


def _build_line_start_offsets(content: str) -> List[int]:
    offsets = [0]
    if not isinstance(content, str) or not content:
        return offsets
    for i, ch in enumerate(content):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _pos_to_line_number(line_start_offsets: List[int], pos: int) -> int:
    # line numbers are 1-based
    if not line_start_offsets:
        return 1
    return bisect.bisect_right(line_start_offsets, pos)


def _find_best_opening_tag_near_source_location(
    *,
    content: str,
    line_no: int,
    column_no: Optional[int],
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(line_no, int) or line_no <= 0:
        return None

    line_offsets = _build_line_start_offsets(content)
    if line_no > len(line_offsets):
        return None

    base_pos = line_offsets[line_no - 1]
    if isinstance(column_no, int) and column_no > 0:
        base_pos = min(len(content) - 1, base_pos + (column_no - 1))

    window_chars = 8000
    window_start = max(0, base_pos - window_chars)
    window_end = min(len(content), base_pos + window_chars)
    window = content[window_start:window_end]

    best: Optional[tuple[int, int, int]] = None  # (score, tag_start, tag_end)
    for m in re.finditer(r"<[A-Za-z][A-Za-z0-9:_-]*", window):
        tag_start = window_start + m.start()
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None:
            continue
        cand_line = _pos_to_line_number(line_offsets, tag_start)
        line_dist = abs(cand_line - line_no)
        pos_dist = abs(tag_start - base_pos)
        score = line_dist * 100_000 + pos_dist
        if best is None or score < best[0]:
            best = (score, tag_start, tag_end)

    if not best:
        return None
    return best[1], best[2]


async def _backfill_design_id_in_source_from_react_source(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    ctx = change.elementContext
    if not ctx or not isinstance(ctx.reactSource, dict):
        return None

    raw_file = ctx.reactSource.get("fileName")
    normalized_file = _normalize_react_source_file_name(raw_file)
    if not normalized_file:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: missing/invalid reactSource.fileName=%r for designId=%s",
            raw_file,
            design_id,
        )
        return None

    normalized_path = _normalize_workspace_file_path(normalized_file)
    if not normalized_path:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: could not normalize reactSource file path %r for designId=%s",
            normalized_file,
            design_id,
        )
        return None

    line_no = None
    try:
        line_no = int(ctx.reactSource.get("lineNumber") or 0) or None
    except Exception:
        line_no = None
    if not line_no:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: missing reactSource.lineNumber for designId=%s",
            design_id,
        )
        return None

    column_no = None
    try:
        column_no = int(ctx.reactSource.get("columnNumber") or 0) or None
    except Exception:
        column_no = None

    try:
        content, resolved_path = await _read_file_with_workspace_fallback(
            sandbox, normalized_path
        )
    except Exception:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Backfill failed: could not read reactSource file %s (from %r) for designId=%s",
            normalized_path,
            raw_file,
            design_id,
        )
        return None

    if not isinstance(content, str) or not content:
        return None

    bounds = _find_best_opening_tag_near_source_location(
        content=content, line_no=line_no, column_no=column_no
    )
    if not bounds:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Backfill failed: could not locate JSX tag near %s:%s for designId=%s",
            resolved_path,
            line_no,
            design_id,
        )
        return None
    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]
    updated_tag = _upsert_data_design_id_attribute(tag, design_id)
    if not updated_tag:
        return None
    if updated_tag == tag:
        return resolved_path, content
    updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]
    return resolved_path, updated_content


async def _backfill_design_id_in_source_from_text_search(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    ctx = change.elementContext
    if not ctx or not isinstance(ctx.textContent, str):
        return None
    text = ctx.textContent.strip()
    if not text or text.upper() == "N/A":
        return None

    query = text[:80]
    search_out = await _search_workspace_for_fixed_string(sandbox, query)
    candidates = _parse_search_paths(search_out)
    if not candidates:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: text query not found in /workspace for designId=%s",
            design_id,
        )
        return None
    best_path = sorted(candidates, key=_score_source_path)[0]

    try:
        content, resolved_path = await _read_file_with_workspace_fallback(
            sandbox, best_path
        )
    except Exception:
        return None

    if not isinstance(content, str) or not content:
        return None

    idx = content.find(query)
    if idx == -1:
        return None

    search_pos = idx
    while True:
        tag_start = content.rfind("<", 0, search_pos + 1)
        if tag_start == -1:
            return None
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            search_pos = tag_start - 1
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None or tag_end >= idx:
            search_pos = tag_start - 1
            continue
        tag = content[tag_start : tag_end + 1]
        updated_tag = _upsert_data_design_id_attribute(tag, design_id)
        if not updated_tag:
            return None
        if updated_tag == tag:
            return resolved_path, content
        updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]
        return resolved_path, updated_content
