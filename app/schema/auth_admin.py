from pydantic import BaseModel, EmailStr, Field, field_validator


# Pydantic models for user authentication and token management
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100, strip_whitespace=True)
    tenant_name: str = Field(..., min_length=2, max_length=100, strip_whitespace=True)


# Token response model
class Token(BaseModel):
    access_token: str
    token_type: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)