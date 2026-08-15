"""
Authentication and authorization routes.

Thin HTTP adapter — all business logic lives in AuthController.
"""

import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.schema.auth_admin import UserCreate, Token, UserLogin
from app.schema.invitation_requests import (
    SendInvitationRequest,
    RegisterViaInvitationRequest,
    ResendInvitationRequest,
)
from app.schema.tenant_schema import (
    TenantRegistrationRequest,
    TenantRegistrationResponse,
)

from app.core.db import get_db
from app.services.auth_services.auth_service import get_current_user, require_admin
from app.controllers.auth_controller import AuthController
from app.core.rate_limitizer import ip_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")


# ==================== Tenant Registration (SaaS) ====================


@router.post("/tenant/register", response_model=TenantRegistrationResponse)
def register_tenant(request: TenantRegistrationRequest, db: Session = Depends(get_db)):
    """Register a new tenant (SaaS admin registration)."""
    return AuthController.register_tenant(request, db)


# ==================== Basic Authentication ====================


@router.post("/register", response_model=Token)
def register(user: UserCreate, request: Request, db: Session = Depends(get_db)):
    """Register a new admin user and create tenant. Rate-limited per IP."""
    ip_rate_limit(client_ip=request.client.host, endpoint="register")
    return AuthController.register(user, db)


@router.post("/login", response_model=Token)
def login(user: UserLogin, request: Request, db: Session = Depends(get_db)):
    """Login user and return access token. Rate-limited per IP."""
    ip_rate_limit(client_ip=request.client.host, endpoint="login")
    return AuthController.login(user, db)


@router.get("/profile")
def get_my_profile(current_user=Depends(get_current_user)):
    """Get current user's profile information."""
    return AuthController.get_profile(current_user)


# ==================== Invitation Management ====================


@router.post("/invitations/send")
def send_invitation(
    request: SendInvitationRequest,
    current_admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Send invitation to a new user (admin only)."""
    return AuthController.send_invitation(
        invited_email=request.invited_email,
        invited_by_id=current_admin.id,
        tenant_id=str(current_admin.tenant_id),
        admin_id=current_admin.id,
        db=db,
    )


@router.get("/invitations/validate")
def validate_invitation(token: str, db: Session = Depends(get_db)):
    """Validate an invitation token and return its details."""
    return AuthController.validate_invitation(token, db)


@router.post("/register-via-invitation")
def register_via_invitation(
    request: RegisterViaInvitationRequest, db: Session = Depends(get_db)
):
    """Register a new user using an invitation token."""
    return AuthController.register_via_invitation(
        token=request.token,
        name=request.name,
        password=request.password,
        tenant_id=request.tenant_id,
        db=db,
    )


@router.get("/invitations/pending")
def get_pending_invitations(
    current_admin=Depends(require_admin), db: Session = Depends(get_db)
):
    """Get all pending invitations sent by the current admin."""
    return AuthController.get_pending_invitations(current_admin.id, db)


@router.post("/invitations/resend")
def resend_invitation(
    request: ResendInvitationRequest,
    current_admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Resend an invitation (generates a new token)."""
    return AuthController.resend_invitation(request.token, db)


@router.delete("/invitations/{invitation_id}")
def delete_invitation(
    invitation_id: str,
    current_admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Permanently invalidate and delete an invitation owned by this admin."""
    return AuthController.delete_invitation(invitation_id, current_admin.tenant_id, db)


# ==================== Admin Approval Workflow ====================


@router.get("/pending-approvals")
def get_pending_approvals(
    current_admin=Depends(require_admin), db: Session = Depends(get_db)
):
    """Get list of pending user approvals (admin only)."""
    return AuthController.get_pending_approvals(current_admin.tenant_id, db)


@router.post("/approve-user/{user_id}")
def approve_user(
    user_id: str, current_admin=Depends(require_admin), db: Session = Depends(get_db)
):
    """Approve a pending user registration (admin only)."""
    return AuthController.approve_user(user_id, current_admin.id, db)


@router.post("/reject-user/{user_id}")
def reject_user(
    user_id: str, current_admin=Depends(require_admin), db: Session = Depends(get_db)
):
    """Reject a pending user registration (admin only)."""
    return AuthController.reject_user(user_id, current_admin.id, db)
