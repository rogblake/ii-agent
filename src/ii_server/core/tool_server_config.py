"""Centralized configuration singleton for tool server state."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from ii_server.core.constants import TOOL_CONFIG_PATH
from ii_server.core.models import DeploymentConfig

_CONFIG_PATH = Path(TOOL_CONFIG_PATH)


class ToolServerConfigSingleton:
    """Centralized, thread-safe singleton for persisting tool server state."""

    _instance: Optional["ToolServerConfigSingleton"] = None
    _instance_lock: Lock = Lock()
    _state_lock: Lock

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._deployment_config = None
                    cls._instance._mobile_app_config = None
                    cls._instance._state_lock = Lock()
                    cls._instance._load_from_disk()
        return cls._instance

    def _load_from_disk(self) -> None:
        if not _CONFIG_PATH.exists():
            return

        try:
            with _CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)

            self._deployment_config = data.get("deployment_config")
            self._mobile_app_config = data.get("mobile_app_config")
        except Exception as e:
            print(f"Failed to load tool server config from disk: {e}")

    def _persist(self) -> None:
        payload = {
            "deployment_config": self._deployment_config,
            "mobile_app_config": self._mobile_app_config,
        }

        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _CONFIG_PATH.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"Failed to persist tool server config to disk: {e}")

    def set_deployment_config(self, deployment_config: DeploymentConfig | Dict[str, Any]) -> None:
        with self._state_lock:
            if isinstance(deployment_config, DeploymentConfig):
                self._deployment_config = deployment_config.model_dump()
            else:
                self._deployment_config = deployment_config
            self._persist()

    def get_deployment_config(self) -> Optional[DeploymentConfig]:
        with self._state_lock:
            if self._deployment_config is None:
                return None
            return DeploymentConfig(**self._deployment_config)

    def set_mobile_app_config(self, mobile_app_config: Dict[str, Any]) -> None:
        """Set the mobile app configuration.

        Args:
            mobile_app_config: Dictionary containing mobile app config including
                project_name, project_dir, web_preview_url, qr_code_url, tunnel_url
        """
        with self._state_lock:
            self._mobile_app_config = mobile_app_config
            self._persist()

    def get_mobile_app_config(self) -> Optional[Dict[str, Any]]:
        """Get the mobile app configuration.

        Returns:
            Dictionary with mobile app config or None if not set.
        """
        with self._state_lock:
            return self._mobile_app_config


def get_tool_server_config() -> ToolServerConfigSingleton:
    return ToolServerConfigSingleton()
