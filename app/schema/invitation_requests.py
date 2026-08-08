"""
Pydantic schemas for invitation-related requests and responses.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, model_validator


class SendInvitationRequest(BaseModel):
    """Request to send an invitation to a user."""

    invited_email: EmailStr
    tenant_id: Optional[
        str
    ] = None  # Ignored — derived from the admin's JWT token server-side

    class Config:
        json_schema_extra = {"example": {"invited_email": "user@example.com"}}


class InvitationResponse(BaseModel):
    """Response containing invitation details."""

    invitation_id: str
    invited_email: str
    status: str
    created_at: datetime
    expires_at: datetime
    token: Optional[str] = None  # Only included when first created

    class Config:
        # بتخلي Pydantic يقدر يحول:
        # ORM object (زي SQLAlchemy model)
        # إلى:
        # Pydantic model مباشرة
        from_attributes = True


class ValidateInvitationRequest(BaseModel):
    """Request to validate an invitation token."""

    token: str

    class Config:
        json_schema_extra = {"example": {"token": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"}}


class InvitationDetailsResponse(BaseModel):
    """Response with invitation details."""

    invited_email: str
    tenant_id: str
    created_at: str
    expires_at: str
    is_expired: bool

    class Config:
        json_schema_extra = {
            "example": {
                "invited_email": "user@example.com",
                "tenant_id": "tenant-123",
                "created_at": "2024-02-24T10:00:00",
                "expires_at": "2024-03-02T10:00:00",
                "is_expired": False,
            }
        }


# class RegisterViaInvitationRequest(BaseModel):


class RegisterViaInvitationRequest(BaseModel):
    """Request to register a new user via invitation.

    Accepts either the flat shape::

        {"token": "...", "password": "..."}
        or
        {"token": "...", "name": "...", "password": "..."}

    or the nested token object shape some clients send::

        {"token": {"token": "...", "password": "..."}}

    name and tenant_id are optional and will be extracted from the invitation record if not provided.
    """

    token: str
    password: str
    name: Optional[str] = None
    tenant_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_token_shape(cls, values):
        tok = values.get("token")

        if isinstance(tok, dict):
            # Unwrap nested token object
            values["token"] = tok.get("token") or values.get("token")
            values["password"] = values.get("password") or tok.get("password")
            values["name"] = values.get("name") or tok.get("name")
            values["tenant_id"] = values.get("tenant_id") or tok.get("tenant_id")

        # Validate that required fields are present
        if not values.get("token"):
            raise ValueError("Missing required field: token")
        if not values.get("password"):
            raise ValueError("Missing required field: password")

        return values


class ResendInvitationRequest(BaseModel):
    """Request to resend an invitation."""

    token: str

    class Config:
        json_schema_extra = {"example": {"token": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"}}


class PendingInvitationsResponse(BaseModel):
    """Response containing list of pending invitations."""

    total: int
    invitations: list[InvitationResponse]


class ResendInvitationResponse(BaseModel):
    """Response after resending invitation."""

    success: bool
    message: str
    new_token: Optional[str] = None
