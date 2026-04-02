"""A2A Client wrapper built on top of the modern a2a-sdk ClientFactory."""

from __future__ import annotations

import asyncio
import copy
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Mapping, Optional

import httpx
from a2a.client import (
    A2ACardResolver,
    Client,
    ClientCallInterceptor,
    ClientCallContext,
    ClientConfig,
    ClientEvent,
    ClientFactory,
    Consumer,
)
from a2a.client.helpers import create_text_message_object
from a2a.types import (
    AgentCard,
    AgentExtension,
    Artifact,
    Message,
    Part,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _ClientEntry:
    """Cache entry for a configured client."""

    config: ClientConfig
    client: Client


class IIAgentA2AClient:
    """High-level client that negotiates transports via ClientFactory."""

    _DEFAULT_HEADERS = {
        "Content-Type": "application/json",
        "User-Agent": "ii-agent-a2a-client/1.0",
    }

    def __init__(
        self,
        agent_url: str,
        *,
        timeout: Optional[httpx.Timeout] = None,
        timeout_seconds: Optional[float] = None,
        supported_transports: Optional[List[str]] = None,
        accepted_output_modes: Optional[List[str]] = None,
        interceptors: Optional[List[ClientCallInterceptor]] = None,
        consumers: Optional[List[Consumer]] = None,
        use_client_preference: bool = False,
        default_headers: Optional[Mapping[str, Any]] = None,
    ):
        sanitized_url = agent_url.rstrip("/")
        self.agent_url = sanitized_url
        self._card_base_url = self._derive_card_base_url(sanitized_url)
        self._timeout = timeout or self._build_timeout(timeout_seconds)
        self._limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)

        self._httpx_client: Optional[httpx.AsyncClient] = None
        self._agent_card: Optional[AgentCard] = None

        self._custom_headers = self._sanitize_headers(default_headers)

        self._supported_transports = supported_transports or []
        self._accepted_output_modes = accepted_output_modes or []
        self._interceptors: list[ClientCallInterceptor] = [
            ExtensionsHeaderInterceptor()
        ]
        if interceptors:
            self._interceptors.extend(interceptors)
        self._consumers = consumers or []
        self._use_client_preference = use_client_preference

        self._client_lock = asyncio.Lock()
        self._clients: dict[bool, _ClientEntry] = {}
        self._last_response_extensions: Optional[Dict[str, Any]] = None
        self._extension_definitions: Dict[str, AgentExtension] = {}
        self._required_extensions: set[str] = set()

        logger.debug("A2A ClientFactory wrapper created for %s", self.agent_url)

    async def call_agent(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a blocking request to the downstream agent."""
        context = context or {}
        logger.debug("Sending blocking request to %s", self.agent_url)

        call_context = ClientCallContext()
        try:
            client = await self._get_client(streaming=False)
            message = self._build_message(query, context)

            final_payload: ClientEvent | Message | None = None
            async for payload in client.send_message(message, context=call_context):
                final_payload = payload
                self._capture_server_extensions(call_context, payload)

            if final_payload is None:
                logger.error("No response returned from agent %s", self.agent_url)
                result = self._format_error("No response received from agent.")
                self._store_response_extensions(call_context, result)
                return result

            content = self._extract_text_from_payload(final_payload)
            if content is None:
                content = str(final_payload)

            logger.info(
                "A2A agent call successful: agent=%s, chars=%s",
                self.agent_url,
                len(content),
            )
            result = {
                "content": content,
                "user_display_content": content,
                "success": True,
                "agent_url": self.agent_url,
            }
            self._store_response_extensions(call_context, result)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Blocking invocation to %s failed: %s",
                self.agent_url,
                exc,
                exc_info=True,
            )
            result = self._format_error(str(exc))
            self._store_response_extensions(call_context, result)
            return result

    async def stream_agent(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Any, None]:
        """Stream responses from a downstream agent."""
        context = context or {}
        logger.debug("Starting streaming request to %s", self.agent_url)

        client = await self._get_client(streaming=True)
        message = self._build_message(query, context)
        call_context = ClientCallContext()

        try:
            async for payload in client.send_message(message, context=call_context):
                self._capture_server_extensions(call_context, payload)
                self._synchronize_stream_extensions(call_context, payload)
                async for item in self._yield_stream_items(payload):
                    yield item
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Streaming invocation to %s failed: %s",
                self.agent_url,
                exc,
                exc_info=True,
            )
            raise
        finally:
            self._store_response_extensions(call_context, None)

    async def get_agent_card(self) -> AgentCard:
        """Return (and cache) the agent card."""
        if self._agent_card is not None:
            return self._agent_card

        httpx_client = await self._get_http_client()
        base_url = self._card_base_url or self.agent_url
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
        card = await resolver.get_agent_card()
        self._agent_card = card
        logger.info(
            "Fetched agent card for %s (name=%s transport=%s)",
            self.agent_url,
            getattr(card, "name", "unknown"),
            getattr(card, "preferred_transport", None),
        )
        return card

    async def refresh_agent_card(self) -> AgentCard:
        """Force refresh of the cached agent card."""
        self._agent_card = None
        return await self.get_agent_card()

    async def close(self) -> None:
        """Close all underlying resources."""
        async with self._client_lock:
            for entry in self._clients.values():
                try:
                    await entry.client.close()
                except Exception as exc:  # pragma: no cover - defensive cleanup
                    logger.debug("Failed to close A2A client transport: %s", exc)
            self._clients.clear()

            if self._httpx_client and not self._httpx_client.is_closed:
                await self._httpx_client.aclose()
            self._httpx_client = None
            self._agent_card = None

    async def _get_client(self, *, streaming: bool) -> Client:
        """Return a configured client for the requested streaming mode."""
        async with self._client_lock:
            entry = self._clients.get(streaming)
            if entry:
                return entry.client

            httpx_client = await self._get_http_client()
            agent_card = await self.get_agent_card()
            self._hydrate_extension_config(agent_card)

            config = ClientConfig(
                streaming=streaming,
                polling=False,
                httpx_client=httpx_client,
                supported_transports=self._supported_transports.copy(),
                use_client_preference=self._use_client_preference,
                accepted_output_modes=self._accepted_output_modes.copy(),
            )

            factory = ClientFactory(config, self._consumers.copy())
            client = factory.create(
                agent_card,
                interceptors=self._interceptors.copy(),
            )

            entry = _ClientEntry(config=config, client=client)
            self._clients[streaming] = entry
            return client

    def _build_message(self, query: str, context: Dict[str, Any]) -> Message:
        """Construct an A2A message using helper utilities."""
        message = create_text_message_object(role=Role.user, content=query)

        if context:
            try:
                metadata = dict(message.metadata or {})
                metadata["ii-agent"] = {"context": context}
                message.metadata = metadata
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Failed to attach structured context: %s", exc)
                metadata = dict(message.metadata or {})
                metadata["ii-agent"] = {"context": str(context)}
                message.metadata = metadata

        requested_extensions = context.get("requested_extensions")
        if isinstance(requested_extensions, list):
            requested = {
                str(ext).strip()
                for ext in requested_extensions
                if isinstance(ext, (str, int, float)) and str(ext).strip()
            }
        else:
            requested = set()
        requested.update(self._required_extensions)
        if requested:
            message.extensions = sorted(requested)
        self._apply_extension_metadata_defaults(message, context)

        return message

    def _hydrate_extension_config(self, card: AgentCard) -> None:
        """Cache extension definitions and required URIs from the agent card."""

        capabilities = getattr(card, "capabilities", None)
        extensions = getattr(capabilities, "extensions", None) or []
        definitions: Dict[str, AgentExtension] = {}
        required: set[str] = set()

        for ext in extensions:
            if not isinstance(ext, AgentExtension):
                continue
            uri = getattr(ext, "uri", None)
            if not uri:
                continue
            definitions[uri] = ext
            if getattr(ext, "required", False):
                required.add(uri)

        self._extension_definitions = definitions
        self._required_extensions = required

    def _apply_extension_metadata_defaults(
        self, message: Message, context: Dict[str, Any]
    ) -> None:
        """Inject default metadata scaffolding for declared extensions."""

        if not self._extension_definitions:
            return

        metadata = dict(message.metadata or {})
        updated = False
        for extension in self._extension_definitions.values():
            params = getattr(extension, "params", None)
            if not isinstance(params, dict):
                continue
            metadata_key = params.get("metadata_key")
            if not metadata_key:
                continue

            nested = metadata.get(metadata_key)
            if isinstance(nested, dict):
                target = nested
            elif nested is None:
                target = {}
            else:
                target = {"value": nested}
            metadata[metadata_key] = target

            sections = params.get("sections")
            if isinstance(sections, list):
                for section in sections:
                    if section in target:
                        continue
                    value = context.get(section)
                    if isinstance(value, dict):
                        target[section] = copy.deepcopy(value)
                    elif value is not None:
                        target[section] = value
                    else:
                        target.setdefault(section, {})
            fields = params.get("fields")
            if isinstance(fields, list):
                for field in fields:
                    if field in target:
                        continue
                    value = context.get(field)
                    if value is not None:
                        target[field] = value
            updated = True

        if updated:
            message.metadata = metadata

    def _capture_server_extensions(
        self, call_context: ClientCallContext, payload: ClientEvent | Message
    ) -> None:
        """Persist extension summary reported by the downstream agent."""

        state = call_context.state.setdefault(
            ExtensionsHeaderInterceptor._STATE_KEY, {}
        )
        if not isinstance(state, dict):
            state = {}
            call_context.state[ExtensionsHeaderInterceptor._STATE_KEY] = state
        for model in self._iter_extension_models(payload):
            summary = self._summary_from_metadata(model)
            if summary:
                state["server_summary"] = copy.deepcopy(summary)
                state.pop("snapshot", None)
                break

    @staticmethod
    def _iter_extension_models(
        payload: ClientEvent | Message,
    ) -> list[Any]:
        """Return candidate models that may contain extension metadata."""

        if payload is None:
            return []
        if isinstance(payload, tuple):
            task, update = payload
            models: list[Any] = [task]
            if update is not None:
                models.append(update)
            return models
        return [payload]

    @staticmethod
    def _summary_from_metadata(model: Any) -> Optional[Dict[str, Any]]:
        """Extract extension summary from a model's metadata."""

        if model is None or not hasattr(model, "metadata"):
            return None

        metadata = getattr(model, "metadata")
        if metadata is None:
            return None

        if isinstance(metadata, dict):
            summary = metadata.get("extensions")
            return summary if isinstance(summary, dict) else None

        if hasattr(metadata, "model_dump"):
            try:
                dumped = metadata.model_dump()
            except Exception:  # pragma: no cover - defensive
                return None
            summary = dumped.get("extensions")
            return summary if isinstance(summary, dict) else None

        if hasattr(metadata, "copy"):
            try:
                copied = metadata.copy()
            except Exception:  # pragma: no cover - defensive
                return None
            if isinstance(copied, dict):
                summary = copied.get("extensions")
                return summary if isinstance(summary, dict) else None

        return None

    def _capture_extensions_snapshot(
        self, call_context: ClientCallContext
    ) -> Optional[Dict[str, Any]]:
        """Ensure negotiation summary is cached and return a snapshot."""

        state = call_context.state.get(ExtensionsHeaderInterceptor._STATE_KEY)
        if not isinstance(state, dict):
            return (
                copy.deepcopy(self._last_response_extensions)
                if self._last_response_extensions
                else None
            )

        snapshot = state.get("snapshot")
        if isinstance(snapshot, dict) and snapshot:
            return snapshot

        server_summary = state.get("server_summary")
        if isinstance(server_summary, dict) and server_summary:
            snapshot = copy.deepcopy(server_summary)
            state["snapshot"] = snapshot
            return snapshot

        if self._last_response_extensions:
            snapshot = copy.deepcopy(self._last_response_extensions)
            state["snapshot"] = snapshot
            return snapshot

        self._store_response_extensions(call_context, None)

        snapshot = state.get("snapshot")
        if isinstance(snapshot, dict) and snapshot:
            return snapshot

        if self._last_response_extensions:
            snapshot = copy.deepcopy(self._last_response_extensions)
            state["snapshot"] = snapshot
            return snapshot

        return None

    def _synchronize_stream_extensions(
        self, call_context: ClientCallContext, payload: ClientEvent | Message
    ) -> None:
        """Attach extension negotiation metadata to streaming payloads."""

        summary = self._capture_extensions_snapshot(call_context)
        if not summary:
            return

        summary_snapshot = copy.deepcopy(summary)
        if isinstance(payload, Message):
            self._inject_extensions_into_model(payload, summary_snapshot)
            return

        task, update = payload
        self._inject_extensions_into_model(task, copy.deepcopy(summary_snapshot))
        if update is not None:
            self._inject_extensions_into_model(update, copy.deepcopy(summary_snapshot))

    @staticmethod
    def _inject_extensions_into_model(model: Any, summary: Dict[str, Any]) -> None:
        """Ensure the provided model carries extension metadata."""

        if model is None or not hasattr(model, "metadata"):
            return

        metadata = getattr(model, "metadata")
        summary_payload = copy.deepcopy(summary)
        if metadata is None:
            setattr(model, "metadata", {"extensions": summary_payload})
            return

        if isinstance(metadata, dict):
            metadata.setdefault("extensions", summary_payload)
            return

        if hasattr(metadata, "model_dump"):
            try:
                dumped = metadata.model_dump()
            except Exception:  # pragma: no cover - defensive
                return
            if "extensions" not in dumped:
                dumped["extensions"] = summary_payload
                setattr(model, "metadata", dumped)
            return

        if hasattr(metadata, "copy"):
            try:
                copied = metadata.copy()
            except Exception:  # pragma: no cover - defensive
                return
            if isinstance(copied, dict) and "extensions" not in copied:
                copied["extensions"] = summary_payload
                setattr(model, "metadata", copied)

    @staticmethod
    def _merge_extension_list(
        summary: Dict[str, Any], field: str, values: List[Any]
    ) -> List[str]:
        """Merge values into summary[field] while preserving stable order."""

        if not isinstance(summary, dict):
            return []

        ordered: List[str] = []
        seen: set[str] = set()

        existing = summary.get(field)
        if isinstance(existing, list):
            for item in existing:
                item_str = str(item).strip()
                if not item_str or item_str in seen:
                    continue
                ordered.append(item_str)
                seen.add(item_str)

        for value in values or []:
            item_str = str(value).strip()
            if not item_str or item_str in seen:
                continue
            ordered.append(item_str)
            seen.add(item_str)

        if ordered:
            summary[field] = ordered
        else:
            summary.pop(field, None)

        return ordered

    async def _yield_stream_items(
        self, payload: ClientEvent | Message
    ) -> AsyncGenerator[Any, None]:
        """Normalize streaming payloads to legacy-compatible objects."""
        if isinstance(payload, Message):
            yield payload
            return

        task, update = payload
        if update is not None:
            yield update
        else:
            yield task

    def _extract_text_from_payload(
        self,
        payload: ClientEvent | Message,
    ) -> Optional[str]:
        """Extract human-readable text from a client payload."""
        if isinstance(payload, Message):
            return self._extract_text_from_message(payload)

        task, update = payload
        if update is not None:
            if isinstance(update, TaskStatusUpdateEvent):
                return self._extract_text_from_status(update.status)
            if isinstance(update, TaskArtifactUpdateEvent):
                return self._extract_text_from_artifact(update.artifact)
        return self._extract_text_from_task(task)

    @staticmethod
    def _extract_text_from_message(message: Optional[Message]) -> Optional[str]:
        if message is None:
            return None
        for part in getattr(message, "parts", []) or []:
            text = IIAgentA2AClient._extract_text_from_part(part)
            if text:
                return text
        return None

    @staticmethod
    def _extract_text_from_part(part: Part | Dict[str, Any]) -> Optional[str]:
        if isinstance(part, dict):
            text = part.get("text")
            if text:
                return str(text)
            root = part.get("root")
            if root and hasattr(root, "text"):
                candidate = getattr(root, "text", None)
                if candidate:
                    return str(candidate)
            return None

        root = getattr(part, "root", None)
        if root is None:
            return None
        if isinstance(root, TextPart):
            return str(root.text) if root.text else None
        if hasattr(root, "text"):
            candidate = getattr(root, "text", None)
            if candidate:
                return str(candidate)
        if hasattr(root, "data"):
            candidate = getattr(root, "data", None)
            if candidate:
                return str(candidate)
        return None

    @staticmethod
    def _extract_text_from_status(status: TaskStatus | None) -> Optional[str]:
        if status is None:
            return None
        return IIAgentA2AClient._extract_text_from_message(
            getattr(status, "message", None)
        )

    @staticmethod
    def _extract_text_from_artifact(artifact: Optional[Artifact]) -> Optional[str]:
        if artifact is None:
            return None
        for part in getattr(artifact, "parts", []) or []:
            text = IIAgentA2AClient._extract_text_from_part(part)
            if text:
                return text
        return None

    def _extract_text_from_task(self, task: Task) -> Optional[str]:
        text = self._extract_text_from_status(getattr(task, "status", None))
        if text:
            return text

        for artifact in getattr(task, "artifacts", []) or []:
            text = self._extract_text_from_artifact(artifact)
            if text:
                return text

        if task.history:
            for message in reversed(task.history):
                text = self._extract_text_from_message(message)
                if text:
                    return text
        return None

    def _format_error(self, message: str) -> Dict[str, Any]:
        return {
            "content": f"Error: {message}",
            "user_display_content": f"A2A agent call failed: {message}",
            "success": False,
            "agent_url": self.agent_url,
        }

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Return a shared AsyncClient instance."""
        if self._httpx_client and not self._httpx_client.is_closed:
            return self._httpx_client

        headers = self._DEFAULT_HEADERS.copy()
        headers.update(self._custom_headers)

        self._httpx_client = httpx.AsyncClient(
            timeout=self._timeout,
            headers=headers,
            limits=self._limits,
        )
        return self._httpx_client

    def get_last_response_extensions(self) -> Optional[Dict[str, Any]]:
        """Return the last captured extension negotiation summary."""
        if not self._last_response_extensions:
            return None
        return dict(self._last_response_extensions)

    def _store_response_extensions(
        self,
        context: ClientCallContext,
        result: Optional[Dict[str, Any]],
    ) -> None:
        """Collect extension data from the call context and attach if present."""
        state = context.state.setdefault(ExtensionsHeaderInterceptor._STATE_KEY, {})
        if not isinstance(state, dict):
            state = {}
            context.state[ExtensionsHeaderInterceptor._STATE_KEY] = state

        server_summary = state.get("server_summary")
        summary: Dict[str, Any] = (
            copy.deepcopy(server_summary) if isinstance(server_summary, dict) else {}
        )

        requested = list(state.get("requested") or [])
        activated = list(state.get("activated") or [])

        requested_list = self._merge_extension_list(summary, "requested", requested)
        activated_list = self._merge_extension_list(summary, "activated", activated)
        if not activated_list:
            active_from_server = summary.get("active")
            if isinstance(active_from_server, list):
                activated_list = self._merge_extension_list(
                    summary, "activated", active_from_server
                )

        missing = [ext for ext in requested_list if ext not in activated_list]
        self._merge_extension_list(summary, "missing", missing)

        if not summary:
            return

        snapshot = copy.deepcopy(summary)
        state["snapshot"] = snapshot

        if result is not None:
            result.setdefault("extensions", copy.deepcopy(summary))
        self._last_response_extensions = copy.deepcopy(summary)

    def _build_timeout(self, timeout_seconds: Optional[float]) -> httpx.Timeout:
        """Construct the timeout used for outbound requests."""
        resolved_seconds = self._resolve_timeout_seconds(timeout_seconds)
        return httpx.Timeout(
            timeout=None,
            connect=10.0,
            read=resolved_seconds,
            write=resolved_seconds,
            pool=10.0,
        )

    def _resolve_timeout_seconds(self, provided: Optional[float]) -> float:
        """Resolve final timeout seconds using provided value or environment defaults."""
        if provided is not None:
            try:
                value = float(provided)
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid timeout_seconds=%s for %s; falling back to defaults",
                    provided,
                    self.agent_url,
                )
            else:
                if value > 0:
                    return value
                logger.warning(
                    "Non-positive timeout_seconds=%s for %s; falling back to defaults",
                    provided,
                    self.agent_url,
                )

        env_value = os.getenv("A2A_AGENT_DEFAULT_TIMEOUT_SECONDS")
        if env_value:
            try:
                value = float(env_value)
            except ValueError:
                logger.warning(
                    "Invalid A2A_AGENT_DEFAULT_TIMEOUT_SECONDS=%s; using fallback value",
                    env_value,
                )
            else:
                if value > 0:
                    return value
                logger.warning(
                    "Non-positive A2A_AGENT_DEFAULT_TIMEOUT_SECONDS=%s; using fallback value",
                    env_value,
                )

        # Default to a 5-minute read/write timeout.
        return 300.0

    @staticmethod
    def _sanitize_headers(headers: Optional[Mapping[str, Any]]) -> Dict[str, str]:
        if not headers:
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
    def _derive_card_base_url(url: str) -> str:
        suffixes = ("/.well-known/agent.json", "/.well-known/agent-card.json")
        for suffix in suffixes:
            if url.endswith(suffix):
                base = url[: -len(suffix)]
                return base or url
        return url
