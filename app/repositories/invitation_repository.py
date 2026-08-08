"""
Repository for Invitation model database operations.

Implements repository pattern for managing user invitations.
"""

from sqlalchemy.orm import Session
from app.models.invitation import Invitation
from typing import List, Optional
from datetime import datetime


class InvitationRepository:
    """Repository for managing Invitation database operations."""

    def __init__(self, db: Session):
        """
        Initialize the repository with a database session.

        Args:
            db: SQLAlchemy Session for database operations
        """
        self.db = db

    def create(
        self,
        invited_email: str,
        invited_by: str,
        tenant_id: str,
        token: str,
        expires_at: datetime,
    ) -> Invitation:
        """
        Create a new invitation.

        Args:
            invited_email: Email of the invited user
            invited_by: User ID of the admin sending the invitation
            tenant_id: Tenant ID for the invitation
            token: Unique invitation token
            expires_at: Expiration datetime for the invitation

        Returns:
            Created Invitation object
        """
        invitation = Invitation(
            invited_email=invited_email,
            invited_by=invited_by,
            tenant_id=tenant_id,
            token=token,
            expires_at=expires_at,
        )
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)
        return invitation

    def get_by_id(self, invitation_id: str) -> Optional[Invitation]:
        """
        Retrieve invitation by ID.

        Args:
            invitation_id: Invitation identifier

        Returns:
            Invitation object or None if not found
        """
        return (
            self.db.query(Invitation)
            .filter(Invitation.invitation_id == invitation_id)
            .first()
        )

    def get_by_token(self, token: str) -> Optional[Invitation]:
        """
        Retrieve invitation by token.

        Args:
            token: Unique invitation token

        Returns:
            Invitation object or None if not found
        """
        return self.db.query(Invitation).filter(Invitation.token == token).first()

    def get_by_email(self, email: str, status: str = None) -> List[Invitation]:
        """
        Retrieve invitations by email address.

        Args:
            email: Invited email address
            status: Filter by status ('pending', 'accepted', 'rejected', 'expired')

        Returns:
            List of Invitation objects
        """
        query = self.db.query(Invitation).filter(Invitation.invited_email == email)
        if status:
            query = query.filter(Invitation.status == status)
        return query.all()

    def get_pending_for_tenant(self, tenant_id: str) -> List[Invitation]:
        """
        Get all pending invitations for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of pending Invitation objects
        """
        return (
            self.db.query(Invitation)
            .filter(Invitation.tenant_id == tenant_id, Invitation.status == "pending")
            .order_by(Invitation.created_at.desc())
            .all()
        )

    def get_sent_by_admin(self, admin_id: str, status: str = None) -> List[Invitation]:
        """
        Get invitations sent by a specific admin.

        Args:
            admin_id: Admin user ID
            status: Optional filter by status

        Returns:
            List of Invitation objects
        """
        query = self.db.query(Invitation).filter(Invitation.invited_by == admin_id)
        if status:
            query = query.filter(Invitation.status == status)
        return query.order_by(Invitation.created_at.desc()).all()

    def accept_invitation(self, token: str, user_id: str) -> Optional[Invitation]:
        """
        Accept an invitation and link it to a user.

        Args:
            token: Invitation token
            user_id: New user's ID

        Returns:
            Updated Invitation object or None if not found
        """
        invitation = self.get_by_token(token)
        if invitation and invitation.is_valid():
            invitation.status = "accepted"
            invitation.user_id = user_id
            invitation.accepted_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(invitation)
            return invitation
        return None

    def reject_invitation(self, token: str) -> Optional[Invitation]:
        """
        Reject an invitation.

        Args:
            token: Invitation token

        Returns:
            Updated Invitation object or None if not found
        """
        invitation = self.get_by_token(token)
        if invitation:
            invitation.status = "rejected"
            self.db.commit()
            self.db.refresh(invitation)
            return invitation
        return None

    def expire_invitation(self, invitation_id: str) -> Optional[Invitation]:
        """
        Mark an invitation as expired.

        Args:
            invitation_id: Invitation identifier

        Returns:
            Updated Invitation object or None if not found
        """
        invitation = self.get_by_id(invitation_id)
        if invitation:
            invitation.status = "expired"
            self.db.commit()
            self.db.refresh(invitation)
            return invitation
        return None

    def delete(self, invitation_id: str) -> bool:
        """
        Delete an invitation.

        Args:
            invitation_id: Invitation identifier

        Returns:
            True if deleted, False if not found
        """
        invitation = self.get_by_id(invitation_id)
        if invitation:
            self.db.delete(invitation)
            self.db.commit()
            return True
        return False
