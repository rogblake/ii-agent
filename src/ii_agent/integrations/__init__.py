"""Integrations domain -- external service connectors and enhancements.

Sub-packages:
    connectors   -- OAuth connectors (GitHub, Google Drive, RevenueCat) + Composio
    enhance_prompt -- Stateless prompt enhancement via LLM providers
    mobile       -- Mobile platform integrations (Apple credentials)

Import pattern:
    from ii_agent.integrations.connectors.service import ConnectorService
    from ii_agent.integrations.connectors.dependencies import ConnectorServiceDep
    from ii_agent.integrations.enhance_prompt.router import router as enhance_prompt_router
"""

__all__: list[str] = []
