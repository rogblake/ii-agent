"""Constants and static asset loading for the design domain."""

from __future__ import annotations

from pathlib import Path

from ii_agent.core.logger import logger

SCRIPT_ASSETS_DIR = Path(__file__).parent / "assets"
EDITABLE_CLASS_NAMES = {"editable", "editable-img", "editing"}


def _load_html_asset(asset_name: str) -> str:
    asset_path = SCRIPT_ASSETS_DIR / asset_name
    try:
        return asset_path.read_text()
    except OSError as exc:
        logger.warning("[DesignMode] Unable to read asset %s: %s", asset_path, exc)
        return ""


DESIGN_MODE_GOOGLE_FONTS = _load_html_asset("design_fonts.html")
DESIGN_MODE_RUNTIME_SCRIPT = _load_html_asset("design_script.html")
