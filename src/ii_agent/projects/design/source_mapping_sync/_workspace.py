"""Workspace/file utilities for source-mapping sync."""

from __future__ import annotations

import posixpath
import re
import shlex
from typing import Any, List, Optional
from urllib.parse import urlparse

from ii_agent.core.logger import logger


def _normalize_workspace_file_path(file_path: str) -> Optional[str]:
    """
    Normalize a potentially workspace-relative path into an absolute sandbox path.

    Design Mode sync is expected to only modify files under `/workspace`.
    """
    if not isinstance(file_path, str):
        return None

    path = file_path.strip()
    if not path:
        return None

    # Strip trivial wrappers from LLMs.
    if len(path) >= 2 and path[0] == path[-1] and path[0] in {"`", '"', "'"}:
        path = path[1:-1].strip()

    path = path.replace("\\", "/")
    if path.startswith("file://"):
        path = path[len("file://"):]
    if path.startswith("workspace/"):
        path = f"/{path}"
    elif path == "workspace":
        path = "/workspace"

    if not path:
        return None

    if path.startswith("/workspace/"):
        normalized = posixpath.normpath(path)
    elif path.startswith("/"):
        # Keep Design Mode sync safely scoped to workspace.
        logger.warning(
            "[DesignMode Sync] Rejecting non-workspace absolute path: %s", path
        )
        return None
    else:
        normalized = posixpath.normpath(posixpath.join("/workspace", path))

    if normalized == "/workspace":
        logger.warning("[DesignMode Sync] Rejecting workspace root path: %s", file_path)
        return None

    if not normalized.startswith("/workspace/"):
        logger.warning(
            "[DesignMode Sync] Rejecting path escaping workspace: %s -> %s",
            file_path,
            normalized,
        )
        return None

    return normalized


def _normalize_workspace_path(file_path: str) -> Optional[str]:
    return _normalize_workspace_file_path(file_path)


