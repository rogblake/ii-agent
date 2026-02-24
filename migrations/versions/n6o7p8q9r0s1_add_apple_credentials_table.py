"""Add apple_credentials table for Apple auth/TestFlight credentials.

Revision ID: n6o7p8q9r0s1
Revises: m5n6o7p8q9r0
Create Date: 2026-02-24 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "n6o7p8q9r0s1"
down_revision: Union[str, None] = "m5n6o7p8q9r0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "apple_credentials",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("apple_id", sa.String(), nullable=False),
        sa.Column(
            "auth_state",
            sa.String(),
            nullable=False,
            server_default="pending_login",
        ),
        sa.Column("encrypted_session_data", sa.Text(), nullable=True),
        sa.Column("selected_team_id", sa.String(), nullable=True),
        sa.Column("team_name", sa.String(), nullable=True),
        sa.Column("available_teams", JSONB(), nullable=True),
        sa.Column("session_expiry", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("encrypted_expo_token", sa.Text(), nullable=True),
        sa.Column("encrypted_app_specific_password", sa.Text(), nullable=True),
        sa.Column("encrypted_ios_p12", sa.Text(), nullable=True),
        sa.Column("encrypted_ios_p12_password", sa.Text(), nullable=True),
        sa.Column("encrypted_ios_provisioning_profile", sa.Text(), nullable=True),
        sa.Column("ios_bundle_identifier", sa.String(), nullable=True),
        sa.Column("ios_certificate_expiry", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ios_certificate_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "apple_id", name="uq_user_apple_account"),
    )
    op.create_index(
        "idx_apple_credentials_user_id",
        "apple_credentials",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_apple_credentials_user_id", table_name="apple_credentials")
    op.drop_table("apple_credentials")
