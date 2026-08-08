"""Merge memory_episodes and tracker_uuid heads.

Revision ID: merge_episodes_and_tracker_uuid
Revises: b4d2e8f1a6c3, 3fb4ef1e662a
Create Date: 2026-08-08 23:10:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "merge_episodes_and_tracker_uuid"
down_revision: Union[str, Sequence[str], None] = ("b4d2e8f1a6c3", "3fb4ef1e662a")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - merge two parallel migration branches."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
