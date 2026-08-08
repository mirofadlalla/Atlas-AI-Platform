"""Add episodic conversation-memory storage.

Revision ID: b4d2e8f1a6c3
Revises: a9f2c3d8e1b4, add_user_approval
"""

from alembic import op
import sqlalchemy as sa

revision = "b4d2e8f1a6c3"
down_revision = ("a9f2c3d8e1b4", "add_user_approval")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_episodes",
        sa.Column("episode_id", sa.String(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("raw_turns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_episodes_user_tenant_created", "memory_episodes", ["user_id", "tenant_id", "created_at"])
    op.create_index("ix_memory_episodes_session", "memory_episodes", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_episodes_session", table_name="memory_episodes")
    op.drop_index("ix_memory_episodes_user_tenant_created", table_name="memory_episodes")
    op.drop_table("memory_episodes")
