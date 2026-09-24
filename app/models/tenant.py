from .base import Base
from sqlalchemy import Column, DateTime, String
from .uuid import uuid_pk
from sqlalchemy.orm import relationship

from datetime import datetime


class Tenants(Base):
    """Tenant model for multi-tenant SaaS platform.

    Lifecycle:
        'pending'  — newly registered, blocked from platform access until
                     a super admin approves the tenant.
        'active'   — super admin approved; the tenant and its admin can log in.
        'rejected' — super admin rejected the registration; login is blocked.
    """

    __tablename__ = "tenants"
    id = uuid_pk()
    name = Column(String, nullable=False)
    plan = Column(String, nullable=False)
    # Tenant approval status — new registrations default to 'pending'.
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("Users", back_populates="tenant")
    tracked_files = relationship(
        "TRACKER_DB_FILE", back_populates="tenant", cascade="all, delete-orphan"
    )
