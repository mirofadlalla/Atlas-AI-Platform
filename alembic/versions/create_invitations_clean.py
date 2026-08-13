"""Create invitations clean - Placeholder for broken migration

Revision ID: create_invitations_clean
Revises: add_invitations
Create Date: 2026-02-24 16:00:00.000000

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "create_invitations_clean"
down_revision: Union[str, None] = "add_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - No-op migration to fix migration chain."""
    pass


def downgrade() -> None:
    """Downgrade schema - No-op migration to fix migration chain."""
    pass
