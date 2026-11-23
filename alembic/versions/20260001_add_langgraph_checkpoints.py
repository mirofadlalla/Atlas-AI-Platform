"""Add LangGraph checkpoint tables.

Revision ID: 20260001
Revises: ce14f21d0f13
Create Date: 2026-01-01 00:00:00.000000

This migration creates the three tables required by LangGraph persistent
checkpointing (lg_checkpoints, lg_checkpoint_blobs, lg_checkpoint_writes).
It is a no-op on SQLite (the SqliteSaver manages its own schema) and is
safe to run multiple times thanks to CREATE TABLE IF NOT EXISTS.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260001"
down_revision = "ce14f21d0f13"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    """Return True when the current migration target is PostgreSQL."""
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # SQLite: SqliteSaver manages its own schema via .setup(); nothing to do here.
        return

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lg_checkpoints (
            thread_id           TEXT NOT NULL,
            checkpoint_ns       TEXT NOT NULL DEFAULT '',
            checkpoint_id       TEXT NOT NULL,
            parent_checkpoint_id TEXT,
            type                TEXT,
            checkpoint          JSONB NOT NULL,
            metadata            JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lg_checkpoint_blobs (
            thread_id     TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            channel       TEXT NOT NULL,
            version       TEXT NOT NULL,
            type          TEXT NOT NULL,
            blob          BYTEA,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lg_checkpoint_writes (
            thread_id     TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            task_id       TEXT NOT NULL,
            idx           INTEGER NOT NULL,
            channel       TEXT NOT NULL,
            type          TEXT,
            blob          BYTEA NOT NULL,
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        )
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute("DROP TABLE IF EXISTS lg_checkpoint_writes")
    op.execute("DROP TABLE IF EXISTS lg_checkpoint_blobs")
    op.execute("DROP TABLE IF EXISTS lg_checkpoints")
