from pydantic import BaseModel


class TenantRegistrationRequest(BaseModel):
    """Request model for SaaS tenant registration"""

    organization_name: str
    admin_email: str
    admin_password: str
    admin_name: str = "Admin"
    plan: str = "starter"  # Default plan for new organizations


class TenantRegistrationResponse(BaseModel):
    """Response model for SaaS tenant registration"""

    tenant_id: str
    admin_id: str
    organization_name: str
    access_token: str
    message: str
    plan: str = "starter"
