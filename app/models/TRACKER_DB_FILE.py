from .base import Base
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .uuid import uuid_pk
from datetime import datetime


class TRACKER_DB_FILE(Base):
    """
    Tracks the ingestion status of documents uploaded per tenant into the RAG pipeline.
    Used to prevent duplicate processing of the same file (via SHA-256 hash comparison).
    Statuses: 'processing' -> 'completed' | 'failed'
    """

    __tablename__ = "tracker_db_file"

    id = uuid_pk()
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    file_name = Column(String(512), nullable=False)
    file_hash = Column(String(64), index=True, nullable=False)

    status = Column(
        String(20), default="completed"
    )  # 'processing', 'completed', 'failed'

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, default=datetime.utcnow)

    # Relationship back to Tenants
    tenant = relationship("Tenants", back_populates="tracked_files")
