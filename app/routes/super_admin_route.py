"""
Super Admin routes.

Thin HTTP adapter — all business logic lives in SuperAdminController.

Route summary
─────────────
POST  /super-admin/setup                            — bootstrap first super admin (no auth)
GET   /super-admin/stats                            — platform-wide dashboard stats
GET   /super-admin/tenants                          — list all tenants
GET   /super-admin/tenants/pending                  — list tenants awaiting approval
POST  /super-admin/tenants/{tenant_id}/approve      — approve a pending tenant
POST  /super-admin/tenants/{tenant_id}/reject       — reject a pending tenant
GET   /super-admin/tenants/{tenant_id}              — tenant detail + user list
PATCH /super-admin/tenants/{tenant_id}              — update tenant name/plan
DEL   /super-admin/tenants/{tenant_id}              — delete tenant (cascades users)
GET   /super-admin/users                            — all users across all tenants
GET   /super-admin/tenants/{tenant_id}/users        — users of a specific tenant
DEL   /super-admin/users/{user_id}                 — delete a user
PATCH /super-admin/users/{user_id}/role             — change user role
PATCH /super-admin/users/{user_id}/status           — change approval status
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.super_admin_controller import SuperAdminController
from app.core.db import get_db
from app.schema.super_admin_schema import (
    ApproveTenantRequest,
    CreateSuperAdminRequest,
    RejectTenantRequest,
    SuperAdminStatsResponse,
    TenantDetailResponse,
    TenantSummary,
    UpdateTenantRequest,
    UpdateUserRoleRequest,
    UpdateUserStatusRequest,
    UserSummary,
)
from app.services.auth_services.auth_service import require_super_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/super-admin")


# ── Bootstrap (no authentication required) ────────────────────────────────────


@router.post("/setup", response_model=UserSummary)
def setup_super_admin(request: CreateSuperAdminRequest, db: Session = Depends(get_db)):
    """Bootstrap the first super admin account.

    Validates the ``secret_key`` in the request body against the
    ``SUPER_ADMIN_SECRET_KEY`` environment variable.  No JWT is required.
    """
    return SuperAdminController.create_super_admin(request, db)


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("/stats", response_model=SuperAdminStatsResponse)
def get_dashboard_stats(_=Depends(require_super_admin), db: Session = Depends(get_db)):
    """Return platform-wide statistics: total tenants, pending tenants, users."""
    return SuperAdminController.get_dashboard_stats(db)


# ── Tenant management ─────────────────────────────────────────────────────────


@router.get("/tenants", response_model=list[TenantSummary])
def list_all_tenants(_=Depends(require_super_admin), db: Session = Depends(get_db)):
    """Return all tenants registered on the platform (all statuses)."""
    return SuperAdminController.get_all_tenants(db)


@router.get("/tenants/pending", response_model=list[TenantSummary])
def list_pending_tenants(_=Depends(require_super_admin), db: Session = Depends(get_db)):
    """Return all tenants currently awaiting super admin approval."""
    return SuperAdminController.get_pending_tenants(db)


@router.post("/tenants/{tenant_id}/approve", response_model=TenantDetailResponse)
def approve_tenant(
    tenant_id: str,
    request: ApproveTenantRequest = ApproveTenantRequest(),
    _=Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Approve a pending tenant registration.

    Activates the tenant and sets all pending users in that tenant to
    'approved' so the admin can log in immediately.  An approval email is
    dispatched to the tenant's admin user(s).
    """
    return SuperAdminController.approve_tenant(tenant_id, db)


@router.post("/tenants/{tenant_id}/reject", response_model=TenantDetailResponse)
def reject_tenant(
    tenant_id: str,
    request: RejectTenantRequest,
    _=Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Reject a pending tenant registration.

    Sets the tenant to 'rejected' and all its pending users to 'rejected'.
    A rejection email with the supplied reason is sent to the admin.
    """
    return SuperAdminController.reject_tenant(tenant_id, request.reason, db)


@router.get("/tenants/{tenant_id}", response_model=TenantDetailResponse)
def get_tenant_detail(
    tenant_id: str, _=Depends(require_super_admin), db: Session = Depends(get_db)
):
    """Return full detail for a single tenant including its user roster."""
    return SuperAdminController.get_tenant_detail(tenant_id, db)


@router.patch("/tenants/{tenant_id}", response_model=TenantSummary)
def update_tenant(
    tenant_id: str,
    request: UpdateTenantRequest,
    _=Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Partially update a tenant's name and/or plan."""
    return SuperAdminController.update_tenant(tenant_id, request, db)


@router.delete("/tenants/{tenant_id}")
def delete_tenant(
    tenant_id: str, _=Depends(require_super_admin), db: Session = Depends(get_db)
):
    """Delete a tenant and cascade-delete all of its users."""
    return SuperAdminController.delete_tenant(tenant_id, db)


# ── User management ───────────────────────────────────────────────────────────


@router.get("/users", response_model=list[UserSummary])
def list_all_users(_=Depends(require_super_admin), db: Session = Depends(get_db)):
    """Return all users across every tenant on the platform."""
    return SuperAdminController.get_all_users(db)


@router.get("/tenants/{tenant_id}/users", response_model=list[UserSummary])
def list_tenant_users(
    tenant_id: str, _=Depends(require_super_admin), db: Session = Depends(get_db)
):
    """Return all users belonging to a specific tenant."""
    return SuperAdminController.get_tenant_users(tenant_id, db)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    current_super_admin=Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Delete a user by ID (super admin cannot delete their own account)."""
    return SuperAdminController.delete_user(user_id, str(current_super_admin.id), db)


@router.patch("/users/{user_id}/role", response_model=UserSummary)
def update_user_role(
    user_id: str,
    request: UpdateUserRoleRequest,
    _=Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Change the role of any user on the platform."""
    return SuperAdminController.update_user_role(user_id, request, db)


@router.patch("/users/{user_id}/status", response_model=UserSummary)
def update_user_status(
    user_id: str,
    request: UpdateUserStatusRequest,
    _=Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Change the approval status of any user on the platform."""
    return SuperAdminController.update_user_status(user_id, request, db)
