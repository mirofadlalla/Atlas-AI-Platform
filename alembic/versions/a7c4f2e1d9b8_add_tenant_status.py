"""Add status column to tenants table

Revision ID: a7c4f2e1d9b8
Revises: f3a1d2c9e8b7
Create Date: 2026-09-24 19:40:00.000000

Adds a ``status`` column to the ``tenants`` table to enforce the tenant
approval workflow.  New tenants are created with status='pending' and may
not log in until a super admin sets the status to 'active'.

Existing rows (tenants already in production) are backfilled to 'active'
so that live tenants continue to work without any manual intervention.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7c4f2e1d9b8"
down_revision: Union[str, None] = "f3a1d2c9e8b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tenants.status column and backfill existing rows to 'active'."""
    # 1. Add the column as nullable first so the backfill UPDATE can run
    #    before we add the NOT NULL constraint.  This avoids locking issues
    #    on large tables and is safer than setting server_default='pending'
    #    (which would mark existing tenants as pending and break production).
    op.add_column(
        "tenants",
        sa.Column("status", sa.String(), nullable=True),
    )

    # 2. Backfill: existing tenants were already active — keep them active.
    op.execute("UPDATE tenants SET status = 'active' WHERE status IS NULL")

    # 3. Tighten to NOT NULL now that every row has a value.
    op.alter_column("tenants", "status", nullable=False)


def downgrade() -> None:
    """Remove the status column from the tenants table."""
    op.drop_column("tenants", "status")
