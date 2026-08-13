"""drop_costlog_unique_run_id_add_index

Revision ID: a9f2c3d8e1b4
Revises: 1eb4a877921f
Create Date: 2026-08-04 21:30:00.000000

Removes the UNIQUE constraint on cost_log.run_id so that a single run can
accumulate multiple cost entries (one per LLM call inside the pipeline).
Adds a plain index on the same column to keep JOIN performance.

Also adds timezone-aware column support for all DateTime columns that were
previously using naive UTC datetimes.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a9f2c3d8e1b4"
down_revision: Union[str, None] = "1eb4a877921f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    1. Drop the UNIQUE constraint on cost_log.run_id.
    2. Add a plain index on cost_log.run_id for fast JOINs.
    3. Migrate DateTime columns to TIMESTAMPTZ (timezone-aware).
    """
    # ── 1. Remove unique constraint on cost_log.run_id ───────────────────────
    # Postgres auto-names the constraint based on the UniqueConstraint call.
    # The name below matches what SQLAlchemy generates from UniqueConstraint('run_id').
    op.drop_constraint("cost_log_run_id_key", "cost_log", type_="unique")

    # ── 2. Add non-unique index for JOIN performance ──────────────────────────
    op.create_index("ix_cost_log_run_id", "cost_log", ["run_id"], unique=False)

    # ── 3. Migrate naive DateTime → TIMESTAMPTZ ───────────────────────────────
    # cost_log.created_at
    op.alter_column(
        "cost_log",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # users.created_at
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # runs.created_at
    op.alter_column(
        "runs",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # invitations timestamps
    for col in ("created_at", "expires_at", "accepted_at"):
        op.alter_column(
            "invitations",
            col,
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=(col == "accepted_at"),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Reverse all changes from upgrade()."""
    # ── Revert TIMESTAMPTZ → DateTime ────────────────────────────────────────
    for col in ("created_at", "expires_at", "accepted_at"):
        op.alter_column(
            "invitations",
            col,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=(col == "accepted_at"),
        )

    for table, col in [
        ("runs", "created_at"),
        ("users", "created_at"),
        ("cost_log", "created_at"),
    ]:
        op.alter_column(
            table,
            col,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=True,
        )

    # ── Drop the plain index ──────────────────────────────────────────────────
    op.drop_index("ix_cost_log_run_id", table_name="cost_log")

    # ── Re-create the unique constraint ──────────────────────────────────────
    op.create_unique_constraint("cost_log_run_id_key", "cost_log", ["run_id"])
