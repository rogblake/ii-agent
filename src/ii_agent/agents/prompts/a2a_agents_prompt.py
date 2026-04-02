"""A2A Agents prompt generation utilities."""

from typing import Dict, Any, Optional


def build_a2a_agents_prompt(tool_args: Optional[Dict[str, Any]] = None) -> str:
    """
    Build A2A agents prompt based on tool_args configuration.

    Args:
        tool_args: Tool arguments containing A2A agents configuration

    Returns:
        Formatted prompt string describing available A2A agents
    """
    if not tool_args or not tool_args.get("enable_a2a_agents"):
        return ""

    a2a_agents = tool_args.get("a2a_agents", {})
    if not a2a_agents:
        return ""

    prompt_lines = [
        "You have access to the following specialized external A2A agents via the `a2a_agent` tool:",
        "These agents are highly specialized and should be preferred for matching tasks:",
    ]

    for name, config in a2a_agents.items():
        if isinstance(config, dict):
            url = config.get("url", "unknown")
            description = config.get(
                "description",
                f"Specialized {config.get('name', name)} agent (description will be loaded from agent card when used)",
            )
            display_name = config.get("name", name)
        else:
            url = config
            display_name = name
            description = (
                f"Specialized {name} agent (description will be loaded from agent card when used)"
            )

        prompt_lines.append(f"- **{display_name}** ({url}): {description}")

    prompt_lines.extend(
        [
            "",
            "When using A2A agents:",
            "1. First check if any A2A agent matches the user's request",
            "2. If a match is found, use the A2A agent as your primary approach",
            "3. If no match is found, then consider standard tools as fallback",
            "4. Always provide clear, detailed instructions to A2A agents",
            "5. Process and integrate the A2A agent's response into your final answer",
        ]
    )

    return "\n".join(prompt_lines)


def get_a2a_agents_rules() -> str:
    """
    Get the base A2A agents rules that are always included in the system prompt.

    Returns:
        Base A2A agents rules string
    """
    return """
<a2a_agents>
You have access to specialized external A2A agents via the `a2a_agent` tool. These agents are specialized for specific domains and can provide expert assistance beyond your core capabilities.

When to use A2A agents:
- When the user's request requires specialized domain knowledge that external agents are better equipped to handle
- When you need expert analysis, research, or processing in a specific field
- When the task would benefit from specialized tools or capabilities not available in your standard toolkit
- When the user explicitly mentions wanting to use a specific external agent

How to use A2A agents:
1. Identify if the task would benefit from specialized external assistance
2. Use the `a2a_agent` tool with the appropriate agent URL and detailed query
3. Provide clear, specific instructions to the external agent
4. Include relevant context in your query to help the external agent understand the task
5. Process and integrate the external agent's response into your final answer

Available A2A agents will be dynamically configured based on the current session. The tool will show you which agents are available and their capabilities.

Important guidelines:
- Always provide clear, detailed instructions to external agents
- Include relevant context and background information
- Process the external agent's response and integrate it meaningfully
- Don't rely solely on external agents - use them to enhance your capabilities
- If an external agent fails, try alternative approaches or provide your own analysis
</a2a_agents>
"""
