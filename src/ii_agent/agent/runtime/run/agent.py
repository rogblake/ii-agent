from dataclasses import asdict, dataclass, field
from enum import Enum
from time import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Union

from pydantic import BaseModel

from ii_agent.agent.runtime.media import Audio, File, Image, Video
from ii_agent.agent.runtime.models.message import Citations, Message
from ii_agent.agent.runtime.models.metrics import Metrics
from ii_agent.agent.types import Provider
from ii_agent.agent.runtime.models.response import ToolExecution
from ii_agent.agent.runtime.run.base import BaseRunOutputEvent, MessageReferences, RunStatus
from ii_agent.agent.runtime.run.requirement import RunRequirement
from ii_agent.agent.sandboxes.schemas import SandboxInfo
from ii_agent.core.logger import logger
from ii_agent.agent.runtime.utils.media import (
    reconstruct_audio_list,
    reconstruct_files,
    reconstruct_images,
    reconstruct_response_audio,
    reconstruct_videos,
)

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agent_sessions.summary import AgentSummary


@dataclass
class RunInput:
    """Container for the raw input data passed to Agent.run().

    This captures the original input exactly as provided by the user,
    separate from the processed messages that go to the model.

    Attributes:
        input_content: The literal input message/content passed to run()
        images: Images directly passed to run()
        videos: Videos directly passed to run()
        audios: Audio files directly passed to run()
        files: Files directly passed to run()
    """

    input_content: Union[str, List, Dict, Message, BaseModel, List[Message]]
    images: Optional[Sequence[Image]] = None
    videos: Optional[Sequence[Video]] = None
    audios: Optional[Sequence[Audio]] = None
    files: Optional[Sequence[File]] = None

    def contains_media(self) -> bool:
        """Check if any media is present in the RunInput"""
        return bool(
            (self.images and len(self.images) > 0)
            or (self.videos and len(self.videos) > 0)
            or (self.audios and len(self.audios) > 0)
            or (self.files and len(self.files) > 0)
        )

    def input_content_string(self) -> str:
        import json

        if isinstance(self.input_content, (str)):
            return self.input_content
        elif isinstance(self.input_content, BaseModel):
            return self.input_content.model_dump_json(exclude_none=True)
        elif isinstance(self.input_content, Message):
            return json.dumps(self.input_content.to_dict())
        elif (
            isinstance(self.input_content, list)
            and self.input_content
            and isinstance(self.input_content[0], Message)
        ):
            return json.dumps([m.to_dict() for m in self.input_content])
        else:
            return str(self.input_content)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        result: Dict[str, Any] = {}

        if self.input_content is not None:
            if isinstance(self.input_content, (str)):
                result["input_content"] = self.input_content
            elif isinstance(self.input_content, BaseModel):
                result["input_content"] = self.input_content.model_dump(exclude_none=True)
            elif isinstance(self.input_content, Message):
                result["input_content"] = self.input_content.to_dict()

            # Handle input_content provided as a list of Message objects
            elif (
                isinstance(self.input_content, list)
                and self.input_content
                and isinstance(self.input_content[0], Message)
            ):
                result["input_content"] = [m.to_dict() for m in self.input_content]

            # Handle input_content provided as a list of dicts
            elif (
                isinstance(self.input_content, list)
                and self.input_content
                and isinstance(self.input_content[0], dict)
            ):
                for content in self.input_content:
                    # Handle media input
                    if isinstance(content, dict):
                        if content.get("images"):
                            content["images"] = [
                                img.to_dict() if isinstance(img, Image) else img
                                for img in content["images"]
                            ]
                        if content.get("videos"):
                            content["videos"] = [
                                vid.to_dict() if isinstance(vid, Video) else vid
                                for vid in content["videos"]
                            ]
                        if content.get("audios"):
                            content["audios"] = [
                                aud.to_dict() if isinstance(aud, Audio) else aud
                                for aud in content["audios"]
                            ]
                        if content.get("files"):
                            content["files"] = [
                                file.to_dict() if isinstance(file, File) else file
                                for file in content["files"]
                            ]
                result["input_content"] = self.input_content
            else:
                result["input_content"] = self.input_content

        if self.images:
            result["images"] = [img.to_dict() for img in self.images]
        if self.videos:
            result["videos"] = [vid.to_dict() for vid in self.videos]
        if self.audios:
            result["audios"] = [aud.to_dict() for aud in self.audios]
        if self.files:
            result["files"] = [file.to_dict() for file in self.files]

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunInput":
        """Create RunInput from dictionary"""
        images = reconstruct_images(data.get("images"))
        videos = reconstruct_videos(data.get("videos"))
        audios = reconstruct_audio_list(data.get("audios"))
        files = reconstruct_files(data.get("files"))

        return cls(
            input_content=data.get("input_content", ""),
            images=images,
            videos=videos,
            audios=audios,
            files=files,
        )


