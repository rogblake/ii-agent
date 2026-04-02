"""Utility functions for media domain."""

from pathlib import Path

import yaml


def load_yaml_config(path: Path) -> dict:
    """Load a YAML configuration file.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r") as f:
        return yaml.safe_load(f)
