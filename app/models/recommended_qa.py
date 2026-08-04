from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey

from .base import Base
from .uuid import uuid_pk

class RecommendedQA(Base):
    __tablename__ = "recommended_qa"

    id = uuid_pk()
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    question = Column(String, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
