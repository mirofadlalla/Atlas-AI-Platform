"""Add user approval workflow columns

Revision ID: add_user_approval
Revises: dcf644ec6a71
Create Date: 2026-02-24 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_user_approval"
down_revision: Union[str, None] = "84d6c8d986ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add approval workflow columns to users table."""
    # Add approval_status column
    op.add_column(
        "users",
        sa.Column(
            "approval_status", sa.String(), nullable=False, server_default="approved"
        ),
    )

    # Add approved_by column (FK to users.id for self-referential relationship)
    op.add_column("users", sa.Column("approved_by", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_users_approved_by", "users", "users", ["approved_by"], ["id"]
    )

    # Add approved_at column
    op.add_column("users", sa.Column("approved_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema - Remove approval workflow columns."""
    op.drop_constraint("fk_users_approved_by", "users", type_="foreignkey")
    op.drop_column("users", "approved_at")
    op.drop_column("users", "approved_by")
    op.drop_column("users", "approval_status")
