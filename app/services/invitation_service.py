"""
Service for managing user invitations and invitation-based signup flow.

Handles invitation creation, validation, acceptance, and user registration.
"""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.repositories.invitation_repository import InvitationRepository
from app.repositories.user_repository import UserRepository
from app.models.user import Users

logger = logging.getLogger(__name__)


class InvitationService:
    """Service for managing invitations and invitation-based registration."""
    
    TOKEN_EXPIRY_DAYS = 7
    TOKEN_LENGTH = 32
    
    def __init__(self, db: Session):
        """
        Initialize the service with database session.
        
        Args:
            db: SQLAlchemy Session
        """
        self.db = db
        self.invitation_repo = InvitationRepository(db)
        self.user_repo = UserRepository(db)
    
    @staticmethod
    def generate_invitation_token() -> str:
        """
        Generate a secure random token for invitation links.
        
        Returns:
            Secure random token (hex string)
        """
        return secrets.token_hex(InvitationService.TOKEN_LENGTH)
    
    def send_invitation(
        self,
        invited_email: str,
        invited_by_id: str,
        tenant_id: str,
        **kwargs
    ):
        """
        Create and send an invitation to a user.
        
        Args:
            invited_email: Email of the user to invite
            invited_by_id: User ID of the admin sending the invitation
            tenant_id: Tenant ID for which to invite the user
            **kwargs: Additional data (name, message, etc.)
            
        Returns:
            Created Invitation object
            
        Raises:
            ValueError: If invited user already exists in tenant
        """
        # Check if user already exists
        existing_user = self.user_repo.find_by_email(invited_email)
        if existing_user and existing_user.tenant_id == tenant_id:
            raise ValueError(f"User {invited_email} already exists in this tenant")
        
        # Check if active invitation already exists
        existing_invitations = self.invitation_repo.get_by_email(invited_email)
        active_invitation = next( # ده generator expression بيشوف لو في دعوة صالحة موجودة بنفس الإيميل
            (inv for inv in existing_invitations if inv.is_valid()),
            None
        )
        if active_invitation:
            raise ValueError(f"Active invitation already exists for {invited_email}")
        
        # Generate unique token
        token = self.generate_invitation_token()
        expires_at = datetime.utcnow() + timedelta(days=self.TOKEN_EXPIRY_DAYS)
        
        # Create invitation
        invitation = self.invitation_repo.create(
            invited_email=invited_email,
            invited_by=invited_by_id,
            tenant_id=tenant_id,
            token=token,
            expires_at=expires_at
        )
        
        logger.info(
            f"Invitation created for {invited_email} by admin {invited_by_id} "
            f"in tenant {tenant_id}"
        )
        
        return invitation
    
    def validate_invitation(self, token: str):
        """
        Validate an invitation token.
        
        Args:
            token: Invitation token to validate
            
        Returns:
            Invitation object if valid, None otherwise
        """
        invitation = self.invitation_repo.get_by_token(token)
        
        if not invitation:
            logger.warning(f"Invitation token not found: {token}")
            return None
        
        if not invitation.is_valid():
            if invitation.status != 'pending':
                logger.warning(
                    f"Invitation token invalid - status: {invitation.status}, token: {token}"
                )
            elif invitation.is_expired():
                logger.warning(f"Invitation token expired: {token}")
            return None
        
        return invitation
    
    def get_invitation_details(self, token: str) -> Optional[dict]:
        """
        Get details about an invitation without accepting it.
        
        Args:
            token: Invitation token
            
        Returns:
            Dictionary with invitation details or None if invalid
        """
        invitation = self.validate_invitation(token)
        if not invitation:
            return None
        
        return {
            'invited_email': invitation.invited_email,
            'tenant_id': invitation.tenant_id,
            'created_at': invitation.created_at.isoformat(),
            'expires_at': invitation.expires_at.isoformat(),
            'is_expired': invitation.is_expired()
        }
    
    def accept_invitation_and_register(
        self,
        token: str,
        name: str,
        password_hash: str,
        tenant_id: str
    ) -> Optional[Users]:
        """
        Accept an invitation and register a new user.
        
        Args:
            token: Invitation token
            name: User's full name
            password_hash: Hashed password
            tenant_id: Tenant ID (must match invitation tenant)
            
        Returns:
            Created Users object or None if registration failed
            
        Raises:
            ValueError: If invitation is invalid or doesn't match tenant
        """
        invitation = self.validate_invitation(token)
        if not invitation:
            raise ValueError("Invalid or expired invitation token")
        
        if invitation.tenant_id != tenant_id:
            raise ValueError("Tenant mismatch - invitation is not for this tenant")
        
        # Check if user already exists
        existing_user = self.user_repo.find_by_email(invitation.invited_email)
        if existing_user:
            raise ValueError(f"User {invitation.invited_email} already registered")
        
        try:
            # Create user with pending approval status
            user = self.user_repo.create(
                name=name,
                email=invitation.invited_email,
                hashed_password=password_hash,
                tenant_id=tenant_id,
                role="user",  # Default role for invited users
                approval_status="pending"  # Require admin approval before user can access services
            )
            
            # Accept invitation
            self.invitation_repo.accept_invitation(token, user.id)
            
            logger.info(
                f"User registered via invitation: {user.email} in tenant {tenant_id}"
            )
            
            return user
            
        except Exception as e:
            logger.error(f"Error registering user from invitation: {e}")
            raise
    
    def reject_invitation(self, token: str) -> bool:
        """
        Reject an invitation.
        
        Args:
            token: Invitation token
            
        Returns:
            True if successful, False otherwise
        """
        invitation = self.invitation_repo.reject_invitation(token)
        if invitation:
            logger.info(f"Invitation rejected: {invitation.invited_email}")
            return True
        return False
    
    def resend_invitation(self, token: str) -> Optional[str]:
        """
        Resend an invitation (generate new token, mark old as expired).
        
        Args:
            token: Current invitation token
            
        Returns:
            New invitation token or None if unable to resend
        """
        old_invitation = self.invitation_repo.get_by_token(token)
        if not old_invitation or old_invitation.status != 'pending':
            logger.warning(f"Cannot resend invitation: {token}")
            return None
        
        try:
            # Expire old invitation
            self.invitation_repo.expire_invitation(old_invitation.invitation_id)
            
            # Create new invitation
            new_invitation = self.send_invitation(
                invited_email=old_invitation.invited_email,
                invited_by_id=old_invitation.invited_by,
                tenant_id=old_invitation.tenant_id
            )
            
            logger.info(
                f"Invitation resent to {old_invitation.invited_email} - "
                f"New token: {new_invitation.token[:8]}..."
            )
            
            return new_invitation.token
            
        except Exception as e:
            logger.error(f"Error resending invitation: {e}")
            return None
    
    def get_pending_invitations_for_admin(self, admin_id: str) -> list:
        """
        Get all pending invitations sent by an admin.
        
        Args:
            admin_id: Admin user ID
            
        Returns:
            List of pending invitations
        """
        invitations = self.invitation_repo.get_sent_by_admin(admin_id, status='pending')
        return invitations
    
    def cancel_invitation(self, invitation_id: str) -> bool:
        """
        Cancel a pending invitation.
        
        Args:
            invitation_id: Invitation ID
            
        Returns:
            True if successful, False otherwise
        """
        invitation = self.invitation_repo.get_by_id(invitation_id)
        if invitation and invitation.status == 'pending':
            self.invitation_repo.expire_invitation(invitation_id)
            logger.info(f"Invitation cancelled: {invitation_id}")
            return True
        return False
