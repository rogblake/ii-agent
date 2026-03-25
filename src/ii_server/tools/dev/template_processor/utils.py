from pathlib import Path


def get_ii_server_root() -> Path:
    """Return the ii_server package root."""
    return Path(__file__).resolve().parents[3]


def get_templates_dir() -> Path:
    """Return the packaged templates directory for dev project scaffolding."""
    templates_dir = get_ii_server_root() / "assets" / "templates"
    if not templates_dir.is_dir():
        raise FileNotFoundError(f"Templates directory not found: {templates_dir}")
    return templates_dir
