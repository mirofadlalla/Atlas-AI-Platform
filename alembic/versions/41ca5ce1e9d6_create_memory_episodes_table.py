"""create memory episodes table

Revision ID: 41ca5ce1e9d6
Revises: merge_episodes_and_tracker_uuid
Create Date: 2026-08-14 22:42:54.425073

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "41ca5ce1e9d6"
down_revision: Union[str, None] = "merge_episodes_and_tracker_uuid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_memory_episodes_session", table_name="memory_episodes")
    op.drop_index(
        "ix_memory_episodes_user_tenant_created", table_name="memory_episodes"
    )
    op.create_index(
        op.f("ix_memory_episodes_session_id"),
        "memory_episodes",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_episodes_tenant_id"),
        "memory_episodes",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_episodes_user_id"), "memory_episodes", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_memory_episodes_user_id"), table_name="memory_episodes")
    op.drop_index(op.f("ix_memory_episodes_tenant_id"), table_name="memory_episodes")
    op.drop_index(op.f("ix_memory_episodes_session_id"), table_name="memory_episodes")
    op.create_index(
        "ix_memory_episodes_user_tenant_created",
        "memory_episodes",
        ["user_id", "tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_memory_episodes_session", "memory_episodes", ["session_id"], unique=False
    )
