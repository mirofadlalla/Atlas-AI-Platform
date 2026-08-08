from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.repositories.user_repository import UserRepository

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

    # 3. Enforce approval status — pending/rejected users are blocked even with a valid JWT.
    #    This re-checks the DB on every request, so revoking approval takes effect immediately.
    if user.approval_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not approved. Please contact your administrator.",
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
