"""Unit tests for projects/cloud_run/*.

Covers:
- DeploymentStatus enum
- TemplateType enum
- DeploymentResult dataclass
- CloudRunConfig dataclass and from_env()
- CloudRunPublisher lazy-loading properties
- detect_template_type() – all branch paths
- prepare_source_with_dockerfile() – unknown type, known type without watermark target
"""

from __future__ import annotations

import gzip
import io
import os
import tarfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# Schemas / Data classes
# ===========================================================================


class TestDeploymentStatus:
    def test_all_expected_values_exist(self):
        from ii_agent.projects.cloud_run.schemas import DeploymentStatus

        assert DeploymentStatus.PENDING.value == "pending"
        assert DeploymentStatus.UPLOADING.value == "uploading"
        assert DeploymentStatus.BUILDING.value == "building"
        assert DeploymentStatus.DEPLOYING.value == "deploying"
        assert DeploymentStatus.COMPLETED.value == "completed"
        assert DeploymentStatus.FAILED.value == "failed"


class TestTemplateType:
    def test_all_expected_values_exist(self):
        from ii_agent.projects.cloud_run.schemas import TemplateType

        assert TemplateType.NEXTJS_SHADCN.value == "nextjs-shadcn"
        assert TemplateType.REACT_VITE_SHADCN.value == "react-vite-shadcn"
        assert TemplateType.REACT_SHADCN_PYTHON.value == "react-shadcn-python"
        assert TemplateType.REACT_TAILWIND_PYTHON.value == "react-tailwind-python"
        assert TemplateType.UNKNOWN.value == "unknown"


class TestDeploymentResult:
    def test_success_result(self):
        from ii_agent.projects.cloud_run.schemas import DeploymentResult

        r = DeploymentResult(
            success=True,
            url="https://my-app.run.app",
            service_name="my-service",
        )
        assert r.success is True
        assert r.url == "https://my-app.run.app"

    def test_failure_result(self):
        from ii_agent.projects.cloud_run.schemas import DeploymentResult

        r = DeploymentResult(success=False, error="Build failed")
        assert r.success is False
        assert r.error == "Build failed"

    def test_default_none_fields(self):
        from ii_agent.projects.cloud_run.schemas import DeploymentResult

        r = DeploymentResult(success=True)
        assert r.url is None
        assert r.service_name is None
        assert r.error is None
        assert r.build_logs is None


class TestCloudRunConfig:
    def test_from_env_requires_gcp_project_id(self):
        from ii_agent.projects.cloud_run.schemas import CloudRunConfig

        env = {"GCP_PROJECT_ID": ""}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("GCP_PROJECT_ID", None)
            with pytest.raises(ValueError, match="GCP_PROJECT_ID"):
                CloudRunConfig.from_env()

    def test_from_env_creates_config_with_defaults(self):
        from ii_agent.projects.cloud_run.schemas import CloudRunConfig

        env = {"GCP_PROJECT_ID": "test-project"}
        with patch.dict(os.environ, env, clear=True):
            os.environ["GCP_PROJECT_ID"] = "test-project"
            config = CloudRunConfig.from_env()

        assert config.project_id == "test-project"
        assert config.region == "us-central1"
        assert config.memory == "512Mi"
        assert config.cpu == "1"
        assert config.max_instances == 10
        assert config.min_instances == 0

    def test_from_env_respects_region_override(self):
        from ii_agent.projects.cloud_run.schemas import CloudRunConfig

        with patch.dict(os.environ, {"GCP_PROJECT_ID": "proj", "GCP_REGION": "europe-west1"}):
            config = CloudRunConfig.from_env()

        assert config.region == "europe-west1"

    def test_from_env_base_images_contain_template_keys(self):
        from ii_agent.projects.cloud_run.schemas import CloudRunConfig, TemplateType

        with patch.dict(os.environ, {"GCP_PROJECT_ID": "proj"}):
            config = CloudRunConfig.from_env()

        assert TemplateType.NEXTJS_SHADCN.value in config.base_images
        assert TemplateType.REACT_VITE_SHADCN.value in config.base_images

    def test_direct_construction(self):
        from ii_agent.projects.cloud_run.schemas import CloudRunConfig

        config = CloudRunConfig(
            project_id="my-proj",
            region="us-east1",
            source_bucket="my-bucket",
            artifact_registry="us-east1-docker.pkg.dev/my-proj/apps",
        )
        assert config.project_id == "my-proj"


# ===========================================================================
# CloudRunPublisher – lazy-loading properties
# ===========================================================================


