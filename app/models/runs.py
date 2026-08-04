from sqlalchemy import Column, String, Float, ForeignKey, Text, Boolean, DateTime, Integer, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.models.uuid import uuid_pk
from .base import Base

class Runs(Base):
    __tablename__ = "runs"

    run_id = uuid_pk()
    tenant_id = Column(String, ForeignKey('tenants.id'), index=True, nullable=False)

    tenant = relationship("Tenants", backref="runs")
    query = Column(Text)
    answer = Column(Text)
    latency = Column(Float)
    cache_hit = Column(Boolean, default=False)
    retrieved_docs_ids = Column(Text) 

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # One run → many cost entries (one per LLM call)
    cost_details = relationship("CostLog", back_populates="run", uselist=True)