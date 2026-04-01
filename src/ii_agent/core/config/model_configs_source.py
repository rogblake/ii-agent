"""Pydantic settings source that loads MODEL_CONFIGS from a YAML file.

When ``MODEL_CONFIGS_FILE`` env var is set, this source reads the YAML file
and populates the ``model_configs`` field as a list of dicts. This has lower
priority than the inline ``MODEL_CONFIGS`` env var (JSON array), so if both
are set the env var wins.

Usage in ``settings_customise_sources``::

    ModelConfigsYamlSource(settings_cls)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic_settings import PydanticBaseSettingsSource


class ModelConfigsYamlSource(PydanticBaseSettingsSource):
    """Load ``model_configs`` from a YAML file specified by MODEL_CONFIGS_FILE."""

    def __init__(self, settings_cls: type) -> None:
        super().__init__(settings_cls)
        self._data: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        yaml_path = os.environ.get("MODEL_CONFIGS_FILE")
        if not yaml_path:
            return

        path = Path(yaml_path)
        if not path.is_file():
            return

        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)

        if isinstance(data, list):
            self._data = data

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        if field_name == "model_configs" and self._data:
            return self._data, field_name, True
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        if self._data:
            return {"model_configs": self._data}
        return {}
