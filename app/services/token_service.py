from jose import JWTError, jwt
from datetime import datetime, timedelta
import os

from app.core.config import settings

SECRET_KEY = settings.api_secret_key or os.getenv("SECRET_KEY", "atlas_ai_default_secret_key_change_in_prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Create a JWT access token with the given data and expiration time
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token : str) :
    return jwt.decode(token, SECRET_KEY, ALGORITHM)