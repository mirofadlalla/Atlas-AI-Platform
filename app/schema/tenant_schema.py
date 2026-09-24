from pydantic import BaseModel


class TenantRegistrationRequest(BaseModel):
    """Request model for SaaS tenant registration."""

    organization_name: str
    admin_email: str
    admin_password: str
    admin_name: str = "Admin"
    plan: str = "starter"  # Default plan for new organizations


class TenantRegistrationResponse(BaseModel):
    """Response model for SaaS tenant registration.

    Note: no ``access_token`` field — registration is now pending super admin
    approval and the admin cannot log in until the tenant is activated.
    """

    tenant_id: str
    admin_id: str
    organization_name: str
    admin_email: str
    plan: str = "starter"
    status: str = "pending"
    message: str
