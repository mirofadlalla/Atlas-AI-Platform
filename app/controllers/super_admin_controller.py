"""
Super Admin Controller.

Thin HTTP adapter layer that delegates all super admin operations to
SuperAdminService.  Route handlers import this class and call its static
methods — no business logic lives here.
"""

import os

from sqlalchemy.orm import Session

from app.schema.super_admin_schema import (
    CreateSuperAdminRequest,
    UpdateTenantRequest,
    UpdateUserRoleRequest,
    UpdateUserStatusRequest,
)
from app.services.super_admin_service import SuperAdminService


class SuperAdminController:
    """Controller that exposes SuperAdminService methods to the route layer."""

    # ── Dashboard ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_dashboard_stats(db: Session):
        """Return platform-wide statistics (tenant count, user count, per-tenant summaries)."""
        return SuperAdminService(db).get_dashboard_stats()

    # ── Tenants ───────────────────────────────────────────────────────────────

    @staticmethod
    def get_all_tenants(db: Session):
        """Return all tenants with their user counts."""
        return SuperAdminService(db).get_all_tenants()

    @staticmethod
    def get_pending_tenants(db: Session):
        """Return tenants awaiting super admin approval."""
        return SuperAdminService(db).get_pending_tenants()

    @staticmethod
    def approve_tenant(tenant_id: str, db: Session):
        """Approve a pending tenant registration and activate its admin users."""
        return SuperAdminService(db).approve_tenant(tenant_id)

    @staticmethod
    def reject_tenant(tenant_id: str, reason: str, db: Session):
        """Reject a pending tenant registration."""
        return SuperAdminService(db).reject_tenant(tenant_id, reason)

    @staticmethod
    def get_tenant_detail(tenant_id: str, db: Session):
        """Return detailed tenant information including its users."""
        return SuperAdminService(db).get_tenant_detail(tenant_id)

    @staticmethod
    def update_tenant(tenant_id: str, request: UpdateTenantRequest, db: Session):
        """Partially update a tenant's name and/or plan."""
        return SuperAdminService(db).update_tenant(tenant_id, request)

    @staticmethod
    def delete_tenant(tenant_id: str, db: Session):
        """Delete a tenant and cascade-delete all of its users."""
        return SuperAdminService(db).delete_tenant(tenant_id)

    # ── Users ─────────────────────────────────────────────────────────────────

    @staticmethod
    def get_all_users(db: Session):
        """Return all users across all tenants."""
        return SuperAdminService(db).get_all_users()

    @staticmethod
    def get_tenant_users(tenant_id: str, db: Session):
        """Return all users belonging to a specific tenant."""
        return SuperAdminService(db).get_tenant_users(tenant_id)

    @staticmethod
    def delete_user(user_id: str, requester_id: str, db: Session):
        """Delete a user (cannot delete self)."""
        return SuperAdminService(db).delete_user(user_id, requester_id)

    @staticmethod
    def update_user_role(user_id: str, request: UpdateUserRoleRequest, db: Session):
        """Change a user's role."""
        return SuperAdminService(db).update_user_role(user_id, request.role)

    @staticmethod
    def update_user_status(user_id: str, request: UpdateUserStatusRequest, db: Session):
        """Change a user's approval status."""
        return SuperAdminService(db).update_user_status(
            user_id, request.approval_status
        )

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    @staticmethod
    def create_super_admin(request: CreateSuperAdminRequest, db: Session):
        """Create the first super admin account using the secret key from env."""
        secret_key = os.getenv("SUPER_ADMIN_SECRET_KEY", "")
        return SuperAdminService(db).create_super_admin(request, secret_key)
