import os
from enum import Enum
from dataclasses import dataclass, field


class DeploymentStatus(Enum):
    """Status of a deployment operation."""

    PENDING = "pending"
    UPLOADING = "uploading"
    BUILDING = "building"
    DEPLOYING = "deploying"
    COMPLETED = "completed"
    FAILED = "failed"


class TemplateType(Enum):
    """Detected template type for the project."""

    NEXTJS_SHADCN = "nextjs-shadcn"
    REACT_VITE_SHADCN = "react-vite-shadcn"
    REACT_SHADCN_PYTHON = "react-shadcn-python"
    REACT_TAILWIND_PYTHON = "react-tailwind-python"
    UNKNOWN = "unknown"


@dataclass
class DeploymentResult:
    """Result of a deployment operation."""

    success: bool
    url: str | None = None
    service_name: str | None = None
    error: str | None = None
    build_logs: str | None = None
    # Source info
    source_bucket: str | None = None
    source_object: str | None = None
    # Image info
    image_url: str | None = None
    image_digest: str | None = None
    # Build info
    build_id: str | None = None
    build_duration_ms: int | None = None


@dataclass
class CloudRunConfig:
    """Configuration for Cloud Run deployments."""

    project_id: str
    region: str
    source_bucket: str
    artifact_registry: str

    # Optional settings
    max_instances: int = 10
    min_instances: int = 0
    memory: str = "512Mi"
    cpu: str = "1"
    timeout_seconds: int = 300
    concurrency: int = 80

    # Base images for pre-built templates (speeds up builds significantly)
    base_images: dict[str, str] = field(default_factory=dict)

    # Cache bucket for Kaniko layer caching
    cache_bucket: str | None = None

    @classmethod
    def from_env(cls) -> "CloudRunConfig":
        """Create config from environment variables."""
        project_id = os.environ.get("GCP_PROJECT_ID")
        if not project_id:
            raise ValueError("GCP_PROJECT_ID environment variable is required")

        region = os.environ.get("GCP_REGION", "us-central1")
        artifact_registry = os.environ.get(
            "GCP_ARTIFACT_REGISTRY",
            f"{region}-docker.pkg.dev/{project_id}/user-apps",
        )

        # Base templates registry (separate from user-apps to avoid naming conflicts)
        base_templates_registry = os.environ.get(
            "GCP_BASE_TEMPLATES_REGISTRY",
            f"{region}-docker.pkg.dev/{project_id}/base-templates",
        )

        # Base images configuration
        # These should point to pre-built images with dependencies installed
        base_images = {
            TemplateType.NEXTJS_SHADCN.value: os.environ.get(
                "BASE_IMAGE_NEXTJS_SHADCN",
                f"{base_templates_registry}/nextjs-shadcn:latest",
            ),
            TemplateType.REACT_VITE_SHADCN.value: os.environ.get(
                "BASE_IMAGE_REACT_VITE_SHADCN",
                f"{base_templates_registry}/react-vite-shadcn:latest",
            ),
            TemplateType.REACT_SHADCN_PYTHON.value: os.environ.get(
                "BASE_IMAGE_REACT_SHADCN_PYTHON",
                f"{base_templates_registry}/react-shadcn-python:latest",
            ),
            TemplateType.REACT_TAILWIND_PYTHON.value: os.environ.get(
                "BASE_IMAGE_REACT_TAILWIND_PYTHON",
                f"{base_templates_registry}/react-tailwind-python:latest",
            ),
        }

        return cls(
            project_id=project_id,
            region=region,
            source_bucket=os.environ.get("GCP_SOURCE_BUCKET", f"{project_id}-app-sources"),
            artifact_registry=artifact_registry,
            max_instances=int(os.environ.get("CLOUD_RUN_MAX_INSTANCES", "10")),
            min_instances=int(os.environ.get("CLOUD_RUN_MIN_INSTANCES", "0")),
            memory=os.environ.get("CLOUD_RUN_MEMORY", "512Mi"),
            cpu=os.environ.get("CLOUD_RUN_CPU", "1"),
            base_images=base_images,
            cache_bucket=os.environ.get("GCP_CACHE_BUCKET"),
        )
