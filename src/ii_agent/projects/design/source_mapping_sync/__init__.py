"""Deterministic source-mapping sync pipeline for Design Mode."""

from ii_agent.projects.design.source_mapping_sync._constants import DESIGN_MODE_MANIFEST_FILENAME
from ii_agent.projects.design.source_mapping_sync._orchestrator import (
    apply_changes_with_source_mapping,
)

__all__ = ["apply_changes_with_source_mapping", "DESIGN_MODE_MANIFEST_FILENAME"]
