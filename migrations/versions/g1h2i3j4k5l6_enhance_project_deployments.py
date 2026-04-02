"""Enhance project_deployments table with detailed tracking fields.

Adds comprehensive deployment tracking including:
- Provider type (cloud_run, vercel)
- Version numbering per project
- Source code snapshot tracking
- Unified metadata for provider-specific info
- Detailed error tracking
- Performance metrics

Also:
- Creates project_custom_domains table for custom subdomain management
- Removes redundant is_active from project_deployments (use current_production_deployment_id instead)
- Adds FK constraint to current_production_deployment_id

Revision ID: g1h2i3j4k5l6
Revises: g4h5i6j7k8l9
Create Date: 2026-01-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "g4h5i6j7k8l9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add new columns to project_deployments and create project_custom_domains table."""

    # =========================================================================
    # Enhance project_deployments table
    # =========================================================================

    with op.batch_alter_table("project_deployments", schema=None) as batch_op:
        # Deployment identification
        batch_op.add_column(
            sa.Column(
                "provider",
                sa.String(50),
                nullable=False,
                server_default="cloud_run",
                comment="Deployment platform: cloud_run, vercel",
            )
        )
        batch_op.add_column(
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="1",
                comment="Auto-incrementing deployment version per project (v1, v2, v3...)",
            )
        )

        # Note: snapshot_id column already exists from 9b7fb0e8a6d2_add_project_tables.py

        # Source info
        batch_op.add_column(
            sa.Column(
                "source_path",
                sa.String(500),
                nullable=True,
                comment="Original path of source code in sandbox/workspace",
            )
        )

        # Unified metadata (provider-specific, source, image, config)
        batch_op.add_column(
            sa.Column(
                "metadata",
                JSONB(),
                nullable=True,
                comment="All deployment metadata: source, image, config, cloud_run/vercel specifics",
            )
        )

        # Error tracking
        batch_op.add_column(
            sa.Column(
                "error_phase",
                sa.String(50),
                nullable=True,
                comment="Phase where error occurred: upload, build, push, deploy, health_check",
            )
        )
        batch_op.add_column(
            sa.Column(
                "error_details",
                JSONB(),
                nullable=True,
                comment="Detailed error context: code, message, stack_trace, logs",
            )
        )

        # Performance metrics
        batch_op.add_column(
            sa.Column(
                "upload_duration_ms",
                sa.BigInteger(),
                nullable=True,
                comment="Time taken to upload source code to cloud storage (ms)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "build_duration_ms",
                sa.BigInteger(),
                nullable=True,
                comment="Time taken for the build step only (ms)",
            )
        )

        # Add indexes for common queries
        batch_op.create_index(
            "idx_project_deployments_provider",
            ["provider"],
        )
        batch_op.create_index(
            "idx_project_deployments_version",
            ["project_id", "version"],
        )

        # Remove redundant is_active column (use project.current_production_deployment_id instead)
        batch_op.drop_column("is_active")

    # =========================================================================
    # Create project_custom_domains table
    # =========================================================================

    op.create_table(
        "project_custom_domains",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            comment="Project this custom domain belongs to",
        ),
        # Domain info
        sa.Column(
            "subdomain",
            sa.String(63),
            nullable=False,
            unique=True,
            comment="User-chosen subdomain (max 63 chars per DNS spec)",
        ),
        sa.Column(
            "full_domain",
            sa.String(255),
            nullable=False,
            comment="Complete domain including base domain",
        ),
        # Deployment linking
        sa.Column(
            "deployment_id",
            sa.String(),
            sa.ForeignKey("project_deployments.id", ondelete="SET NULL"),
            nullable=True,
            comment="Specific deployment this domain points to (NULL = current production)",
        ),
        # DNS/SSL status
        sa.Column(
            "dns_status",
            sa.String(50),
            server_default="pending",
            comment="DNS record status: pending, propagating, active, failed",
        ),
        sa.Column(
            "ssl_status",
            sa.String(50),
            server_default="pending",
            comment="SSL certificate status: pending, provisioning, active, failed",
        ),
        sa.Column(
            "cloudflare_record_id",
            sa.String(100),
            nullable=True,
            comment="Cloudflare DNS record ID for management",
        ),
        # Ownership & audit
        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the subdomain was claimed",
        ),
        sa.Column(
            "claimed_by_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="User who claimed this subdomain",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        # Constraints
        sa.UniqueConstraint("project_id", name="uq_project_custom_domains_project_id"),
    )

    # Create indexes for project_custom_domains
    op.create_index(
        "idx_project_custom_domains_project_id",
        "project_custom_domains",
        ["project_id"],
    )
    op.create_index(
        "idx_project_custom_domains_subdomain",
        "project_custom_domains",
        ["subdomain"],
    )

    # =========================================================================
    # Modify projects table
    # =========================================================================

    with op.batch_alter_table("projects", schema=None) as batch_op:
        # Add custom_domain_id
        batch_op.add_column(
            sa.Column(
                "custom_domain_id",
                sa.String(),
                sa.ForeignKey("project_custom_domains.id", ondelete="SET NULL"),
                nullable=True,
                comment="Reference to project's custom domain",
            )
        )

        # Add FK constraint to current_production_deployment_id
        batch_op.create_foreign_key(
            "fk_projects_current_production_deployment_id",
            "project_deployments",
            ["current_production_deployment_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Remove new columns and table."""

    # Revert projects table changes
    with op.batch_alter_table("projects", schema=None) as batch_op:
        # Drop FK constraint on current_production_deployment_id
        batch_op.drop_constraint("fk_projects_current_production_deployment_id", type_="foreignkey")

        # Remove custom_domain_id
        batch_op.drop_column("custom_domain_id")

    # Drop project_custom_domains table
    op.drop_index("idx_project_custom_domains_subdomain", table_name="project_custom_domains")
    op.drop_index("idx_project_custom_domains_project_id", table_name="project_custom_domains")
    op.drop_table("project_custom_domains")

    # Revert project_deployments changes
    with op.batch_alter_table("project_deployments", schema=None) as batch_op:
        batch_op.drop_index("idx_project_deployments_version")
        batch_op.drop_index("idx_project_deployments_provider")
        batch_op.drop_column("build_duration_ms")
        batch_op.drop_column("upload_duration_ms")
        batch_op.drop_column("error_details")
        batch_op.drop_column("error_phase")
        batch_op.drop_column("metadata")
        batch_op.drop_column("source_path")
        # batch_op.drop_column("snapshot_id")
        batch_op.drop_column("version")
        batch_op.drop_column("provider")

        # Restore is_active column
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=True, server_default="false")
        )
