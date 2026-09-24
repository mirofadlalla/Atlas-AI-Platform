"""Add super_admin role support

Revision ID: f3a1d2c9e8b7
Revises: merge_episodes_and_tracker_uuid
Create Date: 2026-09-24 18:00:00.000000

The super_admin role is stored as the string 'super_admin' in the existing
users.role column (already a plain VARCHAR with no enum constraint).

Super admin accounts have tenant_id = NULL, which is already permitted by
the original DDL (tenant_id is nullable=True in the users table creation
migration dcf644ec6a71).

This migration therefore requires no DDL changes.  It is recorded in the
Alembic history so that:

  * Production deployments have an unambiguous checkpoint confirming the
    super-admin feature has been applied.
  * alembic current / alembic history shows a clear audit trail.
  * A future migration that does need DDL (e.g. adding an index on role)
    can depend on this revision.

Schema facts that make this safe without DDL:
  - users.role        VARCHAR, nullable — 'super_admin' is a valid value.
  - users.tenant_id   VARCHAR, nullable=True — NULL is already allowed.
  - No DB-level CHECK or ENUM constrains the role column.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f3a1d2c9e8b7"
down_revision: Union[str, None] = "merge_episodes_and_tracker_uuid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No DDL required — super_admin role uses existing nullable columns."""
    pass


def downgrade() -> None:
    """No DDL to reverse.

    To remove all super_admin accounts from a live database run:
        UPDATE users SET role = 'admin' WHERE role = 'super_admin';
    This migration does not automate that because it is a data operation
    that depends on your specific rollback strategy.
    """
    pass
