"""Shared billing identity and result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import enum
from typing import Any, Generic, TypeVar
from uuid import UUID

from ii_agent.billing.reservations.types import BillingQuote
from ii_agent.sessions.models import AppKind


class SubjectKind(str, enum.Enum):
    """Stable billing subject kinds."""

    SESSION = "session"
    USER = "user"


class BillingContextValue:
    """Canonical high-level origins for billable work."""

    UNKNOWN = "unknown"
    CHAT_LOOP = "chatloop"
    AGENT_LOOP = "agentloop"
    TOOL_CALL = "toolcall"
    STORYBOOK = "storybook"
    COUNCIL = "council"
    NANO_BANANA = "nanobanana"
    PROJECT_DESIGN = "projectdesign"
    FACTORY = "factory"
    ENHANCE_PROMPT = "enhanceprompt"
    SESSION_TITLE = "sessiontitle"

    @classmethod
    def default_for_app_kind(cls, app_kind: AppKind | str) -> str:
        value = app_kind.value if isinstance(app_kind, AppKind) else str(app_kind)
        if value == AppKind.CHAT.value:
            return cls.CHAT_LOOP
        if value == AppKind.AGENT.value:
            return cls.AGENT_LOOP
        return cls.UNKNOWN


@dataclass(frozen=True)
class BillingSubject:
    """The business object that owns a billable charge."""

    kind: SubjectKind
    id: str


@dataclass(frozen=True)
class BillingScope:
    """Canonical billing identity used across reserve/settle flows."""

    user_id: str
    app_kind: str
    subject: BillingSubject
    billing_context: str = BillingContextValue.UNKNOWN
    run_id: UUID | str | None = None

    @classmethod
    def for_subject(
        cls,
        *,
        user_id: str,
        app_kind: AppKind | str,
        subject_kind: SubjectKind,
        subject_id: str,
        billing_context: str,
        run_id: UUID | str | None = None,
    ) -> "BillingScope":
        return cls(
            user_id=user_id,
            app_kind=app_kind.value if isinstance(app_kind, AppKind) else str(app_kind),
            subject=BillingSubject(kind=subject_kind, id=subject_id),
            billing_context=billing_context,
            run_id=run_id,
        )

    @classmethod
    def for_session(
        cls,
        *,
        user_id: str,
        app_kind: AppKind | str,
        session_id: str,
        billing_context: str | None = None,
        run_id: UUID | str | None = None,
    ) -> "BillingScope":
        return cls.for_subject(
            user_id=user_id,
            app_kind=app_kind,
            subject_kind=SubjectKind.SESSION,
            subject_id=session_id,
            billing_context=billing_context or BillingContextValue.default_for_app_kind(app_kind),
            run_id=run_id,
        )

    @classmethod
    def for_user(
        cls,
        *,
        user_id: str,
        app_kind: AppKind | str,
        billing_context: str,
        run_id: UUID | str | None = None,
    ) -> "BillingScope":
        return cls.for_subject(
            user_id=user_id,
            app_kind=app_kind,
            subject_kind=SubjectKind.USER,
            subject_id=user_id,
            billing_context=billing_context,
            run_id=run_id,
        )

    @property
    def session_id(self) -> str | None:
        if self.subject.kind == SubjectKind.SESSION:
            return self.subject.id
        return None

    @property
    def subject_id(self) -> str:
        return self.subject.id

    def billing_metadata(self) -> dict[str, Any]:
        return {
            "app_kind": self.app_kind,
            "subject_kind": self.subject.kind.value,
            "subject_id": self.subject.id,
            "billing_context": self.billing_context,
        }

    def build_operation_key(self, namespace: str, operation_id: str) -> str:
        parts = [
            namespace,
            self.app_kind,
            self.billing_context,
            self.subject.kind.value,
            self.subject.id,
        ]
        if self.run_id is not None:
            parts.append(str(self.run_id))
        parts.append(operation_id)
        return ":".join(parts)


@dataclass(frozen=True)
class BillingReservationRequest:
    """Inputs required to create a durable reservation."""

    source_domain: str
    source_id: str
    billing_kind: str
    quote: BillingQuote | None
    idempotency_key: str
    model_id: str | None = None
    tool_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    output_token_cap: int | None = None


_T = TypeVar("_T")


@dataclass(frozen=True)
class BillingResult(Generic[_T]):
    """Provider result plus the final billable amount."""

    value: _T
    actual_usd: Decimal
    usage_payload: dict[str, Any] = field(default_factory=dict)
    actual_credits: Decimal | None = None
