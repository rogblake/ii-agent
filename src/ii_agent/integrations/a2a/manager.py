"""A2A Manager for handling A2A configuration and tool management."""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict

from ii_agent.integrations.a2a.config import A2AConfig
from ii_agent.integrations.a2a.exceptions import InvalidA2AAgentConfig
from ii_agent.engine.runtime.tools.a2a.a2a_agent_tool import A2AAgentTool

logger = logging.getLogger(__name__)


class A2AManager:
    """Manager for A2A configuration and tool management."""

    def __init__(self, config: A2AConfig | None = None):
        """Initialize A2A Manager and normalize initial configuration."""

        self.config = config or A2AConfig()
        self._a2a_tool: A2AAgentTool | None = None
        self._third_party_agents: Dict[str, Dict[str, Any]] = self._normalize_agents()

    def get_a2a_agents(self) -> Dict[str, Dict[str, Any]]:
        """Return normalized A2A agent configuration."""
        return copy.deepcopy(self._third_party_agents)

    def has_a2a_agents(self) -> bool:
        """Return True when any A2A agents are available."""
        return bool(self.get_a2a_agents())

    def create_a2a_tool(
        self, a2a_agents_config: Dict[str, Dict[str, Any]]
    ) -> A2AAgentTool:
        """Create (or return cached) A2AAgentTool using provided configuration."""

        if self._a2a_tool is None:
            logger.info("🔧 A2A agents enabled, creating A2A Agent Tool")
            logger.info(f"   A2A agents configuration: {a2a_agents_config}")
            self._a2a_tool = A2AAgentTool(default_agents=a2a_agents_config)
            logger.info("✅ A2A Agent Tool created successfully")

        return self._a2a_tool

    def get_a2a_prompt(self) -> str:
        """Return formatted prompt describing available A2A agents, if any."""

        a2a_agents_config = self.get_a2a_agents()

        if not a2a_agents_config:
            logger.info("ℹ️ No A2A agents configured, skipping prompt generation")
            return ""

        temp_tool_args = {"enable_a2a_agents": True, "a2a_agents": a2a_agents_config}

        logger.info("📝 Adding A2A agents description to system prompt")
        logger.info(f"   A2A agents: {list(a2a_agents_config.keys())}")

        from ii_agent.engine.prompts.a2a_agents_prompt import build_a2a_agents_prompt

        a2a_prompt = build_a2a_agents_prompt(temp_tool_args)
        logger.info(
            f"   Generated A2A prompt: {a2a_prompt[:200]}{'...' if len(a2a_prompt) > 200 else ''}"
        )

        if a2a_prompt:
            logger.info(f"   A2A prompt length: {len(a2a_prompt)} characters")
            logger.info("✅ A2A agents description added to system prompt")
            return a2a_prompt

        logger.warning("⚠️ A2A prompt is empty, not adding to system prompt")
        return ""

    def get_a2a_tool_for_registration(self) -> A2AAgentTool | None:
        """Return configured A2AAgentTool if agents are available, else None."""

        a2a_agents_config = self.get_a2a_agents()

        if not a2a_agents_config:
            logger.info("ℹ️ No A2A agents configured")
            return None

        return self.create_a2a_tool(a2a_agents_config)

    def _normalize_agents(self) -> Dict[str, Dict[str, Any]]:
        """Validate and normalize an agent configuration mapping."""

        agents = self.config.get_third_party_agents()

        if not agents:
            return {}

        normalized: Dict[str, Dict[str, Any]] = {}
        for name, agent_config in agents.items():
            normalized[name] = self._normalize_agent_config(name, agent_config)

        return normalized

    @staticmethod
    def _normalize_agent_config(name: str, agent_config: Any) -> Dict[str, Any]:
        """Normalize a single agent configuration entry."""

        if isinstance(agent_config, str):
            agent_url = agent_config.strip()
            if not agent_url:
                raise InvalidA2AAgentConfig(f"Agent '{name}' has an empty URL string")
            return {"url": agent_url, "name": name}

        if isinstance(agent_config, dict):
            agent_url = str(agent_config.get("url", "")).strip()
            if not agent_url:
                raise InvalidA2AAgentConfig(
                    f"Agent '{name}' configuration is missing a non-empty 'url'"
                )

            normalized: Dict[str, Any] = {
                "url": agent_url,
                "name": agent_config.get("name", name),
            }

            if "description" in agent_config:
                description = agent_config["description"]
                if not isinstance(description, str):
                    raise InvalidA2AAgentConfig(
                        f"Agent '{name}' description must be a string"
                    )
                normalized["description"] = description

            if "metadata" in agent_config:
                metadata = agent_config["metadata"]
                if metadata is not None and not isinstance(metadata, dict):
                    raise InvalidA2AAgentConfig(
                        f"Agent '{name}' metadata must be a mapping if provided"
                    )
                normalized["metadata"] = metadata

            if "headers" in agent_config:
                headers = agent_config["headers"]
                if headers is None:
                    pass
                elif not isinstance(headers, dict):
                    raise InvalidA2AAgentConfig(
                        f"Agent '{name}' headers must be a mapping if provided"
                    )
                else:
                    sanitized_headers: Dict[str, str] = {}
                    for key, value in headers.items():
                        if key is None:
                            continue
                        key_str = str(key).strip()
                        if not key_str:
                            continue
                        if value is None:
                            continue
                        sanitized_headers[key_str] = str(value)
                    if sanitized_headers:
                        normalized["headers"] = sanitized_headers

            return normalized

        raise InvalidA2AAgentConfig(
            f"Agent '{name}' configuration has unsupported type {type(agent_config)}"
        )
