"""Prompts for conversation context management and summarization."""

PREVIOUS_SUMMARY = """<PREVIOUS_SUMMARY>
{parent_summary_text}
</PREVIOUS_SUMMARY>

The following conversation occurred AFTER the previous summary:
"""

SUMMARY_PROMPT = """You maintain a long-term running summary of a conversation.
Your job is to merge the existing summary with new messages and produce an improved, more compact summary.

Rules:
- Keep only meaningful, actionable, or context-critical information.
- Remove outdated intent or information replaced by new messages.
- Prefer abstraction over details unless they matter for future turns.
- Ensure the summary is coherent and can stand alone without the full chat history.
- Focus on user goals, decisions, technical instructions, and constraints.

{previous_summary_section}

<CONVERSATION>
{conversation_text}
</CONVERSATION>

Provide a clear, structured summary."""
