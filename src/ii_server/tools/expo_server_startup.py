"""Shared Expo startup helpers for mobile development tools."""

import asyncio
import re
from typing import Any, Dict

from ii_server.tools.shell.terminal_manager import BaseShellManager

DEFAULT_MAX_ATTEMPTS = 20
DEFAULT_POLL_INTERVAL_SECONDS = 1.5

_ERROR_PATTERNS = [
    r"AssertionError.*ERR_ASSERTION",
    r"TypeError:.*",
    r"SyntaxError:.*",
    r"Cannot find module",
    r"Module not found",
    r"ENOENT",
    r"EACCES",
    r"Command failed",
    r"fatal:",
    r"CommandError:",
    r"Error: .{10,}",
]

_READY_MARKERS = [
    "Metro waiting on",
    "Tunnel ready",
    "Web is waiting on",
    "Waiting on http://",
    "Logs for your project will appear below",
]


def _extract_last_tunnel_url(output_text: str) -> str | None:
    matches = re.findall(r"exp://[^\s\]\)]+", output_text)
    if not matches:
        return None
    return matches[-1].rstrip(")")


def _extract_last_web_url(output_text: str) -> str | None:
    matches = re.findall(
        r"https?://(?:localhost|127\.0\.0\.1|\d{1,3}(?:\.\d{1,3}){3}):\d+",
        output_text,
    )
    if not matches:
        return None
    return matches[-1]


def _extract_error_context(output_text: str) -> str | None:
    for pattern in _ERROR_PATTERNS:
        match = re.search(pattern, output_text, re.IGNORECASE)
        if not match:
            continue

        context_start = max(0, match.start() - 100)
        context_end = min(len(output_text), match.end() + 500)
        return output_text[context_start:context_end].strip()
    return None


def _is_ready(output_text: str) -> bool:
    return any(marker in output_text for marker in _READY_MARKERS)


def _format_startup_error(startup_mode: str, error_context: str) -> str:
    return (
        f"Expo server failed to start in {startup_mode} mode:\n\n"
        f"```\n{error_context}\n```"
    )


def _format_timeout_error(
    startup_mode: str,
    output_text: str,
    max_attempts: int,
    poll_interval_seconds: float,
) -> str:
    max_wait_seconds = int(max_attempts * poll_interval_seconds)
    return (
        f"Expo server failed to start in {startup_mode} mode "
        f"(no startup URL found after {max_wait_seconds} seconds).\n\n"
        f"Terminal output:\n```\n{output_text[-1000:]}\n```"
    )


async def _poll_expo_startup(
    *,
    terminal_manager: BaseShellManager,
    session_name: str,
    startup_mode: str,
    require_tunnel_url: bool,
    max_attempts: int,
    poll_interval_seconds: float,
) -> Dict[str, Any]:
    latest_output = ""

    for _ in range(max_attempts):
        await asyncio.sleep(poll_interval_seconds)

        output = terminal_manager.get_session_output(session_name)
        output_text = output.clean_output if hasattr(output, "clean_output") else str(output)
        latest_output = output_text

        error_context = _extract_error_context(output_text)
        if error_context:
            return {
                "success": False,
                "error": _format_startup_error(startup_mode, error_context),
            }

        tunnel_url = _extract_last_tunnel_url(output_text)
        web_url = _extract_last_web_url(output_text)

        if require_tunnel_url:
            if tunnel_url and _is_ready(output_text):
                return {
                    "success": True,
                    "tunnel_url": tunnel_url,
                    "qr_code_value": tunnel_url,
                    "web_url": web_url,
                }
        else:
            if web_url and (_is_ready(output_text) or "Starting Metro Bundler" in output_text):
                return {
                    "success": True,
                    "tunnel_url": None,
                    "qr_code_value": tunnel_url,
                    "web_url": web_url,
                }

    return {
        "success": False,
        "error": _format_timeout_error(startup_mode, latest_output, max_attempts, poll_interval_seconds),
    }


def _stop_running_command(terminal_manager: BaseShellManager, session_name: str) -> None:
    try:
        terminal_manager.kill_current_command(session_name)
    except Exception:
        pass


async def start_expo_dev_server(
    *,
    terminal_manager: BaseShellManager,
    project_dir: str,
    logger: Any,
    session_name: str = "mobile",
    fallback_to_lan: bool = True,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> Dict[str, Any]:
    """Start Expo dev server, with automatic tunnel-to-LAN fallback."""
    attempts = [("tunnel", "EXPO_FORCE_WEBCONTAINER_ENV=1 bunx expo start --tunnel --web", True)]
    if fallback_to_lan:
        attempts.append(("lan", "bunx expo start --lan --web", False))

    errors: list[str] = []

    for index, (startup_mode, command, require_tunnel_url) in enumerate(attempts):
        try:
            terminal_manager.run_command(
                session_name,
                command,
                run_dir=project_dir,
                wait_for_output=False,
            )
        except Exception as exc:
            errors.append(f"[{startup_mode}] {exc}")
            continue

        result = await _poll_expo_startup(
            terminal_manager=terminal_manager,
            session_name=session_name,
            startup_mode=startup_mode,
            require_tunnel_url=require_tunnel_url,
            max_attempts=max_attempts,
            poll_interval_seconds=poll_interval_seconds,
        )

        if result.get("success"):
            result["startup_mode"] = startup_mode
            if startup_mode == "lan":
                result["warning"] = (
                    "Tunnel mode was unavailable, so Expo started in LAN mode. "
                    "QR code access works only from devices on the same network."
                )
            return result

        errors.append(f"[{startup_mode}] {result.get('error', 'Unknown error')}")

        has_next_attempt = index + 1 < len(attempts)
        should_fallback = startup_mode == "tunnel" and has_next_attempt

        if should_fallback:
            logger.warning(
                "Expo tunnel start failed; retrying in LAN mode. Error: %s",
                result.get("error", "Unknown error"),
            )
            _stop_running_command(terminal_manager, session_name)
            await asyncio.sleep(1)

    if not errors:
        errors.append("Unknown Expo startup error")

    return {"success": False, "error": "\n\n".join(errors)}
