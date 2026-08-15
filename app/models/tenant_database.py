from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from .base import Base


class TenantDatabase(Base):
    """Encrypted, tenant-owned external database connection configuration."""

    __tablename__ = "tenant_databases"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(
        String(36), ForeignKey("tenants.id"), nullable=False, unique=True, index=True
    )
    database_type = Column(String(32), nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    database_name = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)
    encrypted_password = Column(Text, nullable=False)
    default_schema = Column(String(255), nullable=True)
    ssl_enabled = Column(Boolean, default=True, nullable=False)
    ssl_mode = Column(String(32), default="require", nullable=False)
    connection_timeout = Column(Integer, default=10, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    last_tested_at = Column(DateTime, nullable=True)
    schema_metadata = Column(Text, nullable=True)
    schema_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
