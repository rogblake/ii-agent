from dataclasses import asdict, dataclass, field
from enum import Enum
from time import time
from typing import Any, Dict, List, Literal, Optional

from ii_agent.files.media import Audio, File, Image, Video
from ii_agent.agents.models.message import Citations
from ii_agent.agents.models.metrics import Metrics
from ii_agent.agents.sandboxes.schemas import SandboxInfo
from ii_agent.agents.tools.base import UserInputField


class ModelResponseEvent(str, Enum):
    """Events that can be sent by the model provider"""

    tool_call_paused = "ToolCallPaused"
    tool_call_started = "ToolCallStarted"
    tool_call_completed = "ToolCallCompleted"
    assistant_response = "AssistantResponse"


@dataclass
class ToolExecution:
    """Execution of a tool"""

    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_call_error: Optional[bool] = None
    result: Optional[Any] = None  # Can be str or ToolResult for websocket display
    metrics: Optional[Metrics] = None

    # Display metadata (for frontend rendering)
    display_name: Optional[str] = None  # Human-readable name for the tool
    tool_logo: Optional[str] = None  # URL for tool icon/logo

    # If True, the agent will stop executing after this tool call.
    stop_after_tool_call: bool = False

    created_at: int = field(default_factory=lambda: int(time()))

    # User control flow (HITL) fields
    requires_confirmation: Optional[bool] = None
    confirmed: Optional[bool] = None
    confirmation_note: Optional[str] = None

    requires_user_input: Optional[bool] = None
    user_input_schema: Optional[List[UserInputField]] = None
    answered: Optional[bool] = None

    external_execution_required: Optional[bool] = None
    sandbox: Optional[SandboxInfo] = None

    @property
    def is_paused(self) -> bool:
        return bool(
            self.requires_confirmation
            or self.requires_user_input
            or self.external_execution_required
        )

    def to_dict(self) -> Dict[str, Any]:
        _dict = asdict(self)
        if self.metrics is not None:
            _dict["metrics"] = self.metrics.to_dict()

        if self.user_input_schema is not None:
            _dict["user_input_schema"] = [field.to_dict() for field in self.user_input_schema]
        if self.sandbox is not None:
            _dict["sandbox"] = self.sandbox.model_dump(mode="json", exclude_none=True)

        # Handle BaseToolResult for serialization
        if self.result is not None:
            from pydantic import BaseModel

            if isinstance(self.result, BaseModel):
                _dict["result"] = self.result.model_dump(mode="json", exclude_none=True)
        return _dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolExecution":
        # Handle metrics - only create if present in data
        metrics_data = data.get("metrics")
        metrics = Metrics(**metrics_data) if metrics_data else None

        # Handle user_input_schema
        user_input_schema = None
        if "user_input_schema" in data and data["user_input_schema"]:
            user_input_schema = [
                UserInputField.from_dict(field) for field in data["user_input_schema"]
            ]

        # Handle created_at
        created_at = data.get("created_at", int(time()))

        return cls(
            tool_call_id=data.get("tool_call_id"),
            tool_name=data.get("tool_name"),
            tool_args=data.get("tool_args"),
            tool_call_error=data.get("tool_call_error"),
            result=data.get("result"),
            display_name=data.get("display_name"),
            tool_logo=data.get("tool_logo"),
            stop_after_tool_call=data.get("stop_after_tool_call", False),
            requires_confirmation=data.get("requires_confirmation"),
            confirmed=data.get("confirmed"),
            confirmation_note=data.get("confirmation_note"),
            requires_user_input=data.get("requires_user_input"),
            user_input_schema=user_input_schema,
            external_execution_required=data.get("external_execution_required"),
            answered=data.get("answered"),
            metrics=metrics,
            created_at=created_at,
        )


@dataclass
class ModelResponse:
    """Response from the model provider"""

    role: Optional[str] = None

    content: Optional[Any] = None
    parsed: Optional[Any] = None
    audio: Optional[Audio] = None

    # Unified media fields for LLM-generated and tool-generated media artifacts
    images: Optional[List[Image]] = None
    videos: Optional[List[Video]] = None
    audios: Optional[List[Audio]] = None
    files: Optional[List[File]] = None

    # Model tool calls
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    # Actual tool executions
    tool_executions: Optional[List[ToolExecution]] = field(default_factory=list)

    event: str = ModelResponseEvent.assistant_response.value

    provider_data: Optional[Dict[str, Any]] = None

    redacted_reasoning_content: Optional[str] = None

    reasoning_content: Optional[str] = None

    is_delta: bool = False

    delta_status: Optional[
        Literal["reasoning_started", "content_started", "reasoning_done", "content_done"]
    ] = None

    citations: Optional[Citations] = None

    response_usage: Optional[Metrics] = None

    created_at: int = int(time())

    extra: Optional[Dict[str, Any]] = None

    updated_session_state: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ModelResponse to dictionary for caching."""
        _dict = asdict(self)

        # Handle special serialization for audio
        if self.audio is not None:
            _dict["audio"] = self.audio.to_dict()

        # Handle lists of media objects
        if self.images is not None:
            _dict["images"] = [img.to_dict() for img in self.images]
        if self.videos is not None:
            _dict["videos"] = [vid.to_dict() for vid in self.videos]
        if self.audios is not None:
            _dict["audios"] = [aud.to_dict() for aud in self.audios]
        if self.files is not None:
            _dict["files"] = [f.to_dict() for f in self.files]

        # Handle tool executions
        if self.tool_executions is not None:
            _dict["tool_executions"] = [
                tool_execution.to_dict() for tool_execution in self.tool_executions
            ]

        # Handle response usage which might be a Pydantic BaseModel
        response_usage = _dict.pop("response_usage", None)
        if response_usage is not None:
            try:
                from pydantic import BaseModel

                if isinstance(response_usage, BaseModel):
                    _dict["response_usage"] = response_usage.model_dump()
                else:
                    _dict["response_usage"] = response_usage
            except ImportError:
                _dict["response_usage"] = response_usage

        return _dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelResponse":
        """Reconstruct ModelResponse from cached dictionary."""
        # Reconstruct media objects
        if data.get("audio"):
            data["audio"] = Audio(**data["audio"])

        if data.get("images"):
            data["images"] = [Image(**img) for img in data["images"]]
        if data.get("videos"):
            data["videos"] = [Video(**vid) for vid in data["videos"]]
        if data.get("audios"):
            data["audios"] = [Audio(**aud) for aud in data["audios"]]
        if data.get("files"):
            data["files"] = [File(**f) for f in data["files"]]

        # Reconstruct tool executions
        if data.get("tool_executions"):
            data["tool_executions"] = [
                ToolExecution.from_dict(te) for te in data["tool_executions"]
            ]

        # Reconstruct citations
        if data.get("citations") and isinstance(data["citations"], dict):
            data["citations"] = Citations(**data["citations"])

        # Reconstruct response usage (Metrics)
        if data.get("response_usage") and isinstance(data["response_usage"], dict):
            from ii_agent.agents.models.metrics import Metrics

            data["response_usage"] = Metrics(**data["response_usage"])

        return cls(**data)


class FileType(str, Enum):
    MP4 = "mp4"
    GIF = "gif"
    MP3 = "mp3"
    WAV = "wav"
