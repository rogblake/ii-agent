from ii_agent.core.exceptions import IIAgentError


class ProjectDatabaseError(IIAgentError):
    """Raised when querying a project's external database fails."""

    status_code = 400
