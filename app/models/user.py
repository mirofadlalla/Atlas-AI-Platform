from .base import Base
from sqlalchemy import Column, DateTime, String, ForeignKey
from .uuid import uuid_pk
from sqlalchemy.orm import relationship
from datetime import datetime, timezone


class Users(Base):
    """User model for multi-tenant authentication and authorization."""

    __tablename__ = "users"

    id = uuid_pk()
    name = Column(String, nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id"))
    email = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")

    # Admin approval workflow
    # 'approved' - user can log in
    # 'pending' - user is awaiting admin approval
    # 'rejected' - user registration was rejected
    approval_status = Column(String, default="approved", nullable=False)
    approved_by = Column(String, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenants", back_populates="users")