class RunEvent(str, Enum):
    """Events that can be sent by the run() functions"""

    run_started = "RunStarted"
    run_content = "RunContent"
    run_content_completed = "RunContentCompleted"
    run_content_delta = "RunContentDelta"
    run_completed = "RunCompleted"
    run_error = "RunError"
    run_cancelled = "RunCancelled"

    run_paused = "RunPaused"
    run_continued = "RunContinued"

    pre_hook_started = "PreHookStarted"
    pre_hook_completed = "PreHookCompleted"

    post_hook_started = "PostHookStarted"
    post_hook_completed = "PostHookCompleted"

    tool_call_started = "ToolCallStarted"
    tool_call_completed = "ToolCallCompleted"

    reasoning_started = "ReasoningStarted"
    reasoning_delta = "ReasoningDelta"
    reasoning_completed = "ReasoningCompleted"

    memory_update_started = "MemoryUpdateStarted"
    memory_update_completed = "MemoryUpdateCompleted"

    session_summary_started = "SessionSummaryStarted"
    session_summary_completed = "SessionSummaryCompleted"

    parser_model_response_started = "ParserModelResponseStarted"
    parser_model_response_completed = "ParserModelResponseCompleted"

    output_model_response_started = "OutputModelResponseStarted"
    output_model_response_completed = "OutputModelResponseCompleted"

    sandbox_initialized = "SandboxInitialized"
    custom_event = "CustomEvent"


@dataclass
class BaseAgentRunEvent(BaseRunOutputEvent):
    created_at: int = field(default_factory=lambda: int(time()))
    event: str = ""
    agent_id: str = ""
    agent_name: str = ""
    run_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    session_id: Optional[str] = None

    # Model info for all events
    model: Optional[str] = None
    model_provider: Optional[Provider] = None

    tools: Optional[List[ToolExecution]] = None

    # For backwards compatibility
    content: Optional[Any] = None

    # Sub-agent identification
    delegated_from: Optional[str] = None  # Parent agent name
    is_sub_agent_event: bool = False  # Quick check flag

    @property
    def tools_requiring_confirmation(self):
        return [t for t in self.tools if t.requires_confirmation] if self.tools else []

    @property
    def tools_requiring_user_input(self):
        return [t for t in self.tools if t.requires_user_input] if self.tools else []

    @property
    def tools_awaiting_external_execution(self):
        return [t for t in self.tools if t.external_execution_required] if self.tools else []


@dataclass
class RunStartedEvent(BaseAgentRunEvent):
    """Event sent when the run starts"""

    event: str = RunEvent.run_started.value


@dataclass
class RunContentEvent(BaseAgentRunEvent):
    """Main event for each delta of the RunOutput"""

    event: str = RunEvent.run_content.value
    content: Optional[Any] = None
    content_type: str = "str"
    reasoning_content: Optional[str] = None
    model_provider_data: Optional[Dict[str, Any]] = None
    citations: Optional[Citations] = None
    response_audio: Optional[Audio] = None  # Model audio response
    image: Optional[Image] = None  # Image attached to the response
    references: Optional[List[MessageReferences]] = None
    additional_input: Optional[List[Message]] = None
    reasoning_messages: Optional[List[Message]] = None


@dataclass
class RunContentCompletedEvent(BaseAgentRunEvent):
    event: str = RunEvent.run_content_completed.value


