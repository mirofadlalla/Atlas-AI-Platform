from sqlalchemy import Column, String, DateTime, ForeignKey
from datetime import datetime
from app.models.base import Base
from app.models.uuid import uuid_pk

class Documents(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=uuid_pk)
    tenant_id = Column(String(36), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(50), default="pending")
    source = Column(String(255), nullable=True)
    author = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)