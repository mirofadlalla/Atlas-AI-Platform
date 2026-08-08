from .base import Base
from sqlalchemy import Column, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone
from .uuid import uuid_pk


class Invitation(Base):
    """
    Model representing user invitations sent by admins.

    Tracks invitation status, token, and expiration for the invitation-based signup flow.
    """

    __tablename__ = "invitations"

    invitation_id = uuid_pk()

    # Invited user's email address
    invited_email = Column(String, nullable=False, index=True)

    # Admin who sent the invitation
    invited_by = Column(String, ForeignKey("users.id"), nullable=False)

    # Tenant the invitation is for
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)

    # Unique token for the invitation link
    token = Column(Text, nullable=False, unique=True, index=True)

    # Invitation status: 'pending', 'accepted', 'rejected', 'expired'
    status = Column(String, default="pending", nullable=False)

    # User ID after acceptance (links to Users table)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(days=7),
        nullable=False,
    )
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    invited_by_user = relationship(
        "Users", foreign_keys=[invited_by], backref="invitations_sent"
    )
    accepted_by_user = relationship(
        "Users", foreign_keys=[user_id], backref="invitation_acceptance"
    )
    tenant = relationship("Tenants", backref="invitations")

    def is_expired(self) -> bool:
        """Check if the invitation has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def is_valid(self) -> bool:
        """Check if the invitation is valid and can still be used."""
        return self.status == "pending" and not self.is_expired()


# backref
# الـ backref بيعمل علاقة عكسية أوتوماتيك من الجدول التاني.
# في المثال:

# python
# invited_by_user = relationship("Users", foreign_keys=[invited_by], backref="invitations_sent")
# ده معناه:

# من جدول Invitation تقدر توصل للمستخدم اللي بعت الدعوة عن طريق invited_by_user.
# ومن جدول Users تقدر توصل لكل الدعوات اللي بعتها عن طريق user.invitations_sent.
