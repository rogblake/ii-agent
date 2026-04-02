"""Secrets management module for projects.

Public API re-exports are declared in ``__all__`` but use lazy imports
to avoid circular-import chains at module load time.
"""

__all__ = [
    # Service
    "SecretService",
    # Schemas
    "ProjectSecretsRequest",
    "ProjectSecretsResponse",
    # Router
    "router",
]


def __getattr__(name: str):  # noqa: ANN001
    """Lazy imports to avoid circular dependency chains."""
    if name == "SecretService":
        from ii_agent.projects.secrets.service import SecretService

        return SecretService
    if name in ("ProjectSecretsRequest", "ProjectSecretsResponse"):
        from ii_agent.projects.secrets import schemas as _mod

        return getattr(_mod, name)
    if name == "router":
        from ii_agent.projects.secrets.router import router

        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
