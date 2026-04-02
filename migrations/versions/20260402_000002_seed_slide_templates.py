"""Seed slide templates from CSV.

Revision ID: 20260402_000002
Revises: 20260330_000001
Create Date: 2026-04-02
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID, insert as pg_insert

# revision identifiers, used by Alembic.
revision = "20260402_000002"
down_revision = "20260330_000001"
branch_labels = None
depends_on = None

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "slide_templates.csv"

slide_templates = sa.table(
    "slide_templates",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("slide_template_name", sa.String()),
    sa.column("slide_content", sa.String()),
    sa.column("slide_template_images", ARRAY(sa.String())),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    for timestamp_format in ("%Y-%m-%d %H:%M:%S.%f %z", "%Y-%m-%d %H:%M:%S %z"):
        try:
            return datetime.strptime(normalized, timestamp_format)
        except ValueError:
            continue

    raise ValueError(f"Unsupported timestamp format in slide template seed CSV: {value!r}")


def _parse_array_literal(value: str | None) -> list[str] | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None
    if normalized == "{}":
        return []

    if normalized.startswith("{") and normalized.endswith("}"):
        normalized = normalized[1:-1]

    return [item.strip().strip('"') for item in normalized.split(",") if item.strip()]


def _load_seed_rows() -> list[dict[str, object]]:
    with DATA_FILE.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return [
            {
                "id": uuid.UUID(row["id"]),
                "slide_template_name": row["slide_template_name"],
                "slide_content": row["slide_content"],
                "slide_template_images": _parse_array_literal(row["slide_template_images"]),
                "created_at": _parse_timestamp(row["created_at"]),
                "updated_at": _parse_timestamp(row["updated_at"]),
            }
            for row in reader
        ]


def upgrade() -> None:
    seed_rows = _load_seed_rows()
    if not seed_rows:
        return

    bind = op.get_bind()
    insert_stmt = pg_insert(slide_templates).values(seed_rows)
    bind.execute(insert_stmt.on_conflict_do_nothing(index_elements=["id"]))


def downgrade() -> None:
    seed_ids = [row["id"] for row in _load_seed_rows()]
    if not seed_ids:
        return

    bind = op.get_bind()
    bind.execute(sa.delete(slide_templates).where(slide_templates.c.id.in_(seed_ids)))
