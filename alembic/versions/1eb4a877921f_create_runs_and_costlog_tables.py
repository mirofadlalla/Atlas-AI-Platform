"""create_runs_and_costlog_tables

Revision ID: 1eb4a877921f
Revises: add_invitations
Create Date: 2026-02-26 06:57:13.176456

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1eb4a877921f"
down_revision: Union[str, None] = "add_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # Create runs table
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("latency", sa.Float(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=True),
        sa.Column("retrieved_docs_ids", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
        sa.Index("ix_runs_tenant_id", "tenant_id"),
    )

    # Create cost_log table
    op.create_table(
        "cost_log",
        sa.Column("log_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("log_id"),
        sa.UniqueConstraint("run_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("cost_log")
    op.drop_table("runs")
    op.drop_index(op.f("ix_users_email"), table_name="users")
