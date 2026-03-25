"""Base models for requests and responses."""

from pydantic import BaseModel, Field


class BaseRequest(BaseModel):
    """Base request model."""

    pass


class BaseResponse(BaseModel):
    """Base response model with success/error pattern."""

    success: bool = Field(..., description="Whether the operation was successful")
    error: str | None = Field(None, description="Error message if operation failed")
    cost: float | None = Field(None, description="Cost of the operation if applicable")
