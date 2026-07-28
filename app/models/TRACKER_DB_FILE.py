from .base import Base
from sqlalchemy import Column, Integer, String, DateTime

from datetime import datetime


class TRACKER_DB_FILE(Base):
    __tablename__ = "tracker_db_file"
    
    id = Column(Integer, primary_key=True, index=True,autoincrement=True)
    tenant_id = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_hash = Column(String, index=True)
    processed_at = Column(DateTime , default=datetime.utcnow)
    status = Column(String, default='completed')  # 'processing', 'completed', 'failed'
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)