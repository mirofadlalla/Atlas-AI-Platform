"""
Authentication and authorization routes.

Handles user registration, login, invitation management, and admin approval workflows.
Also handles multi-tenant SaaS registration for new organizations.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.schema.auth_admin import UserCreate, Token, UserLogin
from app.schema.invitation_requests import (
    SendInvitationRequest,
    InvitationResponse,
    ValidateInvitationRequest,
    InvitationDetailsResponse,
    RegisterViaInvitationRequest,
    ResendInvitationRequest,
    PendingInvitationsResponse,
    ResendInvitationResponse
)

from app.core.db import get_db
from app.services.auth_services.auth_service import get_current_user, require_admin
from app.services.auth_services.auth_admin_service import AuthService
from app.services.invitation_service import InvitationService
from app.repositories.user_repository import UserRepository
from app.controllers.auth_controller import AuthController
from app.core.rate_limitizer import rate_limit, ip_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth"
)


# ==================== Tenant Registration (SaaS) ====================

from app.schema.tenant_schema import TenantRegistrationRequest, TenantRegistrationResponse


@router.post("/tenant/register", response_model=TenantRegistrationResponse)
def register_tenant(request: TenantRegistrationRequest, db: Session = Depends(get_db)):
    from app.services.tenant_registration_service import TenantRegistrationService
    """
    Register a new tenant (SaaS admin registration).
    Creates organization and first admin user.
    
    This endpoint allows new organizations to create their own Atlas AI workspace.
    
    Args:
        request: Tenant and admin registration data
        db: Database session
        
    Returns:
        Tenant ID, admin user token, and access information
        
    Raises:
        HTTPException: If organization or email already exists
    """
    service = TenantRegistrationService(db)
    return service.register_tenant(request)


# ==================== Basic Authentication ====================

@router.post("/register", response_model=Token)
def register(user: UserCreate, request: Request, db: Session = Depends(get_db)):
    """
    Register a new admin user and create tenant.

    Rate-limited per client IP (5 requests/minute) to prevent mass account creation.
    """
    ip_rate_limit(client_ip=request.client.host, endpoint="register")
    return AuthController.register(user, db)


@router.post("/login", response_model=Token)
def login(user: UserLogin, request: Request, db: Session = Depends(get_db)):
    """
    Login user and return access token.

    Rate-limited per client IP (10 requests/minute) to prevent brute-force
    and credential-stuffing attacks.
    """
    ip_rate_limit(client_ip=request.client.host, endpoint="login")
    return AuthController.login(user, db)


@router.get("/profile")
def get_my_profile(current_user=Depends(get_current_user)):
    """
    Get current user's profile information.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User profile data
    """
    from app.services.user_profile_service import UserProfileService
    service = UserProfileService()
    return service.get_profile(current_user)


# ==================== Invitation Management ====================

@router.post("/invitations/send")
def send_invitation(
    request: SendInvitationRequest,
    current_admin = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Send invitation to a new user (admin only).
    
    Args:
        request: Invitation request with email and tenant
        current_admin: Current authenticated admin user object
        db: Database session
        
    Returns:
        Invitation details with token
    """
    from app.services.invitation_management_service import InvitationManagementService
    
    invitation_service = InvitationManagementService(db)
    return invitation_service.send_invitation(
        invited_email=request.invited_email,
        invited_by_id=current_admin.id,
        tenant_id=str(current_admin.tenant_id),  # Always from JWT — never trust client
        admin_id=current_admin.id
    )


@router.get("/invitations/validate")
def validate_invitation(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Validate an invitation token and get details.
    
    Args:
        token: Invitation token
        db: Database session
        
    Returns:
        Invitation details if valid
    """
    from app.services.invitation_management_service import InvitationManagementService
    
    service = InvitationManagementService(db)
    return service.validate_invitation(token)


@router.post("/register-via-invitation")
def register_via_invitation(
    request: RegisterViaInvitationRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new user using an invitation token.
    
    Args:
        request: Registration request with invitation token and password
        db: Database session
        
    Returns:
        Access token for newly registered user
    """
    from app.services.invitation_management_service import InvitationManagementService
    
    service = InvitationManagementService(db)
    return service.register_via_invitation(
        token=request.token,
        name=request.name,
        password=request.password,
        tenant_id=request.tenant_id
    )


@router.get("/invitations/pending")
def get_pending_invitations(
    current_admin = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get all pending invitations sent by current admin.
    """
    from app.services.invitation_management_service import InvitationManagementService
    
    invitation_service = InvitationManagementService(db)
    return invitation_service.get_pending_invitations(current_admin.id)


@router.post("/invitations/resend")
def resend_invitation(
    request: ResendInvitationRequest,
    current_admin = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Resend an invitation (generate new token).
    """
    from app.services.invitation_management_service import InvitationManagementService
    
    invitation_service = InvitationManagementService(db)
    return invitation_service.resend_invitation(request.token)


# ==================== Admin Approval Workflow ====================

@router.get("/pending-approvals")
def get_pending_approvals(
    current_admin = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get list of pending user approvals (admin only).
    """
    from app.services.user_approval_service import UserApprovalService
    
    service = UserApprovalService(db)
    pending_users = service.get_pending_approvals()
    
    return {
        "total": len(pending_users),
        "pending_users": [
            {
                "user_id": u.id,
                "name": u.name,
                "email": u.email,
                "created_at": u.created_at
            }
            for u in pending_users
        ]
    }


@router.post("/approve-user/{user_id}")
def approve_user(
    user_id: str,
    current_admin = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Approve a pending user registration (admin only).
    """
    from app.services.user_approval_service import UserApprovalService
    
    service = UserApprovalService(db)
    return service.approve_user(user_id, current_admin.id)


@router.post("/reject-user/{user_id}")
def reject_user(
    user_id: str,
    current_admin = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reject a pending user registration (admin only).
    """
    from app.services.user_approval_service import UserApprovalService
    
    service = UserApprovalService(db)
    return service.reject_user(user_id, current_admin.id)