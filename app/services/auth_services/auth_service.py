from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.repositories.user_repository import UserRepository

from app.services.token_service import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_current_user(access_token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 1. decode token
        payload = decode_access_token(token=access_token)
        email: str = payload.get("sub")
        tenant_id: int = payload.get("tenant_id")
        
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 2. make sure that use is already exist in db
    user_repo = UserRepository(db)
    user = user_repo.find_by_email(email)
    
    if user is None:
        raise credentials_exception
        
    return user # return user

def require_admin(current_user = Depends(get_current_user)):
    """Enforce that current authenticated user has admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user