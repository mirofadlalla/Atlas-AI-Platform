"""Add invitations table

Revision ID: add_invitations
Revises: add_user_approval
Create Date: 2026-02-24 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_invitations"
down_revision: Union[str, None] = "add_user_approval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Create invitations table."""
    op.create_table(
        "invitations",
        sa.Column("invitation_id", sa.String(), nullable=False),
        sa.Column("invited_email", sa.String(), nullable=False),
        sa.Column("invited_by", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("invitation_id"),
        sa.ForeignKeyConstraint(
            ["invited_by"], ["users.id"], name="fk_invitations_invited_by"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_invitations_tenant_id"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_invitations_user_id"
        ),
    )
    # Create indexes
    op.create_index(
        "ix_invitations_invited_email", "invitations", ["invited_email"], unique=False
    )
    op.create_index("ix_invitations_token", "invitations", ["token"], unique=True)


def downgrade() -> None:
    """Downgrade schema - Drop invitations table."""
    op.drop_index("ix_invitations_token", table_name="invitations")
    op.drop_index("ix_invitations_invited_email", table_name="invitations")
    op.drop_table("invitations")