@dataclass
class SandboxInitializedEvent(BaseAgentRunEvent):
    event: str = RunEvent.sandbox_initialized.value
    sandbox_info: Optional[SandboxInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        _dict = super().to_dict()
        if self.sandbox_info:
            _dict["sandbox_info"] = self.sandbox_info.model_dump(mode="json", exclude_none=True)
        return _dict


@dataclass
class RunContentDeltaEvent(BaseAgentRunEvent):
    event: str = RunEvent.run_content_delta.value
    content: Optional[Any] = None
    content_type: str = "str"


@dataclass
class RunCompletedEvent(BaseAgentRunEvent):
    event: str = RunEvent.run_completed.value
    content: Optional[Any] = None
    content_type: str = "str"
    reasoning_content: Optional[str] = None
    citations: Optional[Citations] = None
    model_provider_data: Optional[Dict[str, Any]] = None
    images: Optional[List[Image]] = None  # Images attached to the response
    videos: Optional[List[Video]] = None  # Videos attached to the response
    audio: Optional[List[Audio]] = None  # Audio attached to the response
    response_audio: Optional[Audio] = None  # Model audio response
    references: Optional[List[MessageReferences]] = None
    additional_input: Optional[List[Message]] = None
    reasoning_messages: Optional[List[Message]] = None
    metadata: Optional[Dict[str, Any]] = None
    metrics: Optional[Metrics] = None
    session_state: Optional[Dict[str, Any]] = None
    status: Optional[RunStatus] = None


@dataclass
class RunPausedEvent(BaseAgentRunEvent):
    event: str = RunEvent.run_paused.value
    tools: Optional[List[ToolExecution]] = None
    requirements: Optional[List[RunRequirement]] = None

    @property
    def is_paused(self):
        return True

    @property
    def active_requirements(self) -> List[RunRequirement]:
        if not self.requirements:
            return []
        return [requirement for requirement in self.requirements if not requirement.is_resolved()]

    def to_dict(self) -> Dict[str, Any]:
        _dict = super().to_dict()
        if self.requirements is not None:
            _dict["requirements"] = [r.to_dict() for r in self.requirements]
        return _dict


@dataclass
class RunContinuedEvent(BaseAgentRunEvent):
    event: str = RunEvent.run_continued.value


@dataclass
class RunErrorEvent(BaseAgentRunEvent):
    event: str = RunEvent.run_error.value
    content: Optional[str] = None

    # From exceptions
    error_type: Optional[str] = None
    error_id: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


@dataclass
class RunCancelledEvent(BaseAgentRunEvent):
    event: str = RunEvent.run_cancelled.value
    reason: Optional[str] = None

    @property
    def is_cancelled(self):
        return True


@dataclass
class PreHookStartedEvent(BaseAgentRunEvent):
    event: str = RunEvent.pre_hook_started.value
    pre_hook_name: Optional[str] = None
    run_input: Optional[RunInput] = None


@dataclass
class PreHookCompletedEvent(BaseAgentRunEvent):
    event: str = RunEvent.pre_hook_completed.value
    pre_hook_name: Optional[str] = None
    run_input: Optional[RunInput] = None


@dataclass
class PostHookStartedEvent(BaseAgentRunEvent):
    event: str = RunEvent.post_hook_started.value
    post_hook_name: Optional[str] = None


@dataclass
class PostHookCompletedEvent(BaseAgentRunEvent):
    event: str = RunEvent.post_hook_completed.value
    post_hook_name: Optional[str] = None


@dataclass
class MemoryUpdateStartedEvent(BaseAgentRunEvent):
    event: str = RunEvent.memory_update_started.value


@dataclass
class MemoryUpdateCompletedEvent(BaseAgentRunEvent):
    event: str = RunEvent.memory_update_completed.value


@dataclass
class AgentSummaryStartedEvent(BaseAgentRunEvent):
    event: str = RunEvent.session_summary_started.value


@dataclass
class AgentSummaryCompletedEvent(BaseAgentRunEvent):
    event: str = RunEvent.session_summary_completed.value
    session_summary: Optional["AgentSummary"] = None


@dataclass
class ReasoningStartedEvent(BaseAgentRunEvent):
    event: str = RunEvent.reasoning_started.value


@dataclass
class ReasoningDeltaEvent(BaseAgentRunEvent):
    """Event for streaming reasoning/thinking content deltas.

    This event is emitted during streaming when the model produces
    reasoning/thinking content (e.g., OpenAI o-series models, Anthropic extended thinking).

    Attributes:
        reasoning_content: The reasoning content delta (chunk)
        redacted_reasoning_content: Redacted reasoning content (for models that support it)
        is_redacted: Whether the reasoning content is redacted/encrypted
        provider_data: Provider-specific metadata (e.g., signature for Anthropic, encrypted_content for OpenAI ZDR)
    """

    event: str = RunEvent.reasoning_delta.value
    reasoning_content: Optional[str] = None
    redacted_reasoning_content: Optional[str] = None
    is_redacted: bool = False
    provider_data: Optional[Dict[str, Any]] = None


@dataclass
class ReasoningCompletedEvent(BaseAgentRunEvent):
    """Event emitted when reasoning/thinking is completed.

    This event contains the final reasoning content summary and any provider-specific data
    needed for subsequent requests (e.g., encrypted reasoning for OpenAI ZDR mode).

    Attributes:
        content: The final reasoning content (summary or full)
        content_type: Type of the content (default: "str")
        provider_data: Provider-specific metadata for conversation continuity
    """

    event: str = RunEvent.reasoning_completed.value
    content: Optional[Any] = None
    content_type: str = "str"
    provider_data: Optional[Dict[str, Any]] = None


@dataclass
class ToolCallStartedEvent(BaseAgentRunEvent):
    event: str = RunEvent.tool_call_started.value
    tool: Optional[ToolExecution] = None


@dataclass
class ToolCallCompletedEvent(BaseAgentRunEvent):
    event: str = RunEvent.tool_call_completed.value
    tool: Optional[ToolExecution] = None
    content: Optional[Any] = None
    images: Optional[List[Image]] = None  # Images produced by the tool call
    videos: Optional[List[Video]] = None  # Videos produced by the tool call
    audio: Optional[List[Audio]] = None  # Audio produced by the tool call


@dataclass
class ParserModelResponseStartedEvent(BaseAgentRunEvent):
    event: str = RunEvent.parser_model_response_started.value


@dataclass
class ParserModelResponseCompletedEvent(BaseAgentRunEvent):
    event: str = RunEvent.parser_model_response_completed.value


@dataclass
class OutputModelResponseStartedEvent(BaseAgentRunEvent):
    event: str = RunEvent.output_model_response_started.value


@dataclass
class OutputModelResponseCompletedEvent(BaseAgentRunEvent):
    event: str = RunEvent.output_model_response_completed.value


@dataclass
class CustomEvent(BaseAgentRunEvent):
    event: str = RunEvent.custom_event.value

    def __init__(self, **kwargs):
        # Store arbitrary attributes directly on the instance
        for key, value in kwargs.items():
            setattr(self, key, value)


RunOutputEvent = Union[
    RunStartedEvent,
    RunContentEvent,
    RunContentDeltaEvent,
    RunContentCompletedEvent,
    RunCompletedEvent,
    RunErrorEvent,
    RunCancelledEvent,
    RunPausedEvent,
    RunContinuedEvent,
    PreHookStartedEvent,
    PreHookCompletedEvent,
    PostHookStartedEvent,
    PostHookCompletedEvent,
    ReasoningStartedEvent,
    ReasoningDeltaEvent,
    ReasoningCompletedEvent,
    MemoryUpdateStartedEvent,
    MemoryUpdateCompletedEvent,
    AgentSummaryStartedEvent,
    AgentSummaryCompletedEvent,
    ToolCallStartedEvent,
    ToolCallCompletedEvent,
    ParserModelResponseStartedEvent,
    ParserModelResponseCompletedEvent,
    OutputModelResponseStartedEvent,
    OutputModelResponseCompletedEvent,
    SandboxInitializedEvent,
    CustomEvent,
]


# Map event string to dataclass
RUN_EVENT_TYPE_REGISTRY = {
    RunEvent.run_started.value: RunStartedEvent,
    RunEvent.run_content.value: RunContentEvent,
    RunEvent.run_content_completed.value: RunContentCompletedEvent,
    RunEvent.run_content_delta.value: RunContentDeltaEvent,
    RunEvent.run_completed.value: RunCompletedEvent,
    RunEvent.run_error.value: RunErrorEvent,
    RunEvent.run_cancelled.value: RunCancelledEvent,
    RunEvent.run_paused.value: RunPausedEvent,
    RunEvent.run_continued.value: RunContinuedEvent,
    RunEvent.pre_hook_started.value: PreHookStartedEvent,
    RunEvent.pre_hook_completed.value: PreHookCompletedEvent,
    RunEvent.post_hook_started.value: PostHookStartedEvent,
    RunEvent.post_hook_completed.value: PostHookCompletedEvent,
    RunEvent.reasoning_started.value: ReasoningStartedEvent,
    RunEvent.reasoning_delta.value: ReasoningDeltaEvent,
    RunEvent.reasoning_completed.value: ReasoningCompletedEvent,
    RunEvent.memory_update_started.value: MemoryUpdateStartedEvent,
    RunEvent.memory_update_completed.value: MemoryUpdateCompletedEvent,
    RunEvent.session_summary_started.value: AgentSummaryStartedEvent,
    RunEvent.session_summary_completed.value: AgentSummaryCompletedEvent,
    RunEvent.tool_call_started.value: ToolCallStartedEvent,
    RunEvent.tool_call_completed.value: ToolCallCompletedEvent,
    RunEvent.parser_model_response_started.value: ParserModelResponseStartedEvent,
    RunEvent.parser_model_response_completed.value: ParserModelResponseCompletedEvent,
    RunEvent.output_model_response_started.value: OutputModelResponseStartedEvent,
    RunEvent.output_model_response_completed.value: OutputModelResponseCompletedEvent,
    RunEvent.sandbox_initialized.value: SandboxInitializedEvent,
    RunEvent.custom_event.value: CustomEvent,
}


def run_output_event_from_dict(data: dict) -> BaseRunOutputEvent:
    event_type = data.get("event", "")
    cls = RUN_EVENT_TYPE_REGISTRY.get(event_type)
    if not cls:
        raise ValueError(f"Unknown event type: {event_type}")
    return cls.from_dict(data)  # type: ignore


@dataclass
class RunOutput:
    """Response returned by Agent.run()"""

    # Required fields (must be provided at creation)
    run_id: str
    session_id: str
    user_id: str
    model: str
    agent_name: str
    # Optional fields
    parent_run_id: Optional[str] = None
    agent_id: Optional[str] = None

    # Input media and messages from user
    input: Optional[RunInput] = None

    content: Optional[Any] = None
    content_type: str = "str"

    reasoning_content: Optional[str] = None
    reasoning_messages: Optional[List[Message]] = None

    model_provider_data: Optional[Dict[str, Any]] = None

    model_provider: Optional[str] = None
    messages: Optional[List[Message]] = None
    metrics: Optional[Metrics] = None
    additional_input: Optional[List[Message]] = None

    tools: Optional[List[ToolExecution]] = None

    images: Optional[List[Image]] = None  # Images attached to the response
    videos: Optional[List[Video]] = None  # Videos attached to the response
    audio: Optional[List[Audio]] = None  # Audio attached to the response
    files: Optional[List[File]] = None  # Files attached to the response
    response_audio: Optional[Audio] = None  # Model audio response

    citations: Optional[Citations] = None
    references: Optional[List[MessageReferences]] = None

    metadata: Optional[Dict[str, Any]] = None
    session_state: Optional[Dict[str, Any]] = None

    created_at: int = field(default_factory=lambda: int(time()))

    status: RunStatus = RunStatus.RUNNING
    summary: Optional["AgentSummary"] = None
    # User control flow (HITL) requirements to continue a run when paused, in order of arrival
    requirements: Optional[list[RunRequirement]] = None
    error_message: Optional[str] = None

    # Sub-agent support fields
    delegated_from: Optional[str] = None  # Parent agent name (for identification)
    member_responses: Optional[List["RunOutput"]] = None  # Sub-agent responses

    @property
    def active_requirements(self) -> list[RunRequirement]:
        if not self.requirements:
            return []
        return [requirement for requirement in self.requirements if not requirement.is_resolved()]

    @property
    def is_paused(self):
        return self.status == RunStatus.PAUSED

    @property
    def is_cancelled(self):
        return self.status == RunStatus.ABORTED

    @property
    def tools_requiring_confirmation(self):
        return [t for t in self.tools if t.requires_confirmation] if self.tools else []

    @property
    def tools_requiring_user_input(self):
        return [t for t in self.tools if t.requires_user_input] if self.tools else []

    @property
    def tools_awaiting_external_execution(self):
        return [t for t in self.tools if t.external_execution_required] if self.tools else []

    @property
    def is_sub_agent_response(self) -> bool:
        """Check if this response is from a sub-agent."""
        return self.delegated_from is not None or self.parent_run_id is not None

    def add_member_run(self, run_response: "RunOutput") -> None:
        """Add a sub-agent's run response to member_responses.

        Also aggregates media from the sub-agent response.
        """
        if self.member_responses is None:
            self.member_responses = []
        self.member_responses.append(run_response)

        # Aggregate media from sub-agent
        if run_response.images:
            if self.images is None:
                self.images = []
            self.images.extend(run_response.images)

        if run_response.videos:
            if self.videos is None:
                self.videos = []
            self.videos.extend(run_response.videos)

        if run_response.audio:
            if self.audio is None:
                self.audio = []
            self.audio.extend(run_response.audio)

        if run_response.files:
            if self.files is None:
                self.files = []
            self.files.extend(run_response.files)

    def to_dict(self) -> Dict[str, Any]:
        _dict = {
            k: v
            for k, v in asdict(self).items()
            if v is not None
            and k
            not in [
                "messages",
                "metrics",
                "tools",
                "metadata",
                "images",
                "videos",
                "audio",
                "files",
                "response_audio",
                "input",
                "citations",
                "additional_input",
                "references",
                "error_message",
                "member_responses",
                "summary",
            ]
        }

        if self.metrics is not None:
            _dict["metrics"] = (
                self.metrics.to_dict() if isinstance(self.metrics, Metrics) else self.metrics
            )

        if self.status is not None:
            _dict["status"] = (
                self.status.value if isinstance(self.status, RunStatus) else self.status
            )

        if self.messages is not None:
            _dict["messages"] = [m.to_dict() for m in self.messages]

        if self.metadata is not None:
            _dict["metadata"] = self.metadata

        if self.additional_input is not None:
            _dict["additional_input"] = [m.to_dict() for m in self.additional_input]

        if self.reasoning_messages is not None:
            _dict["reasoning_messages"] = [m.to_dict() for m in self.reasoning_messages]

        if self.references is not None:
            _dict["references"] = [r.model_dump() for r in self.references]

        if self.summary is not None:
            _dict["summary"] = self.summary.to_dict()

        if self.images is not None:
            _dict["images"] = []
            for img in self.images:
                if isinstance(img, Image):
                    _dict["images"].append(img.to_dict())
                else:
                    _dict["images"].append(img)

        if self.videos is not None:
            _dict["videos"] = []
            for vid in self.videos:
                if isinstance(vid, Video):
                    _dict["videos"].append(vid.to_dict())
                else:
                    _dict["videos"].append(vid)

        if self.audio is not None:
            _dict["audio"] = []
            for aud in self.audio:
                if isinstance(aud, Audio):
                    _dict["audio"].append(aud.to_dict())
                else:
                    _dict["audio"].append(aud)

        if self.files is not None:
            _dict["files"] = []
            for file in self.files:
                if isinstance(file, File):
                    _dict["files"].append(file.to_dict())
                else:
                    _dict["files"].append(file)

        if self.response_audio is not None:
            if isinstance(self.response_audio, Audio):
                _dict["response_audio"] = self.response_audio.to_dict()
            else:
                _dict["response_audio"] = self.response_audio

        if self.citations is not None:
            if isinstance(self.citations, Citations):
                _dict["citations"] = self.citations.model_dump(exclude_none=True)
            else:
                _dict["citations"] = self.citations

        if self.content and isinstance(self.content, BaseModel):
            _dict["content"] = self.content.model_dump(exclude_none=True, mode="json")

        if self.tools is not None:
            _dict["tools"] = []
            for tool in self.tools:
                if isinstance(tool, ToolExecution):
                    _dict["tools"].append(tool.to_dict())
                else:
                    _dict["tools"].append(tool)

        if self.input is not None:
            _dict["input"] = self.input.to_dict()

        if self.member_responses is not None:
            _dict["member_responses"] = [r.to_dict() for r in self.member_responses]

        return _dict

    def to_json(self, separators=(", ", ": "), indent: Optional[int] = 2) -> str:
        import json

        try:
            _dict = self.to_dict()
        except Exception:
            logger.opt(exception=True).error("Failed to convert response to json")
            raise

        if indent is None:
            return json.dumps(_dict, separators=separators)
        else:
            return json.dumps(_dict, indent=indent, separators=separators)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunOutput":
        # Extract required fields first
        run_id = data.pop("run_id")
        session_id = data.pop("session_id")
        user_id = data.pop("user_id", "")
        model = data.pop("model")
        agent_name = data.pop("agent_name", "")

        # Pop events from data to ignore (events are stored separately in DB)
        data.pop("events", None)

        messages = data.pop("messages", None)
        messages = [Message.from_dict(message) for message in messages] if messages else None

        citations = data.pop("citations", None)
        citations = Citations.model_validate(citations) if citations else None

        tools = data.pop("tools", [])
        tools = [ToolExecution.from_dict(tool) for tool in tools] if tools else None

        images = reconstruct_images(data.pop("images", []))
        videos = reconstruct_videos(data.pop("videos", []))
        audio = reconstruct_audio_list(data.pop("audio", []))
        files = reconstruct_files(data.pop("files", []))
        response_audio = reconstruct_response_audio(data.pop("response_audio", None))

        # Handle both "input" (from to_dict) and "run_input" (from store.py) keys
        input_data = data.pop("input", None) or data.pop("run_input", None)
        input_obj = None
        if input_data:
            input_obj = RunInput.from_dict(input_data)

        metrics = data.pop("metrics", None)
        if metrics:
            metrics = Metrics(**metrics)

        additional_input = data.pop("additional_input", None)

        if additional_input is not None:
            additional_input = [Message.from_dict(message) for message in additional_input]

        reasoning_messages = data.pop("reasoning_messages", None)
        if reasoning_messages is not None:
            reasoning_messages = [Message.from_dict(message) for message in reasoning_messages]

        references = data.pop("references", None)
        if references is not None:
            references = [MessageReferences.model_validate(reference) for reference in references]

        # Handle member_responses (sub-agent responses)
        member_responses = data.pop("member_responses", None)
        if member_responses is not None:
            member_responses = [cls.from_dict(r) for r in member_responses]

        # Convert status string to RunStatus enum
        status = data.pop("status", None)
        if status is not None:
            if isinstance(status, str):
                try:
                    status = RunStatus(status)
                except ValueError:
                    status = RunStatus.COMPLETED
            elif not isinstance(status, RunStatus):
                status = RunStatus.COMPLETED

        # Filter data to only include fields that are actually defined in the RunOutput dataclass
        from dataclasses import fields

        supported_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in supported_fields}

        return cls(
            # Required fields
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            model=model,
            agent_name=agent_name,
            # Optional fields
            status=status or RunStatus.RUNNING,
            messages=messages,
            metrics=metrics,
            citations=citations,
            tools=tools,
            images=images,
            audio=audio,
            videos=videos,
            files=files,
            response_audio=response_audio,
            input=input_obj,
            additional_input=additional_input,
            reasoning_messages=reasoning_messages,
            references=references,
            member_responses=member_responses,
            **filtered_data,
        )

    def get_content_as_string(self, **kwargs) -> str:
        import json

        from pydantic import BaseModel

        if isinstance(self.content, str):
            return self.content
        elif isinstance(self.content, BaseModel):
            return self.content.model_dump_json(exclude_none=True, **kwargs)
        else:
            return json.dumps(self.content, **kwargs)
