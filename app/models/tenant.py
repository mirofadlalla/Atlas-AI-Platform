from .base import Base
from sqlalchemy import Column ,DateTime, String , Float
from .uuid import uuid_pk
from sqlalchemy.orm import relationship

from datetime import datetime


class Tenants(Base):
    __tablename__ = 'tenants'
    id  = uuid_pk()
    name  = Column(String , nullable=False)
    plan = Column(String , nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("Users", back_populates="tenant")
    tracked_files = relationship("TRACKER_DB_FILE", back_populates="tenant", cascade="all, delete-orphan")