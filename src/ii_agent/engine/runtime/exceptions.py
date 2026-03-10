from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ii_agent.engine.runtime.models.message import Message


class AgentRunException(Exception):
    def __init__(
        self,
        exc,
        user_message: Optional[Union[str, Message]] = None,
        agent_message: Optional[Union[str, Message]] = None,
        messages: Optional[List[Union[dict, Message]]] = None,
        stop_execution: bool = False,
    ):
        super().__init__(exc)
        self.user_message = user_message
        self.agent_message = agent_message
        self.messages = messages
        self.stop_execution = stop_execution
        self.type = "agent_run_error"
        self.error_id = "agent_run_error"


class RetryAgentRun(AgentRunException):
    """Exception raised when a tool call should be retried."""

    def __init__(
        self,
        exc,
        user_message: Optional[Union[str, Message]] = None,
        agent_message: Optional[Union[str, Message]] = None,
        messages: Optional[List[Union[dict, Message]]] = None,
    ):
        super().__init__(
            exc,
            user_message=user_message,
            agent_message=agent_message,
            messages=messages,
            stop_execution=False,
        )
        self.error_id = "retry_agent_run_error"


class AgentError(Exception):
    """Exception raised when an internal error occurs."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.type = "error"
        self.error_id = "error"

    def __str__(self) -> str:
        return str(self.message)


class ModelAuthenticationError(AgentError):
    """Raised when model authentication fails."""

    def __init__(self, message: str, status_code: int = 401, model_name: Optional[str] = None):
        super().__init__(message, status_code)
        self.model_name = model_name

        self.type = "model_authentication_error"
        self.error_id = "model_authentication_error"


class ModelProviderError(AgentError):
    """Exception raised when a model provider returns an error."""

    def __init__(
        self,
        message: str,
        status_code: int = 502,
        model_name: Optional[str] = None,
        model_id: Optional[str] = None,
    ):
        super().__init__(message, status_code)
        self.model_name = model_name
        self.model_id = model_id

        self.type = "model_provider_error"
        self.error_id = "model_provider_error"


class ModelRateLimitError(ModelProviderError):
    """Exception raised when a model provider returns a rate limit error."""

    def __init__(
        self,
        message: str,
        status_code: int = 429,
        model_name: Optional[str] = None,
        model_id: Optional[str] = None,
    ):
        super().__init__(message, status_code, model_name, model_id)
        self.error_id = "model_rate_limit_error"


class EvalError(Exception):
    """Exception raised when an evaluation fails."""

    pass


class CheckTrigger(Enum):
    """Enum for guardrail triggers."""

    OFF_TOPIC = "off_topic"
    INPUT_NOT_ALLOWED = "input_not_allowed"
    OUTPUT_NOT_ALLOWED = "output_not_allowed"
    VALIDATION_FAILED = "validation_failed"

    PROMPT_INJECTION = "prompt_injection"
    PII_DETECTED = "pii_detected"


class BaseCheckError(Exception):
    """Base class for check errors with common check trigger handling."""

    def __init__(
        self,
        message: str,
        error_type: str,
        check_trigger: CheckTrigger,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.type = error_type
        self.error_id = check_trigger.value if isinstance(check_trigger, CheckTrigger) else str(check_trigger)
        self.message = message
        self.check_trigger = check_trigger
        self.additional_data = additional_data


class InputCheckError(BaseCheckError):
    """Exception raised when an input check fails."""

    def __init__(
        self,
        message: str,
        check_trigger: CheckTrigger = CheckTrigger.INPUT_NOT_ALLOWED,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_type="input_check_error",
            check_trigger=check_trigger,
            additional_data=additional_data,
        )


class OutputCheckError(BaseCheckError):
    """Exception raised when an output check fails."""

    def __init__(
        self,
        message: str,
        check_trigger: CheckTrigger = CheckTrigger.OUTPUT_NOT_ALLOWED,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_type="output_check_error",
            check_trigger=check_trigger,
            additional_data=additional_data,
        )
