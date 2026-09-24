from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.repositories.user_repository import UserRepository
from app.repositories.tenant_repository import TenantRepository

from app.services.token_service import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    access_token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 1. Decode and validate token signature + expiry
        payload = decode_access_token(token=access_token)
        email: str = payload.get("sub")

        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 2. Verify the user still exists in the database
    user_repo = UserRepository(db)
    user = user_repo.find_by_email(email)

    if user is None:
        raise credentials_exception

    # 3. Enforce per-user approval status — re-checked on every request so
    #    revoking approval takes effect immediately even for active JWTs.
    if user.approval_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not approved. Please contact your administrator.",
        )

    # 4. Enforce tenant-level approval status — blocks all users of a tenant
    #    the moment a super admin rejects or suspends that tenant.
    #    Super admin accounts (tenant_id is None) are exempt.
    if user.tenant_id is not None:
        tenant = TenantRepository(db).find_by_id(str(user.tenant_id))
        if tenant and tenant.status == "pending":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Your organization's registration is awaiting super admin "
                    "approval. You will be notified once access is granted."
                ),
            )
        if tenant and tenant.status == "rejected":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your organization's registration was not approved.",
            )

    return user


def require_admin(current_user=Depends(get_current_user)):
    """Enforce that the current authenticated user has the admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def require_super_admin(current_user=Depends(get_current_user)):
    """Enforce that the current authenticated user has the super_admin role."""
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin privileges required",
        )
    return current_user


def require_admin_or_super_admin(current_user=Depends(get_current_user)):
    """Enforce that the current authenticated user is either an admin or a super_admin."""
    if current_user.role not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or super admin privileges required",
        )
    return current_user
