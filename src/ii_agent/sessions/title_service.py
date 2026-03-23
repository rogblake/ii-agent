"""Service for generating semantic session titles via LLM with truncation fallback."""

from __future__ import annotations

import asyncio
import logging
from openai import AsyncOpenAI
from pydantic import SecretStr

from ii_agent.billing.types import BillingContextValue, BillingScope
from ii_agent.chat.types import MessageRole, TextContent
from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.core.llm.execution_service import LLMBillingContext, LLMExecutionService
from ii_agent.sessions.title_config import SessionTitleConfig

logger = logging.getLogger(__name__)

TITLE_PENDING_KEY = "title_pending"

_SYSTEM_PROMPT = (
    "Generate a short, descriptive title (max 80 characters) for a conversation "
    "that starts with the following user message. Return only the title text, "
    "no quotes, no punctuation wrapping."
)


class SessionTitleService:
    """Generates semantic session titles using an LLM, with truncation fallback."""

    def __init__(
        self,
        config: SessionTitleConfig,
        llm_execution_service: LLMExecutionService | None = None,
    ) -> None:
        self._config = config
        self._llm_execution_service = llm_execution_service
        self._client: AsyncOpenAI | None = None
        if config.openai_api_key and config.enabled:
            if llm_execution_service is None:
                self._client = AsyncOpenAI(api_key=config.openai_api_key)
            else:
                # Keep a simple truthy marker so existing pending-title logic
                # still treats semantic titling as available.
                self._client = object()  # type: ignore[assignment]

    def _should_generate_semantic_title(self, query: str) -> bool:
        """Return whether the query should use LLM title generation."""
        return bool(self._client and len(query) >= self._config.semantic_min_query_length)

    def build_initial_title(
        self,
        query: str,
        max_length: int = 80,
    ) -> tuple[str | None, bool]:
        """Return the initial persisted title and whether async generation is pending."""
        stripped = query.strip()
        if not stripped:
            return "Untitled", False

        if self._should_generate_semantic_title(stripped):
            return None, True

        return self._truncate(stripped, max_length), False

    @staticmethod
    def is_title_pending(metadata: dict | None) -> bool:
        """Return whether title generation is still pending."""
        if not metadata:
            return False
        return bool(metadata.get(TITLE_PENDING_KEY))

    @staticmethod
    def set_title_pending(metadata: dict | None, pending: bool) -> dict | None:
        """Return updated session metadata with the title pending flag applied."""
        updated = dict(metadata or {})
        if pending:
            updated[TITLE_PENDING_KEY] = True
        else:
            updated.pop(TITLE_PENDING_KEY, None)
        return updated or None

    async def generate_title(
        self,
        query: str,
        max_length: int = 80,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        app_kind: str = "chat",
    ) -> str:
        """Generate a semantic title for the given user query.

        Falls back to simple truncation when the LLM is unavailable or fails.
        """
        stripped = query.strip()
        if not stripped:
            return "Untitled"

        if not self._should_generate_semantic_title(stripped):
            return self._truncate(stripped, max_length)

        try:
            title = await asyncio.wait_for(
                self._call_llm(
                    stripped,
                    session_id=session_id,
                    user_id=user_id,
                    app_kind=app_kind,
                ),
                timeout=self._config.timeout,
            )
            if not title or not title.strip():
                return self._truncate(stripped, max_length)
            return title.strip()[:max_length]
        except Exception:
            logger.warning(
                "LLM title generation failed, falling back to truncation",
                exc_info=True,
            )
            return self._truncate(stripped, max_length)

    def schedule_title_update(
        self,
        session_id: str,
        query: str,
        max_length: int = 80,
        *,
        user_id: str,
        app_kind: str,
    ) -> None:
        """Fire-and-forget: generate an LLM title in the background and update the DB.

        The caller should mark the session title as pending before calling this
        method so the generated title can replace it asynchronously.
        """
        stripped = query.strip()
        if not stripped or not self._should_generate_semantic_title(stripped):
            return  # No LLM client — truncation fallback is already set by caller
        asyncio.create_task(
            self._background_title_update(
                session_id=session_id,
                user_id=user_id,
                app_kind=app_kind,
                query=stripped,
                max_length=max_length,
            ),
            name=f"title-update-{session_id}",
        )

    async def _background_title_update(
        self,
        *,
        session_id: str,
        user_id: str,
        app_kind: str,
        query: str,
        max_length: int,
    ) -> None:
        """Generate a title via LLM and persist it to the session row."""
        fallback_title = self._truncate(query, max_length)
        try:
            title = await self.generate_title(
                query,
                max_length,
                session_id=session_id,
                user_id=user_id,
                app_kind=app_kind,
            )
        except Exception:
            logger.warning(
                "Background title generation failed for session %s",
                session_id,
                exc_info=True,
            )
            title = fallback_title

        try:
            persisted = await self._persist_title_update(session_id, title)
            if persisted:
                logger.info(
                    "Background title update for session %s: %s",
                    session_id,
                    title,
                )
            return
        except Exception:
            logger.warning(
                "Background title persistence failed for session %s; "
                "retrying with truncation fallback",
                session_id,
                exc_info=True,
            )

        try:
            persisted = await self._persist_title_update(session_id, fallback_title)
            if persisted:
                logger.warning(
                    "Recovered pending title state for session %s with truncation fallback",
                    session_id,
                )
        except Exception:
            logger.error(
                "Failed to recover pending title state for session %s",
                session_id,
                exc_info=True,
            )

    async def _persist_title_update(self, session_id: str, title: str) -> bool:
        """Persist a resolved title and clear the pending flag."""
        from ii_agent.core.db.manager import get_db_session_local
        from ii_agent.sessions.repository import SessionRepository

        repo = SessionRepository()
        async with get_db_session_local() as db:
            session = await repo.get_by_id(db, session_id)
            if not session or not self.is_title_pending(session.session_metadata):
                return False
            session.name = title
            session.session_metadata = self.set_title_pending(
                session.session_metadata,
                False,
            )
            return True

    async def _call_llm(
        self,
        query: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        app_kind: str = "chat",
    ) -> str:
        """Call the OpenAI API to generate a title."""
        if (
            self._llm_execution_service is not None
            and session_id is not None
            and user_id is not None
        ):
            llm_config = LLMConfig(
                model=self._config.model,
                api_key=SecretStr(self._config.openai_api_key)
                if self._config.openai_api_key
                else None,
                api_type=APITypes.OPENAI,
                config_type="system",
            )
            client = self._llm_execution_service.create_client(llm_config)
            messages = [
                self._llm_execution_service.new_message(
                    role=MessageRole.SYSTEM,
                    session_id=session_id,
                    parts=[TextContent(text=_SYSTEM_PROMPT)],
                ),
                self._llm_execution_service.new_message(
                    role=MessageRole.USER,
                    session_id=session_id,
                    parts=[TextContent(text=query)],
                ),
            ]
            response = await self._llm_execution_service.send_once(
                client=client,
                messages=messages,
                billing_context=LLMBillingContext(
                    scope=BillingScope.for_session(
                        user_id=user_id,
                        app_kind=app_kind,
                        session_id=session_id,
                        billing_context=BillingContextValue.SESSION_TITLE,
                    ),
                    llm_config=llm_config,
                    model_id=llm_config.model,
                    requested_output_token_cap=self._config.max_tokens,
                ),
                usage_key=f"session_title:{session_id}",
            )
            if isinstance(response.content, list):
                return self._llm_execution_service.extract_text_content(response.content)
            return str(response.content or "")

        if not isinstance(self._client, AsyncOpenAI):
            raise RuntimeError("Session title LLM client unavailable")

        response = await self._client.responses.create(
            model=self._config.model,
            instructions=_SYSTEM_PROMPT,
            input=query,
            max_output_tokens=self._config.max_tokens,
            reasoning={"effort": "low"},
        )
        return response.output_text

    @staticmethod
    def _truncate(query: str, max_length: int) -> str:
        """Truncate a query string to use as a session title."""
        truncated = query[:max_length].strip()
        if len(query) > max_length:
            truncated += "..."
        return truncated
