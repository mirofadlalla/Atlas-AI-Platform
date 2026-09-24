"""
Super Admin Pydantic schemas.

Defines all request and response models for the super admin dashboard API.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TenantSummary(BaseModel):
    """Serialised view of a tenant including its current user count and status."""

    id: str
    name: str
    plan: str
    status: str  # 'pending' | 'active' | 'rejected'
    created_at: datetime
    user_count: int

    model_config = ConfigDict(from_attributes=True)


class UserSummary(BaseModel):
    """Serialised view of a user for super admin listings."""

    id: str
    name: str
    email: str
    role: str
    approval_status: str
    created_at: datetime
    tenant_id: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class TenantDetailResponse(BaseModel):
    """Detailed tenant view that includes the list of its users."""

    tenant: TenantSummary
    users: List[UserSummary]


class UpdateUserRoleRequest(BaseModel):
    """Request body for changing a user's role."""

    role: str  # must be 'user', 'admin', or 'super_admin'


class UpdateUserStatusRequest(BaseModel):
    """Request body for changing a user's approval status."""

    approval_status: str  # 'approved', 'pending', or 'rejected'


class UpdateTenantRequest(BaseModel):
    """Request body for partial tenant updates (name and/or plan)."""

    name: Optional[str] = None
    plan: Optional[str] = None


class ApproveTenantRequest(BaseModel):
    """Optional request body for approving a tenant registration.

    ``note`` is stored in the approval log (future use) and sent in the
    approval email to the tenant admin.
    """

    note: Optional[str] = None


class RejectTenantRequest(BaseModel):
    """Request body for rejecting a tenant registration.

    ``reason`` is sent to the tenant admin in the rejection email so they
    understand why their application was declined.
    """

    reason: str = "Your registration did not meet our requirements."


class SuperAdminStatsResponse(BaseModel):
    """Dashboard-level statistics returned for the super admin stats endpoint."""

    total_tenants: int
    total_users: int
    pending_tenants: int
    tenants: List[TenantSummary]


class CreateSuperAdminRequest(BaseModel):
    """Request body for bootstrapping the first super admin account."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100)
    secret_key: str  # must match the SUPER_ADMIN_SECRET_KEY environment variable
