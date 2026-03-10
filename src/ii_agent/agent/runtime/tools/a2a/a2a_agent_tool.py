"""A2A Agent Tool for calling external A2A agents."""

import json
import logging
from typing import Any, Dict, Optional, Tuple

from a2a.types import (
    Message,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TaskState,
)

from ii_agent.agent.runtime.tools.base import BaseAgentTool, ToolResult

from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
from ii_agent.core.events.models import EventType, RealtimeEvent

logger = logging.getLogger(__name__)


class A2AAgentTool(BaseAgentTool):
    """Tool for calling external A2A agents."""

    name: str = "a2a_agent"
    display_name: str = "A2A Agent"
    description: str = "Call external agents based on A2A protocol to execute tasks"
    input_schema: dict = {
        "type": "object",
        "properties": {
            "agent_url": {
                "type": "string",
                "description": "Service URL of the A2A agent",
            },
            "query": {
                "type": "string",
                "description": "Query to send to the A2A agent",
            },
            "context": {
                "type": "object",
                "description": "Additional context information",
            },
        },
        "required": ["agent_url", "query"],
    }
    read_only: bool = True

    def __init__(self, default_agents: Optional[Dict[str, Any]] = None):
        """
        Initialize A2A Agent Tool.

        Args:
            default_agents: Pre-configured A2A agent mapping. Values can be plain URLs
                or dictionaries containing at least a `url` key along with optional
                metadata such as `name` or `description`.
        """
        self.default_agents: Dict[str, Dict[str, Any]] = {}
        if default_agents:
            for name, agent_config in default_agents.items():
                normalized = self._normalize_agent_config(name, agent_config)
                if normalized:
                    self.default_agents[name] = normalized

        self._clients: Dict[str, IIAgentA2AClient] = {}
        self._client_headers: Dict[str, Tuple[Tuple[str, str], ...]] = {}
        self._agent_descriptions: Dict[str, str] = {}
        self._agent_cards: Dict[str, Any] = {}
        self._agent_extensions: Dict[str, set[str]] = {}
        self._initialized = False
        self._event_stream = None

        logger.info(
            f"A2A Agent Tool initialized with {len(self.default_agents)} agents"
        )
        for name, info in self.default_agents.items():
            logger.debug(f"  - {name}: {info['url']}")

    async def initialize(self):
        """Initialize by testing connections and caching agent cards."""
        if self._initialized:
            logger.debug("A2A Agent Tool already initialized, skipping...")
            return

        logger.info("Starting A2A agents initialization...")

        for name, info in self.default_agents.items():
            try:
                agent_url = info["url"]
                logger.debug(f"Testing connection to {name} at {agent_url}")
                client = await self._get_client(agent_url)

                logger.debug(f"Fetching agent card for {name}...")
                agent_card = await client.get_agent_card()
                self._agent_cards[agent_url] = agent_card
                self._agent_extensions[agent_url] = set(
                    getattr(agent_card, "extensions", []) or []
                )

                description = (
                    getattr(agent_card, "description", None)
                    or info.get("description")
                    or f"Specialized {info.get('name', name)} agent"
                )
                self._agent_descriptions[agent_url] = description

                logger.debug(f"Successfully cached agent card for {name}")

            except Exception as e:
                logger.error(f"Failed to initialize {name} at {agent_url}: {e}")
                # Set fallback description
                fallback_description = info.get(
                    "description", f"Specialized {name} agent (connection failed)"
                )
                self._agent_descriptions[info["url"]] = fallback_description

        self._initialized = True
        logger.info(
            f"A2A Agent Tool initialization completed! Initialized {len(self._agent_descriptions)} agents"
        )

    def set_event_stream(self, event_stream) -> None:
        """Inject the agent event stream so we can emit streaming updates."""
        self._event_stream = event_stream

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        """Execute A2A agent call."""
        try:
            logger.debug("A2A Agent Tool execute() called")

            # Initialize if not already done
            if not self._initialized:
                logger.debug(
                    "A2A Agent Tool not initialized, starting initialization..."
                )
                await self.initialize()

            agent_identifier = tool_input.get("agent_url")
            query = tool_input.get("query")
            raw_context = tool_input.get("context", {})
            if not isinstance(raw_context, dict):
                raw_context = {}
            context = dict(raw_context)
            streaming_preference = context.pop("streaming", None)
            if self._event_stream:
                if streaming_preference is None:
                    streaming_enabled = True
                else:
                    streaming_enabled = self._coerce_bool(streaming_preference)
            else:
                streaming_enabled = False
            streaming_enabled = streaming_enabled and self._event_stream is not None

            logger.debug(f"A2A Agent call: {agent_identifier} - {query[:50]}...")

            if not agent_identifier or not query:
                logger.error("Missing required parameters: agent_url or query")
                return ToolResult(
                    llm_content="Error: agent_url and query are required",
                    user_display_content="❌ Error: Missing required parameters agent_url or query",
                )

            # Allow using the configured agent name instead of raw URL
            agent_defaults = None
            if agent_identifier in self.default_agents:
                agent_defaults = self.default_agents[agent_identifier]
                agent_url = agent_defaults["url"]
            else:
                agent_url = agent_identifier
                agent_defaults = self._find_agent_defaults_by_url(agent_url)

            if agent_defaults:
                metadata_defaults = agent_defaults.get("metadata")
                if isinstance(metadata_defaults, dict):
                    default_context = metadata_defaults.get("context")
                    if isinstance(default_context, dict):
                        merged_context = dict(default_context)
                        merged_context.update(context)
                        context = merged_context
                    for key in ("requested_extensions", "fallback_briefing"):
                        if key in metadata_defaults and key not in context:
                            context[key] = metadata_defaults[key]

            # Get or create A2A client
            client = await self._get_client(agent_url)

            # Ensure agent card cached for negotiation routines
            await self._ensure_agent_card(client, agent_url)

            # Resolve description and supported extensions
            agent_description = await self.get_agent_description(agent_url)
            supported_extensions = await self.get_agent_extensions(agent_url)

            negotiation = self._negotiate_extensions(supported_extensions, context)

            final_query, final_context = self._prepare_context(
                query=query,
                context=context,
                negotiation=negotiation,
                agent_description=agent_description,
            )

            result: Optional[dict[str, Any]] = None
            if streaming_enabled:
                try:
                    result = await self._execute_streaming_call(
                        client=client,
                        agent_url=agent_url,
                        agent_description=agent_description,
                        query=final_query,
                        context=final_context,
                        negotiation=negotiation,
                    )
                except Exception as exc:
                    logger.warning(
                        "Streaming call to %s failed (%s); falling back to blocking mode",
                        agent_url,
                        exc,
                    )
                    streaming_enabled = False
                    result = None

            if result is None:
                result = await client.call_agent(
                    query=final_query, context=final_context
                )

            logger.debug(
                f"A2A agent response: success={result.get('success', False)}, content_length={len(result.get('content', ''))}"
            )

            if result.get("success"):
                # Include agent description in the response for better context
                enhanced_content = f"[Using {agent_description}] {result['content']}"
                enhanced_display = (
                    f"[{agent_description}] {result['user_display_content']}"
                )

                logger.info("A2A agent call successful")
                return ToolResult(
                    llm_content=enhanced_content, user_display_content=enhanced_display
                )
            else:
                logger.warning("A2A agent call failed")
                return ToolResult(
                    llm_content=result["content"],
                    user_display_content=result["user_display_content"],
                )

        except Exception as e:
            logger.error(f"A2A agent call failed with exception: {e}", exc_info=True)
            return ToolResult(
                llm_content=f"Error calling A2A agent: {str(e)}",
                user_display_content=f"❌ A2A agent call failed: {str(e)}",
            )

    async def _emit_stream_event(self, event_type: EventType, content: Dict[str, Any]):
        """Send a realtime event to the agent event stream, if available."""
        if not self._event_stream:
            return
        try:
            await self._event_stream.add_event(
                RealtimeEvent(type=event_type, content=content)
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to emit streaming event: %s", exc)

    def _extract_text_from_artifact(
        self, event: TaskArtifactUpdateEvent
    ) -> Optional[str]:
        artifact = getattr(event, "artifact", None)
        if artifact is None:
            return None

        parts = getattr(artifact, "parts", None)
        if parts:
            for part in parts:
                root = getattr(part, "root", None)
                if root and hasattr(root, "text") and root.text:
                    return str(root.text)
                if isinstance(part, dict):
                    text = part.get("text")
                    if text:
                        return str(text)

        data = getattr(artifact, "data", None)
        if data:
            return str(data)
        return None

    def _extract_text_from_message(self, message: Optional[Message]) -> Optional[str]:
        if message is None:
            return None
        parts = getattr(message, "parts", None) or []
        for part in parts:
            root = getattr(part, "root", None)
            if root and hasattr(root, "text") and root.text:
                return str(root.text)
            if isinstance(part, dict) and "text" in part:
                return str(part["text"])
        return None

    def _map_task_state(self, state: TaskState) -> EventType:
        if state is TaskState.working:
            return EventType.PROCESSING
        return EventType.STATUS_UPDATE

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"false", "0", "no", "off"}:
                return False
            if lowered in {"true", "1", "yes", "on"}:
                return True
        return bool(value)

    async def _execute_streaming_call(
        self,
        *,
        client: IIAgentA2AClient,
        agent_url: str,
        agent_description: str,
        query: str,
        context: Dict[str, Any],
        negotiation: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self._event_stream is None:
            raise RuntimeError("Streaming requested without an event stream")

        aggregated_chunks: list[str] = []
        final_text: Optional[str] = None
        last_status: Optional[TaskStatusUpdateEvent] = None

        async for payload in client.stream_agent(query=query, context=context):
            if isinstance(payload, TaskArtifactUpdateEvent):
                text = self._extract_text_from_artifact(payload)
                if text:
                    aggregated_chunks.append(text)
                    await self._emit_stream_event(
                        EventType.AGENT_RESPONSE,
                        {
                            "text": text,
                            "agent_url": agent_url,
                            "negotiation": negotiation,
                            "artifact_name": getattr(payload.artifact, "name", None),
                        },
                    )
            elif isinstance(payload, TaskStatusUpdateEvent):
                last_status = payload
                message_text = self._extract_text_from_message(payload.status.message)
                status_state = payload.status.state
                content = {
                    "agent_url": agent_url,
                    "downstream_state": status_state.value
                    if hasattr(status_state, "value")
                    else str(status_state),
                    "metadata": payload.metadata or {},
                }
                if message_text:
                    content["text"] = message_text
                    if status_state is TaskState.working:
                        aggregated_chunks.append(message_text)
                event_type = self._map_task_state(status_state)
                await self._emit_stream_event(event_type, content)
                if status_state is TaskState.completed and message_text:
                    final_text = message_text
                if status_state is TaskState.failed and message_text:
                    final_text = message_text
            elif isinstance(payload, Message):
                message_text = self._extract_text_from_message(payload)
                if message_text:
                    final_text = message_text
                    aggregated_chunks.append(message_text)
                    await self._emit_stream_event(
                        EventType.AGENT_RESPONSE,
                        {"text": message_text, "agent_url": agent_url},
                    )
            elif isinstance(payload, Task):
                task_payload = (
                    payload.model_dump()
                    if hasattr(payload, "model_dump")
                    else getattr(payload, "__dict__", str(payload))
                )
                await self._emit_stream_event(
                    EventType.STATUS_UPDATE,
                    {"agent_url": agent_url, "task": task_payload},
                )
            else:
                logger.debug(
                    "Received unhandled streaming payload from %s: %s",
                    agent_url,
                    type(payload),
                )

        if final_text is None:
            combined = "\n".join(chunk for chunk in aggregated_chunks if chunk).strip()
            final_text = combined or "Streaming call completed."

        result: Dict[str, Any] = {
            "success": True,
            "content": final_text,
            "user_display_content": final_text,
            "agent_url": agent_url,
            "status": last_status,
        }
        get_extensions = getattr(client, "get_last_response_extensions", None)
        if callable(get_extensions):
            try:
                extensions_summary = get_extensions()
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "Failed to fetch extension summary from %s: %s",
                    agent_url,
                    exc,
                )
            else:
                if extensions_summary:
                    result["extensions"] = extensions_summary
        return result

    async def _get_client(self, agent_url: str) -> IIAgentA2AClient:
        """Get or create A2A client for the given URL."""

        headers = self._resolve_headers(agent_url)
        header_signature = self._canonicalize_headers(headers)

        existing_client = self._clients.get(agent_url)
        if existing_client:
            cached_signature = self._client_headers.get(agent_url, ())
            if cached_signature == header_signature:
                return existing_client

            logger.debug(
                "Detected updated headers for %s; refreshing client instance",
                agent_url,
            )
            await existing_client.close()
            self._clients.pop(agent_url, None)
            self._client_headers.pop(agent_url, None)

        timeout_seconds = self._resolve_timeout_seconds(agent_url)
        if timeout_seconds is not None:
            logger.debug(
                "Using custom timeout %.2fs for A2A agent %s",
                timeout_seconds,
                agent_url,
            )
            client = IIAgentA2AClient(
                agent_url,
                timeout_seconds=timeout_seconds,
                default_headers=headers,
            )
        else:
            client = IIAgentA2AClient(agent_url, default_headers=headers)

        self._clients[agent_url] = client
        self._client_headers[agent_url] = header_signature
        return client

    def _resolve_headers(self, agent_url: str) -> Dict[str, str]:
        """Return sanitized headers configured for the agent, if any."""

        defaults = self._find_agent_defaults_by_url(agent_url)
        if not defaults:
            return {}

        raw_headers = defaults.get("headers")
        return self._sanitize_headers(raw_headers)

    @staticmethod
    def _sanitize_headers(headers: Any) -> Dict[str, str]:
        if not isinstance(headers, dict):
            return {}

        sanitized: Dict[str, str] = {}
        for key, value in headers.items():
            if key is None:
                continue
            key_str = str(key).strip()
            if not key_str:
                continue
            if value is None:
                continue
            sanitized[key_str] = str(value)
        return sanitized

    @staticmethod
    def _canonicalize_headers(headers: Dict[str, str]) -> Tuple[Tuple[str, str], ...]:
        if not headers:
            return ()

        ordered = sorted(((key.lower(), value) for key, value in headers.items()))
        return tuple(ordered)

    async def get_agent_description(self, agent_url: str) -> str:
        """Get agent description from agent card."""
        if agent_url in self._agent_descriptions:
            return self._agent_descriptions[agent_url]

        for info in self.default_agents.values():
            if info["url"] == agent_url and "description" in info:
                self._agent_descriptions[agent_url] = info["description"]
                return info["description"]

        try:
            client = await self._get_client(agent_url)
            await self._ensure_agent_card(client, agent_url)

            agent_card = self._agent_cards.get(agent_url)
            description = (
                getattr(agent_card, "description", None)
                if agent_card is not None
                else None
            )
            if not description:
                description = f"Specialized agent at {agent_url}"
            self._agent_descriptions[agent_url] = description
            return description
        except Exception as e:
            logger.warning(f"Failed to get agent card for {agent_url}: {e}")
            # Fallback description
            description = f"Specialized agent at {agent_url}"
            self._agent_descriptions[agent_url] = description
            return description

    async def close_all_clients(self):
        """Close all A2A client connections."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
        self._client_headers.clear()

    async def get_agent_extensions(self, agent_url: str) -> list[str]:
        """Return supported extensions for the specified agent."""

        if agent_url in self._agent_extensions:
            return sorted(self._agent_extensions[agent_url])

        client = await self._get_client(agent_url)
        await self._ensure_agent_card(client, agent_url)
        return sorted(self._agent_extensions.get(agent_url, set()))

    async def _ensure_agent_card(
        self, client: IIAgentA2AClient, agent_url: str
    ) -> None:
        """Fetch and cache agent card if not already available."""

        if agent_url in self._agent_cards:
            return

        agent_card = await client.get_agent_card()

        self._agent_cards[agent_url] = agent_card
        self._agent_extensions[agent_url] = set(
            getattr(agent_card, "extensions", []) or []
        )
        if (
            agent_url not in self._agent_descriptions
            and hasattr(agent_card, "description")
            and getattr(agent_card, "description")
        ):
            self._agent_descriptions[agent_url] = getattr(agent_card, "description")

    def _negotiate_extensions(
        self, supported: list[str], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Determine active and missing extensions for the call."""

        requested = []
        if context and isinstance(context, dict):
            requested = list(context.get("requested_extensions", []))

        supported_set = set(supported)
        active = [ext for ext in requested if ext in supported_set]
        missing = [ext for ext in requested if ext not in supported_set]

        return {
            "requested_extensions": requested,
            "active_extensions": active,
            "missing_extensions": missing,
        }

    def _prepare_context(
        self,
        *,
        query: str,
        context: Dict[str, Any],
        negotiation: Dict[str, Any],
        agent_description: str,
    ) -> tuple[str, Dict[str, Any]]:
        """Return final query/context payload with fallback applied when needed."""

        final_context: Dict[str, Any] = {}
        if context and isinstance(context, dict):
            final_context.update(context)

        final_context.setdefault("a2a_negotiation", negotiation)

        missing = negotiation["missing_extensions"]
        if missing:
            logger.info(
                "A2A agent at %s does not support extensions %s; using fallback",
                agent_description,
                missing,
            )

            fallback_brief = final_context.pop("fallback_briefing", None)
            if fallback_brief is None:
                fallback_brief = final_context.get("briefing")

            if fallback_brief is None:
                try:
                    fallback_brief = json.dumps(final_context, ensure_ascii=False)
                except Exception:  # pragma: no cover - best effort
                    fallback_brief = str(final_context)

            if fallback_brief:
                query = f"{query}\n\n[Fallback Context for {agent_description}]\n{fallback_brief}"
                final_context.setdefault("fallback_payload", fallback_brief)

        return query, final_context

    def _find_agent_defaults_by_url(self, agent_url: str) -> Optional[Dict[str, Any]]:
        """Return configured agent defaults by matching URL."""

        for info in self.default_agents.values():
            if info.get("url") == agent_url:
                return info
        return None

    def _resolve_timeout_seconds(self, agent_url: str) -> Optional[float]:
        """Return timeout override in seconds when provided via agent metadata."""

        agent_defaults = self._find_agent_defaults_by_url(agent_url)
        if not agent_defaults:
            return None

        metadata = agent_defaults.get("metadata")
        if not isinstance(metadata, dict):
            return None

        candidate_keys = ("timeout_seconds", "timeoutSeconds", "timeout")
        for key in candidate_keys:
            if key not in metadata:
                continue
            seconds = self._coerce_timeout(metadata[key])
            if seconds is not None and seconds > 0:
                return seconds

        return None

    @staticmethod
    def _coerce_timeout(value: Any) -> Optional[float]:
        """Convert timeout metadata value into seconds."""

        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            text = value.strip().lower()
            if not text:
                return None

            multiplier = 1.0
            if text.endswith("ms"):
                multiplier = 0.001
                text = text[:-2]
            elif text.endswith("s"):
                text = text[:-1]

            try:
                numeric = float(text)
            except ValueError:
                logger.warning(
                    "Failed to parse timeout value '%s'; ignoring override", value
                )
                return None

            return numeric * multiplier

        logger.warning(
            "Unsupported timeout override type %s (value=%s); ignoring",
            type(value),
            value,
        )
        return None

    @staticmethod
    def _normalize_agent_config(
        name: str, agent_config: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Normalize agent configuration entries. Supports:
        - Plain string URL values
        - Dict values containing `url`, `name`, `description`, etc.
        """
        if isinstance(agent_config, str):
            agent_url = agent_config.strip()
            if not agent_url:
                logger.warning("A2A agent %s has empty URL string, skipping.", name)
                return None
            return {"url": agent_url, "name": name}

        if isinstance(agent_config, dict):
            agent_url = str(agent_config.get("url", "")).strip()
            if not agent_url:
                logger.warning(
                    "A2A agent %s configuration is missing 'url', skipping.", name
                )
                return None

            normalized = {
                "url": agent_url,
                "name": agent_config.get("name", name),
            }
            if "description" in agent_config:
                normalized["description"] = agent_config["description"]
            if "metadata" in agent_config:
                normalized["metadata"] = agent_config["metadata"]
            if "headers" in agent_config:
                raw_headers = agent_config["headers"]
                if isinstance(raw_headers, dict):
                    sanitized_headers = A2AAgentTool._sanitize_headers(raw_headers)
                    if sanitized_headers:
                        normalized["headers"] = sanitized_headers
                elif raw_headers is not None:
                    logger.warning(
                        "A2A agent %s headers must be a mapping, got %s; ignoring.",
                        name,
                        type(raw_headers),
                    )
            return normalized

        logger.warning(
            "A2A agent %s configuration has unsupported type %s, skipping.",
            name,
            type(agent_config),
        )
        return None