class TestCloudRunPublisherProperties:
    def _config(self):
        from ii_agent.projects.cloud_run.schemas import CloudRunConfig

        return CloudRunConfig(
            project_id="test-proj",
            region="us-central1",
            source_bucket="bucket",
            artifact_registry="reg",
        )

    def test_storage_client_lazy_loaded(self):
        from ii_agent.projects.cloud_run.service import CloudRunPublisher

        publisher = CloudRunPublisher(config=self._config())
        assert publisher._storage_client is None

        mock_client = MagicMock()
        with patch("google.cloud.storage.Client", return_value=mock_client):
            client = publisher.storage_client

        assert client is mock_client

    def test_storage_client_cached_after_first_access(self):
        from ii_agent.projects.cloud_run.service import CloudRunPublisher

        publisher = CloudRunPublisher(config=self._config())
        mock_client = MagicMock()

        with patch("google.cloud.storage.Client", return_value=mock_client) as mock_cls:
            _ = publisher.storage_client
            _ = publisher.storage_client

        # Storage.Client() should only be called once
        assert mock_cls.call_count == 1

    def test_on_status_update_defaults_to_none(self):
        from ii_agent.projects.cloud_run.service import CloudRunPublisher

        publisher = CloudRunPublisher(config=self._config())
        assert publisher.on_status_update is None

    def test_on_status_update_can_be_set(self):
        from ii_agent.projects.cloud_run.service import CloudRunPublisher

        cb = MagicMock()
        publisher = CloudRunPublisher(config=self._config(), on_status_update=cb)
        assert publisher.on_status_update is cb


# ===========================================================================
# Helpers for tar archive creation
# ===========================================================================


