"""Merge tenant-status and encrypted-tenant-db heads

Revision ID: b1e9f3a2d7c5
Revises: a7c4f2e1d9b8, 3c5d5f3860a3
Create Date: 2026-09-24 20:30:00.000000

This migration merges two independent heads into a single linear history:

  a7c4f2e1d9b8  — add_tenant_status
    (adds tenants.status column for the super-admin approval workflow)

  3c5d5f3860a3  — create_encrypted_tenant_db
    (restructures the tenant_databases unique index)

Both migrations operate on different tables (tenants vs tenant_databases)
and have no DDL conflicts, so a no-op merge is safe.

After this migration ``alembic upgrade head`` has exactly one head and will
not raise "Multiple head revisions are present".
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b1e9f3a2d7c5"
down_revision: Union[str, Sequence[str], None] = ("a7c4f2e1d9b8", "3c5d5f3860a3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No DDL — this migration only merges two branch heads."""
    pass


def downgrade() -> None:
    """No DDL to reverse."""
    pass
