from app.models.uuid import uuid_pk

from sqlalchemy import Column, String, Integer, Numeric, ForeignKey, Text, Boolean, DateTime, Index

from sqlalchemy.orm import relationship

from .base import Base

from datetime import datetime, timezone


class CostLog(Base):
    """
    Tracks token usage and monetary cost for each LLM call within a run.

    A single run may involve multiple LLM calls (e.g. routing model +
    generation model), so the relationship is One run → Many cost entries.
    The previous UNIQUE constraint on run_id has been removed to allow this.
    """
    __tablename__ = "cost_log"

    log_id = uuid_pk()

    # Non-unique FK so one run can have many cost entries
    run_id = Column(String, ForeignKey("runs.run_id"), nullable=True, index=True)

    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    model_name = Column(String)
    cost_usd = Column(Numeric(10, 6))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    run = relationship("Runs", back_populates="cost_details")