"""Project visual editing (design mode) sub-domain.

Public API re-exports are declared in ``__all__`` but use lazy imports
to avoid circular-import chains at module load time.
"""

__all__ = [
    # Repository
    "ProjectDesignRepository",
    # Service
    "ProjectDesignService",
    # Router
    "router",
    # Schemas
    "StyleChange",
    "ElementContext",
    "IframeDocumentSnapshot",
    # Exceptions
    "DesignSessionNotFoundError",
    "DesignSessionAccessDeniedError",
    "DesignSandboxUnavailableError",
    "DesignValidationError",
]


def __getattr__(name: str):  # noqa: ANN001
    """Lazy imports to avoid circular dependency chains."""
    if name == "ProjectDesignRepository":
        from ii_agent.projects.design.repository import ProjectDesignRepository

        return ProjectDesignRepository
    if name == "ProjectDesignService":
        from ii_agent.projects.design.service import ProjectDesignService

        return ProjectDesignService
    if name == "router":
        from ii_agent.projects.design.router import router

        return router
    if name in ("StyleChange", "ElementContext", "IframeDocumentSnapshot"):
        from ii_agent.projects.design import schemas as _mod

        return getattr(_mod, name)
    if name in (
        "DesignSessionNotFoundError",
        "DesignSessionAccessDeniedError",
        "DesignSandboxUnavailableError",
        "DesignValidationError",
    ):
        from ii_agent.projects.design import exceptions as _mod

        return getattr(_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
