"""Router registration for the main application."""

from __future__ import annotations

from fastapi import FastAPI

from .health import health_router


def include_routers(app: FastAPI) -> None:
    """Attach all HTTP routers to the application."""
    # Import concrete router objects to avoid package/submodule name collisions.
    from ii_agent.auth.router import router as auth_router
    from ii_agent.auth.users.router import router as users_router
    from ii_agent.agent.sandboxes.router import router as sandbox_files_router
    from ii_agent.billing.router import router as billing_router
    from ii_agent.billing.credits.router import router as credits_router
    from ii_agent.chat.api.router import router as chat_router
    from ii_agent.content.media.router import router as media_router
    from ii_agent.content.media.router import templates_router as media_templates_router
    from ii_agent.content.media.router import tools_router as media_tools_router
    from ii_agent.content.slides.router import router as slides_router
    from ii_agent.content.slides.templates.router import router as slide_templates_router
    from ii_agent.content.slides.design.router import router as slide_design_router
    from ii_agent.content.slides.nano_banana.router import router as nano_banana_router
    from ii_agent.content.storybook.router import router as storybook_router
    from ii_agent.files.router import router as files_router
    from ii_agent.integrations.connectors.router import router as connectors_router
    from ii_agent.integrations.enhance_prompt.router import router as enhance_prompt_router
    from ii_agent.projects.design.router import router as project_design_router
    from ii_agent.projects.router import router as project_router
    from ii_agent.projects.subdomains.router import router as subdomains_router
    from ii_agent.sessions.router import router as sessions_router
    from ii_agent.sessions.pin import router as pin_router
    from ii_agent.sessions.wishlist import router as wishlist_router
    from ii_agent.settings.llm.router import router as llm_settings_router
    from ii_agent.settings.mcp.router import router as mcp_settings_router
    from ii_agent.settings.skills.router import router as skills_settings_router

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(sandbox_files_router)
    app.include_router(sessions_router)
    app.include_router(credits_router)
    app.include_router(llm_settings_router)
    app.include_router(mcp_settings_router)
    app.include_router(skills_settings_router)
    app.include_router(files_router)
    app.include_router(slides_router)
    app.include_router(slide_templates_router)
    app.include_router(project_design_router)
    app.include_router(slide_design_router)
    app.include_router(nano_banana_router)
    app.include_router(wishlist_router)
    app.include_router(enhance_prompt_router)
    app.include_router(billing_router)
    app.include_router(chat_router)
    app.include_router(connectors_router)
    app.include_router(pin_router)
    app.include_router(project_router)
    app.include_router(subdomains_router)
    app.include_router(media_templates_router)
    app.include_router(media_tools_router)
    app.include_router(media_router)
    app.include_router(storybook_router)
    app.include_router(health_router)