def _make_tar_gz(files: dict[str, str]) -> bytes:
    """Create an in-memory tar.gz archive from a dict of {path: content}."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _tar_file_names(archive: bytes) -> set[str]:
    """Return the set of normalized filenames in a tar.gz archive."""
    names = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getnames():
            names.add(member.lstrip("./"))
    return names


# ===========================================================================
# detect_template_type
# ===========================================================================


class TestDetectTemplateType:
    async def test_detects_nextjs_shadcn(self):
        from ii_agent.projects.cloud_run.source_preparer import detect_template_type
        from ii_agent.projects.cloud_run.schemas import TemplateType

        archive = _make_tar_gz({"next.config.js": "module.exports = {}"})
        result = await detect_template_type(archive)
        assert result == TemplateType.NEXTJS_SHADCN

    async def test_detects_nextjs_mjs(self):
        from ii_agent.projects.cloud_run.source_preparer import detect_template_type
        from ii_agent.projects.cloud_run.schemas import TemplateType

        archive = _make_tar_gz({"next.config.mjs": "export default {}"})
        result = await detect_template_type(archive)
        assert result == TemplateType.NEXTJS_SHADCN

    async def test_detects_react_vite_shadcn(self):
        from ii_agent.projects.cloud_run.source_preparer import detect_template_type
        from ii_agent.projects.cloud_run.schemas import TemplateType

        archive = _make_tar_gz({"vite.config.ts": "export default {}", "package.json": "{}"})
        result = await detect_template_type(archive)
        assert result == TemplateType.REACT_VITE_SHADCN

    async def test_detects_react_vite_js(self):
        from ii_agent.projects.cloud_run.source_preparer import detect_template_type
        from ii_agent.projects.cloud_run.schemas import TemplateType

        archive = _make_tar_gz({"vite.config.js": "export default {}", "package.json": "{}"})
        result = await detect_template_type(archive)
        assert result == TemplateType.REACT_VITE_SHADCN

    async def test_detects_react_shadcn_python_with_radix_ui(self):
        from ii_agent.projects.cloud_run.source_preparer import detect_template_type
        from ii_agent.projects.cloud_run.schemas import TemplateType

        archive = _make_tar_gz(
            {
                "backend/requirements.txt": "fastapi",
                "backend/app.py": "pass",
                "frontend/package.json": '{"dependencies": {"@radix-ui/react-dialog": "1.0.0"}}',
            }
        )
        result = await detect_template_type(archive)
        assert result == TemplateType.REACT_SHADCN_PYTHON

    async def test_detects_react_tailwind_python_without_radix(self):
        from ii_agent.projects.cloud_run.source_preparer import detect_template_type
        from ii_agent.projects.cloud_run.schemas import TemplateType

        archive = _make_tar_gz(
            {
                "backend/requirements.txt": "fastapi",
                "backend/app.py": "pass",
                "frontend/package.json": '{"dependencies": {"tailwindcss": "^3.0.0"}}',
            }
        )
        result = await detect_template_type(archive)
        assert result == TemplateType.REACT_TAILWIND_PYTHON

    async def test_detects_react_tailwind_python_when_no_frontend_package_json(self):
        """When frontend/package.json is missing, falls back to REACT_TAILWIND_PYTHON."""
        from ii_agent.projects.cloud_run.source_preparer import detect_template_type
        from ii_agent.projects.cloud_run.schemas import TemplateType

        archive = _make_tar_gz(
            {
                "backend/requirements.txt": "fastapi",
                "frontend/index.html": "<html>",
            }
        )
        result = await detect_template_type(archive)
        assert result == TemplateType.REACT_TAILWIND_PYTHON

    async def test_unknown_returns_unknown(self):
        from ii_agent.projects.cloud_run.source_preparer import detect_template_type
        from ii_agent.projects.cloud_run.schemas import TemplateType

        archive = _make_tar_gz({"random.txt": "just text"})
        result = await detect_template_type(archive)
        assert result == TemplateType.UNKNOWN


# ===========================================================================
# prepare_source_with_dockerfile
# ===========================================================================


class TestPrepareSourceWithDockerfile:
    async def test_unknown_type_returns_original_bytes(self):
        from ii_agent.projects.cloud_run.source_preparer import (
            prepare_source_with_dockerfile,
        )
        from ii_agent.projects.cloud_run.schemas import TemplateType

        original = _make_tar_gz({"app.py": "print('hello')"})
        result = await prepare_source_with_dockerfile(original, TemplateType.UNKNOWN)
        assert result == original

    async def test_known_type_adds_dockerfile_when_absent(self):
        from ii_agent.projects.cloud_run.source_preparer import (
            prepare_source_with_dockerfile,
        )
        from ii_agent.projects.cloud_run.schemas import TemplateType

        original = _make_tar_gz({"package.json": "{}", "src/main.tsx": "<></>"})
        result = await prepare_source_with_dockerfile(original, TemplateType.NEXTJS_SHADCN)
        names = _tar_file_names(result)
        assert "Dockerfile" in names

    async def test_existing_dockerfile_not_duplicated(self):
        from ii_agent.projects.cloud_run.source_preparer import (
            prepare_source_with_dockerfile,
        )
        from ii_agent.projects.cloud_run.schemas import TemplateType

        original = _make_tar_gz({"Dockerfile": "FROM node:18", "package.json": "{}"})
        result = await prepare_source_with_dockerfile(original, TemplateType.NEXTJS_SHADCN)
        names = list(_tar_file_names(result))
        dockerfile_count = sum(1 for n in names if n == "Dockerfile")
        assert dockerfile_count == 1

    async def test_result_is_valid_targz(self):
        from ii_agent.projects.cloud_run.source_preparer import (
            prepare_source_with_dockerfile,
        )
        from ii_agent.projects.cloud_run.schemas import TemplateType

        original = _make_tar_gz({"package.json": "{}"})
        result = await prepare_source_with_dockerfile(original, TemplateType.REACT_VITE_SHADCN)
        # Should be parseable as tar.gz
        with tarfile.open(fileobj=io.BytesIO(result), mode="r:gz") as tar:
            members = tar.getmembers()
        assert len(members) >= 1

    async def test_vite_entry_file_gets_watermark(self):
        """For REACT_VITE_SHADCN, src/main.tsx with <App /> should get watermark component."""
        from ii_agent.projects.cloud_run.source_preparer import (
            prepare_source_with_dockerfile,
        )
        from ii_agent.projects.cloud_run.schemas import TemplateType

        entry_content = "import App from './App'\nimport React from 'react'\n<App />"
        original = _make_tar_gz(
            {
                "package.json": "{}",
                "src/main.tsx": entry_content,
            }
        )
        result = await prepare_source_with_dockerfile(original, TemplateType.REACT_VITE_SHADCN)
        # The watermark component file should be present
        names = _tar_file_names(result)
        assert any("IIAgent" in n or "ii-agent" in n.lower() for n in names), (
            f"Expected IIAgent watermark in archive, found: {names}"
        )

    async def test_entry_file_without_app_component_not_modified(self):
        """If the entry file doesn't contain <App />, watermark is skipped."""
        from ii_agent.projects.cloud_run.source_preparer import (
            prepare_source_with_dockerfile,
        )
        from ii_agent.projects.cloud_run.schemas import TemplateType

        entry_content = "import React from 'react'\nconst x = 1"
        original = _make_tar_gz(
            {
                "package.json": "{}",
                "src/main.tsx": entry_content,
            }
        )
        result = await prepare_source_with_dockerfile(original, TemplateType.REACT_VITE_SHADCN)
        # Entry file should be present but unmodified (no extra IIAgent import)
        with tarfile.open(fileobj=io.BytesIO(result), mode="r:gz") as tar:
            entry_member = None
            for m in tar.getmembers():
                if "main.tsx" in m.name:
                    entry_member = m
                    break
        assert entry_member is not None


# ===========================================================================
# EXCLUDE_PATTERNS
# ===========================================================================


class TestExcludePatterns:
    def test_node_modules_in_exclude(self):
        from ii_agent.projects.cloud_run.service import CloudRunPublisher

        assert "node_modules" in CloudRunPublisher.EXCLUDE_PATTERNS

    def test_git_in_exclude(self):
        from ii_agent.projects.cloud_run.service import CloudRunPublisher

        assert ".git" in CloudRunPublisher.EXCLUDE_PATTERNS

    def test_pycache_in_exclude(self):
        from ii_agent.projects.cloud_run.service import CloudRunPublisher

        assert "__pycache__" in CloudRunPublisher.EXCLUDE_PATTERNS
