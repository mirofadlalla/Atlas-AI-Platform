"""fix id column type to uuid in tracker_db_file

Revision ID: 3fb4ef1e662a
Revises: ce14f21d0f13
Create Date: 2026-07-29 03:32:31.233095

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3fb4ef1e662a"
down_revision: Union[str, None] = "ce14f21d0f13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("runs", "tenant_id", existing_type=sa.VARCHAR(), nullable=False)
    op.create_foreign_key(None, "runs", "tenants", ["tenant_id"], ["id"])

    op.alter_column(
        "tracker_db_file",
        "id",
        existing_type=sa.INTEGER(),
        type_=sa.String(),
        postgresql_using="id::text",
        existing_nullable=False,
        server_default=None,
    )

    op.alter_column(
        "tracker_db_file", "file_hash", existing_type=sa.VARCHAR(), nullable=False
    )
    op.alter_column(
        "tracker_db_file",
        "status",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.String(length=20),
        existing_nullable=True,
        existing_server_default=sa.text("'completed'::character varying"),
    )
    op.drop_index("ix_tracker_db_file_id", table_name="tracker_db_file")
    op.create_index(
        op.f("ix_tracker_db_file_tenant_id"),
        "tracker_db_file",
        ["tenant_id"],
        unique=False,
    )
    op.create_foreign_key(None, "tracker_db_file", "tenants", ["tenant_id"], ["id"])
    # failed_reason و retry_count محافظ عليهم - متشالوش


def downgrade() -> None:
    op.drop_constraint(None, "tracker_db_file", type_="foreignkey")
    op.drop_index(op.f("ix_tracker_db_file_tenant_id"), table_name="tracker_db_file")
    op.create_index("ix_tracker_db_file_id", "tracker_db_file", ["id"], unique=False)
    op.alter_column(
        "tracker_db_file",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.VARCHAR(length=50),
        existing_nullable=True,
        existing_server_default=sa.text("'completed'::character varying"),
    )
    op.alter_column(
        "tracker_db_file", "file_hash", existing_type=sa.VARCHAR(), nullable=True
    )
    op.alter_column(
        "tracker_db_file",
        "id",
        existing_type=sa.String(),
        type_=sa.INTEGER(),
        postgresql_using="id::integer",
        existing_nullable=False,
    )
    op.drop_constraint(None, "runs", type_="foreignkey")
    op.alter_column("runs", "tenant_id", existing_type=sa.VARCHAR(), nullable=True)
