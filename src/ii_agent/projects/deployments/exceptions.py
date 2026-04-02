from ii_agent.core.exceptions import NotFoundError


class DeploymentNotFoundError(NotFoundError):
    """Raised when a deployment is not found."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        super().__init__(f"Deployment with ID {project_id} not found")
