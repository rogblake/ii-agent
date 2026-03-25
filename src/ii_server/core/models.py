"""Shared data models for ii_server."""

from pydantic import BaseModel, ConfigDict


class ServerConfig(BaseModel):
    """Configuration for a single development server."""

    deployment_url: str
    port: int
    command: str
    session: str
    run_dir: str

    model_config = ConfigDict(extra="forbid")


class DeploymentConfig(BaseModel):
    """Full deployment configuration for a project."""

    preview_url: str
    preview_port: int
    project_name: str
    framework: str
    directory: str
    servers: list[ServerConfig]

    model_config = ConfigDict(extra="forbid")