def _normalize_react_source_file_name(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None

    value = value.split("#", 1)[0].split("?", 1)[0]

    # Handle fileName values that look like URLs.
    if "://" in value:
        try:
            value = urlparse(value).path or value
        except Exception:
            pass

    value = value.replace("\\", "/")

    # Handle webpack style: webpack:///./src/App.tsx
    if value.startswith("webpack://"):
        value = value[len("webpack://"):]

    value = value.lstrip("/")
    if value.startswith("./"):
        value = value[2:]

    # If the path is absolute but not under /workspace, salvage a src-relative suffix.
    # This commonly happens when devtools report an absolute host path.
    if (
        value.startswith("Users/")
        or value.startswith("home/")
        or value.startswith("var/")
    ):
        match = re.search(r"(?P<suffix>src/.*)$", value)
        if match:
            value = match.group("suffix")
        else:
            return None

    if not value:
        return None
    return value


def _workspace_relative_path(normalized_workspace_path: str) -> Optional[str]:
    if not isinstance(normalized_workspace_path, str):
        return None
    path = normalized_workspace_path.strip()
    if not path.startswith("/workspace/"):
        return None
    rel = path[len("/workspace/"):]
    if not rel or rel.startswith("/"):
        return None
    rel = posixpath.normpath(rel)
    if rel.startswith("../") or rel == "..":
        return None
    return rel


async def _get_workspace_top_level_dirs(sandbox: Any) -> List[str]:
    """
    List top-level directories directly under `/workspace` (cached per sandbox object).

    These are used both for prompting (so the model can return absolute paths) and
    for resolving workspace-relative paths.
    """
    cache_key = "design_mode_workspace_roots"
    cached = getattr(sandbox, cache_key, None)
    if isinstance(cached, list) and all(isinstance(item, str) for item in cached):
        return cached

    roots: List[str] = []
    try:
        roots_out = await sandbox.run_command(
            "find /workspace -maxdepth 1 -mindepth 1 -type d -print"
        )
        roots = [
            line.strip() for line in (roots_out or "").splitlines() if line.strip()
        ]
    except Exception:
        roots = []

    ignored_basenames = {
        ".git",
        "node_modules",
        "__pycache__",
        ".cache",
        ".next",
        "dist",
        "build",
    }
    filtered: List[str] = []
    for root in roots:
        base = posixpath.basename(root.rstrip("/"))
        if base in ignored_basenames:
            continue
        if not root.startswith("/workspace/"):
            continue
        filtered.append(root)

    filtered.sort()
    try:
        setattr(sandbox, cache_key, filtered)
    except Exception:
        pass
    return filtered


async def _read_file_with_workspace_fallback(
    sandbox: Any, normalized_workspace_path: str
) -> tuple[str, str]:
    """
    Read a file from the sandbox, with fallbacks for projects nested under `/workspace/<project>/...`.

    Returns:
        (content, resolved_path)
    """
    last_error: Optional[Exception] = None

    def _coerce_text(content: Any) -> Optional[str]:
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if isinstance(content, (bytes, bytearray)):
            try:
                return bytes(content).decode("utf-8")
            except Exception:
                return None
        return None

    # 1) Direct read.
    try:
        content = await sandbox.read_file(normalized_workspace_path)
        text = _coerce_text(content)
        if text is not None:
            return text, normalized_workspace_path
    except Exception as exc:
        last_error = exc

    relative_path = _workspace_relative_path(normalized_workspace_path)
    if not relative_path:
        if last_error:
            raise last_error
        raise FileNotFoundError(normalized_workspace_path)

    # 2) Try `/workspace/*/<relative_path>` for each top-level directory.
    for root in await _get_workspace_top_level_dirs(sandbox):
        candidate = posixpath.normpath(posixpath.join(root, relative_path))
        if not candidate.startswith("/workspace/"):
            continue
        try:
            content = await sandbox.read_file(candidate)
            text = _coerce_text(content)
            if text is not None:
                return text, candidate
        except Exception as exc:
            last_error = exc

    # 3) Fallback: `find` by suffix anywhere in /workspace (excluding heavy dirs).
    try:
        pattern = f"*/{relative_path}"
        find_cmd = (
            "find /workspace -type f "
            "-not -path '*/node_modules/*' "
            "-not -path '*/.git/*' "
            "-not -path '*/dist/*' "
            "-not -path '*/build/*' "
            "-not -path '*/.next/*' "
            f"-path {shlex.quote(pattern)} "
            "-print -quit"
        )
        found = (await sandbox.run_command(find_cmd) or "").strip()
        if found:
            content = await sandbox.read_file(found)
            text = _coerce_text(content)
            if text is not None:
                return text, found
    except Exception as exc:
        last_error = exc

    if last_error:
        raise last_error
    raise FileNotFoundError(normalized_workspace_path)


def _score_source_path(path: str) -> tuple[int, int, int]:
    lowered = (path or "").lower()
    ext_rank = 9
    for ext, rank in (
        (".tsx", 0),
        (".jsx", 1),
        (".ts", 2),
        (".js", 3),
        (".html", 4),
        (".css", 5),
        (".vue", 6),
        (".svelte", 7),
    ):
        if lowered.endswith(ext):
            ext_rank = rank
            break
    in_src = 0 if "/src/" in lowered else 1
    return (ext_rank, in_src, len(path))


async def _search_workspace_for_fixed_string(sandbox: Any, query: str) -> str:
    quoted = shlex.quote(query)
    cmd = (
        "if command -v rg >/dev/null 2>&1; then "
        f"rg --no-heading -n -F --hidden "
        "--glob '!**/node_modules/**' "
        "--glob '!**/.git/**' "
        "--glob '!**/dist/**' "
        "--glob '!**/build/**' "
        "--glob '!**/.next/**' "
        f"{quoted} /workspace | head -n 50; "
        "else "
        "grep -R -n -F "
        "--exclude-dir=node_modules "
        "--exclude-dir=.git "
        "--exclude-dir=dist "
        "--exclude-dir=build "
        "--exclude-dir=.next "
        f"-e {quoted} /workspace | head -n 50; "
        "fi"
    )
    try:
        return await sandbox.run_command(cmd) or ""
    except Exception:
        return ""


def _parse_search_paths(output: str) -> List[str]:
    paths: List[str] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(?P<path>/[^:]+):(?P<line>\d+):", line)
        if not match:
            continue
        path = match.group("path").strip()
        if not path:
            continue
        paths.append(path)
    # De-dupe while preserving order.
    deduped: List[str] = []
    seen: set[str] = set()
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)
    return deduped


def _score_globals_css_candidate(path: str) -> int:
    lowered = (path or "").lower()
    if lowered.endswith("/src/app/globals.css"):
        return 0
    if lowered.endswith("/app/globals.css"):
        return 1
    if lowered.endswith("/src/styles/globals.css"):
        return 2
    if lowered.endswith("/styles/globals.css"):
        return 3
    return 9
