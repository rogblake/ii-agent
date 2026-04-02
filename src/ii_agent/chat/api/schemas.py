"""Pydantic models for chat API HTTP requests/responses."""

from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from ii_agent.billing.schemas import TokenUsage
from ii_agent.chat.types import (
    CouncilPreferences,
    MediaPreferences,
    GitHubRepositoryContext,
    MediaReference,
    MessageRoleType,
    SessionStatusType,
)


class AdvancedModeReference(MediaReference):
    """Advanced mode reference with preview URL."""

    file_url: str | None = Field(
        None, description="Signed URL for previewing the uploaded reference image"
    )


class AdvancedModeState(BaseModel):
    """Advanced mode settings stored per chat session."""

    enabled: bool = Field(False, description="Whether advanced mode is enabled")
    references: list[AdvancedModeReference] = Field(
        default_factory=list,
        description="Stored reference images for advanced image generation",
    )


class AdvancedModeUpdateRequest(BaseModel):
    """Payload for updating advanced mode state."""

    enabled: bool = Field(..., description="Enable or disable advanced mode")
    references: list[MediaReference] | None = Field(
        default=None,
        description="Reference images to persist for advanced mode",
    )


class ChatMessageRequest(BaseModel):
    """Request to send a chat message."""

    content: str = Field(
        ..., description="Message content - can be string or structured content object"
    )
    model_id: str = Field(..., description="LLM model ID")
    file_ids: Optional[List[str]] = Field(
        None, description="List of uploaded file IDs to include in the message"
    )
    session_id: Optional[UUID] = Field(None, description="Existing session ID")
    tools: Optional[Dict[str, bool]] = Field(
        None,
        description="Tool enablement configuration. Keys: tool names, Values: enabled status. "
        "Available tools: web_search, image_search, web_visit, code_interpreter. "
        "Example: {'web_search': true, 'code_interpreter': false}. "
        "If None or empty, no tools are enabled.",
    )
    media_preferences: Optional[MediaPreferences] = Field(
        None,
        description="Media generation preferences when user explicitly enables image/video in Chat Mode.",
    )
    github_repository: Optional[GitHubRepositoryContext] = Field(
        None,
        description="Selected GitHub repository context for agent operations. "
        "When provided, the agent will use this repository as the default context for GitHub operations.",
    )
    council_preferences: Optional[CouncilPreferences] = Field(
        None,
        description="Model Council preferences for running multiple LLMs in parallel.",
    )


class StopConversationRequest(BaseModel):
    """Request to send a chat message."""

    session_id: UUID = Field(..., description="Existing session ID")


class StopConversationResponse(BaseModel):
    """Request to send a chat message."""

    success: bool = Field(
        ..., description="Whether the conversation was successfully stopped"
    )
    last_message_id: Optional[UUID] = Field(
        None, description="ID of the last message in the conversation"
    )


class FileAttachmentResponse(BaseModel):
    id: UUID
    file_name: str
    file_size: int
    content_type: str
    created_at: datetime


class ChatMessageResponse(BaseModel):
    """Single chat message response.

    The content field contains a list of ContentPart objects directly from the database.

    Example:
    [
        {"type": "text", "text": "hello"},
        {"type": "reasoning", "thinking": "...", "signature": "..."},
        {"type": "tool_call", "id": "...", "name": "...", "input": "...", "finished": true},
        {"type": "tool_result", "tool_call_id": "...", "name": "...", "content": "...", "is_error": false}
    ]
    """

    id: str
    role: MessageRoleType
    content: List[Dict[str, Any]] = Field(
        ...,
        description="List of ContentPart objects (text, reasoning, tool_call, tool_result, etc.)",
    )
    usage: Optional[TokenUsage] = None
    tokens: Optional[int] = None
    model: Optional[str] = None
    created_at: datetime
    files: List[FileAttachmentResponse] = Field(default_factory=list)
    finish_reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    provider_metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class MessageHistoryResponse(BaseModel):
    """Response with message history."""

    messages: List[ChatMessageResponse]
    has_more: bool
    total_count: int


class ClearHistoryResponse(BaseModel):
    """Response after clearing history."""

    success: bool
    deleted_count: int
    message: str


class ModelInfo(BaseModel):
    """Information about an available model."""

    id: str
    name: str
    provider: str
    cost_per_1k_tokens: float
    max_tokens: int
    supports_streaming: bool


class ModelsListResponse(BaseModel):
    """Response with list of available models."""

    models: List[ModelInfo]


class SessionMetadata(BaseModel):
    """Chat session metadata."""

    session_id: UUID = Field(..., description="Unique session identifier")
    name: str | None = Field(None, description="Session name")
    title_pending: bool = Field(
        False,
        description="Whether a background title is still being generated",
    )
    status: SessionStatusType = Field(..., description="Session status")
    agent_type: Literal["chat"] = Field(..., description="Type of agent")
    model_id: str = Field(..., description="LLM model ID used for this session")
    created_at: str = Field(..., description="Session creation timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Chat - 2025-10-23 15:30",
                "title_pending": False,
                "status": "active",
                "agent_type": "chat",
                "model_id": "gpt-4",
                "created_at": "2025-10-23T15:30:00.000Z",
            }
        }
