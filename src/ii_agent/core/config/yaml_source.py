from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import PydanticBaseSettingsSource


class YamlSettingsSource(PydanticBaseSettingsSource):
    """Load settings from a YAML file.

    Looks for settings.yaml in:
    1. Path specified explicitly via constructor
    2. Path specified by SETTINGS_YAML_PATH env var
    3. ./settings.yaml (cwd)
    4. /etc/ii-agent/settings.yaml (k8s ConfigMap mount)
    """

    def __init__(self, settings_cls: type, yaml_path: str | None = None):
        super().__init__(settings_cls)
        self._yaml_path = yaml_path
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        paths = [
            self._yaml_path,
            os.environ.get("SETTINGS_YAML_PATH"),
            "settings.yaml",
            "/etc/ii-agent/settings.yaml",
        ]
        for p in paths:
            if p and Path(p).is_file():
                with open(p) as f:
                    self._data = yaml.safe_load(f) or {}
                return

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        val = self._data.get(field_name)
        return val, field_name, val is not None

    def __call__(self) -> dict[str, Any]:
        return self._data
