import logging
import uuid
from typing import List, Tuple, Optional

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.llm.execution_service import (
    LLMBillingContext,
    LLMExecutionService,
)
from ii_agent.chat.schemas import Message, MessageRole, TextContent

logger = logging.getLogger("prompt_generator")
logger.setLevel(logging.INFO)


async def enhance_user_prompt(
    llm_execution_service: LLMExecutionService,
    llm_config: LLMConfig,
    user_input: str,
    files: List[str],
    billing_context: LLMBillingContext | None = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Enhance a user request into a detailed, comprehensive prompt using an LLM.

    Args:
        llm_execution_service: Shared LLM execution service
        llm_config: LLM model configuration
        user_input: The user's request text
        files: List of file paths to include as context
        billing_context: Optional billing metadata for token deduction

    Returns:
        Tuple of (success: bool, message: str, enhanced_prompt: Optional[str])
    """
    try:
        # Prepare context from files if provided
        file_context = ""
        if files and len(files) > 0:
            file_context = "Referenced files:\n"
            for file_path in files:
                file_path = file_path.lstrip(".")  # Remove leading dot if present
                file_context += f"- {file_path}\n"

        system_prompt = (
            "You are an expert at enhancing user requests into detailed, specific prompts. "
            "Your task is to expand the user's brief request into a comprehensive prompt that will help an AI assistant understand exactly what is needed. "
            "Include specific details, requirements, and context that would be helpful. "
            "Format your response as a single, well-structured prompt without explanations or meta-commentary."
        )

        system_message = Message(
            id=uuid.uuid4(),
            role=MessageRole.SYSTEM,
            parts=[TextContent(text=system_prompt)],
            session_id="enhance_prompt",
        )

        user_message = Message(
            id=uuid.uuid4(),
            role=MessageRole.USER,
            parts=[TextContent(text=f"Enhance this request into a detailed prompt: {user_input}\n\nAdditional context - {file_context}")],
            session_id="enhance_prompt",
        )

        client = llm_execution_service.create_client(llm_config)
        response = await llm_execution_service.send_once(
            client=client,
            messages=[system_message, user_message],
            billing_context=billing_context,
            usage_key="enhance_prompt",
        )
        enhanced_prompt = llm_execution_service.extract_text_content(response.content).strip()

        return True, "Prompt enhanced successfully", enhanced_prompt

    except Exception as e:
        logger.error(f"Error enhancing prompt: {str(e)}", exc_info=True)
        return False, f"Error enhancing prompt: {str(e)}", None
