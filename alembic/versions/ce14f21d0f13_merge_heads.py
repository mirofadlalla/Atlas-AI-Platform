"""merge heads

Revision ID: ce14f21d0f13
Revises: 1eb4a877921f, add_processing_status
Create Date: 2026-07-29 03:32:10.939537

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "ce14f21d0f13"
down_revision: Union[str, None] = ("1eb4a877921f", "add_processing_status")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
