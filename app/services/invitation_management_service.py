"""Service for invitation management with response formatting."""

import logging
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.services.invitation_service import InvitationService
from app.services.hash_service import password_hash
from app.services.token_service import create_access_token
from app.core.rate_limitizer import rate_limit

logger = logging.getLogger(__name__)


class InvitationManagementService:
    """Service for managing invitations with proper abstraction."""

    def __init__(self, db: Session):
        self.db = db
        self.invitation_service = InvitationService(db)

    def send_invitation(
        self, invited_email: str, invited_by_id: str, tenant_id: str, admin_id: str
    ) -> dict:
        """
        Send invitation to a new user.

        Args:
            invited_email: Email of user to invite
            invited_by_id: ID of admin sending invitation
            tenant_id: Tenant ID
            admin_id: Admin ID for rate limiting

        Returns:
            Invitation details including token

        Raises:
            HTTPException: On validation or database errors
        """
        try:
            logger.info(
                f"Sending invitation to {invited_email} by admin {invited_by_id} for tenant {tenant_id}"
            )

            # Apply rate limiting
            rate_limit(
                user_id=admin_id, role="admin", endpoint="/auth/invitations/send"
            )

            invitation = self.invitation_service.send_invitation(
                invited_email=invited_email,
                invited_by_id=invited_by_id,
                tenant_id=tenant_id,
            )

            logger.info(f"Invitation sent successfully: {invitation.invitation_id}")

            return {
                "invitation_id": str(invitation.invitation_id),
                "invited_email": invitation.invited_email,
                "token": invitation.token,
                "status": invitation.status,
                "created_at": (
                    invitation.created_at.isoformat() if invitation.created_at else None
                ),
                "expires_at": (
                    invitation.expires_at.isoformat() if invitation.expires_at else None
                ),
                "message": "Invitation sent successfully",
            }
        except ValueError as e:
            logger.error(f"Validation error sending invitation: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            logger.error(f"Error sending invitation: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send invitation: {str(e)}",
            )

    def validate_invitation(self, token: str) -> dict:
        """
        Validate invitation token and get details.

        Args:
            token: Invitation token

        Returns:
            Invitation details

        Raises:
            HTTPException: If token invalid or expired
        """
        try:
            details = self.invitation_service.get_invitation_details(token)

            if not details:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired invitation token",
                )

            return details
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error validating invitation: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to validate invitation",
            )

    def register_via_invitation(
        self, token: str, name: str = None, password: str = None, tenant_id: str = None
    ) -> dict:
        """
        Register a new user via invitation token.

        Args:
            token: Invitation token
            name: User's full name (optional; will use email prefix if not provided)
            password: User's password (plain text)
            tenant_id: Tenant ID (optional; will be extracted from invitation if not provided)

        Returns:
            Access token and user details

        Raises:
            HTTPException: On validation or registration errors
        """
        try:
            # Validate invitation and extract tenant_id and name if not provided
            details = self.invitation_service.get_invitation_details(token)
            if not details:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired invitation token",
                )

            # Never trust tenant_id from the request/link; the invitation token
            # is the authoritative tenant binding.
            tenant_id = details.get("tenant_id")
            if not tenant_id:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not determine tenant from invitation")

            # Extract name from invitation or use email prefix if not provided
            if not name:
                invited_email = details.get("invited_email")
                if invited_email:
                    # Use email prefix as name (e.g., "user@example.com" -> "user")
                    name = invited_email.split("@")[0]
                else:
                    name = "User"  # Fallback name

            # Hash password
            password_hash_obj = password_hash(password)

            # Register user
            user = self.invitation_service.accept_invitation_and_register(
                token=token,
                name=name,
                password_hash=password_hash_obj,
                tenant_id=tenant_id,
            )

            # Generate access token
            access_token = create_access_token(
                {
                    "sub": user.email,
                    "tenant_id": user.tenant_id,
                    "role": user.role,
                    "approval_status": user.approval_status,
                }
            )

            logger.info(f"User registered via invitation: {user.email}")

            message = (
                "Please await admin approval"
                if user.approval_status == "pending"
                else "Registration successful"
            )

            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user_id": user.id,
                "email": user.email,
                "approval_status": user.approval_status,
                "message": message,
            }
        except ValueError as e:
            logger.error(f"Invalid invitation data: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error registering via invitation: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to register user",
            )

    def get_pending_invitations(self, admin_id: str) -> dict:
        """
        Get all pending invitations for admin.

        Args:
            admin_id: ID of admin

        Returns:
            List of pending invitations

        Raises:
            HTTPException: On database errors
        """
        try:
            logger.info(f"Retrieving pending invitations for admin_id: {admin_id}")
            invitations = self.invitation_service.get_pending_invitations_for_admin(
                admin_id
            )
            logger.info(f"Found {len(invitations)} pending invitations")

            # Convert datetime objects to ISO format strings for JSON serialization
            invitations_list = []
            for inv in invitations:
                try:
                    invitations_list.append(
                        {
                            "invitation_id": str(inv.invitation_id),
                            "invited_email": inv.invited_email,
                            "token": getattr(inv, "token", None),
                            "status": inv.status,
                            "created_at": (
                                inv.created_at.isoformat() if inv.created_at else None
                            ),
                            "expires_at": (
                                inv.expires_at.isoformat() if inv.expires_at else None
                            ),
                        }
                    )
                except Exception as e:
                    logger.error(
                        f"Error serializing invitation {inv.invitation_id}: {e}"
                    )
                    # Skip this invitation if serialization fails
                    continue

            return {"total": len(invitations_list), "invitations": invitations_list}
        except Exception as e:
            logger.error(f"Error retrieving pending invitations: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve invitations: {str(e)}",
            )

    def resend_invitation(self, token: str) -> dict:
        """
        Resend invitation (generate new token).

        Args:
            token: Current invitation token

        Returns:
            New invitation token

        Raises:
            HTTPException: If cannot resend
        """
        try:
            new_token = self.invitation_service.resend_invitation(token)

            if not new_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot resend this invitation",
                )

            logger.info("Invitation token resent")

            return {
                "success": True,
                "new_token": new_token,
                "message": "Invitation resent successfully",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resending invitation: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to resend invitation",
            )
