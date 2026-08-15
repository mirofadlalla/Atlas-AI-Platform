"""create tenant external database configurations

Revision ID: 7d1c2e3f4a5b
Revises: 41ca5ce1e9d6
"""

from alembic import op
import sqlalchemy as sa

revision = "7d1c2e3f4a5b"
down_revision = "41ca5ce1e9d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tenant_databases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("database_type", sa.String(32), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database_name", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=False),
        sa.Column("default_schema", sa.String(255)),
        sa.Column(
            "ssl_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("ssl_mode", sa.String(32), nullable=False, server_default="require"),
        sa.Column(
            "connection_timeout", sa.Integer(), nullable=False, server_default="10"
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_tested_at", sa.DateTime()),
        sa.Column("schema_metadata", sa.Text()),
        sa.Column("schema_updated_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tenant_databases_tenant_id", "tenant_databases", ["tenant_id"])


def downgrade():
    op.drop_index("ix_tenant_databases_tenant_id", table_name="tenant_databases")
    op.drop_table("tenant_databases")
