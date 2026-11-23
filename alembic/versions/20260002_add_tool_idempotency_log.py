"""Add tool idempotency log table."""

revision = "20260002"
down_revision = "20260001"  # depends on checkpoint migration
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_idempotency_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            idem_key VARCHAR(64) UNIQUE NOT NULL,
            tool_name VARCHAR(50) NOT NULL,
            tenant_id VARCHAR(50),
            run_id VARCHAR(128),
            status VARCHAR(20) DEFAULT 'success',
            has_data BOOLEAN DEFAULT FALSE,
            observation TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            expires_at TIMESTAMPTZ
        )
    """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_idem_log_run_id ON tool_idempotency_log (run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_idem_log_tenant ON tool_idempotency_log (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_idem_log_expires ON tool_idempotency_log (expires_at)"
    )


def downgrade():
    from alembic import op

    op.execute("DROP TABLE IF EXISTS tool_idempotency_log")
