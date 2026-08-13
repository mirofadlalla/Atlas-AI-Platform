"""Add processing status to tracker_db_file

Revision ID: add_processing_status
Revises: create_invitations_clean
Create Date: 2026-02-27 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_processing_status"
down_revision: Union[str, None] = "create_invitations_clean"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tracker_db_file",
        sa.Column("status", sa.String(), nullable=True, default="completed"),
    )
    op.add_column(
        "tracker_db_file", sa.Column("started_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "tracker_db_file", sa.Column("completed_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tracker_db_file", "completed_at")
    op.drop_column("tracker_db_file", "started_at")
    op.drop_column("tracker_db_file", "status")
