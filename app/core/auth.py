from jose import JWTError, jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os

SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT => HEADER.PAYLOAD.SIGNATURE

# Utility functions for password hashing and token creation/verification
def password_hash(password : str) -> str :
    return pwd_context.hash(password)

# Verify the password against the hashed password
def verify_password(plain_password : str, hashed_password : str) -> bool :
    return pwd_context.verify(plain_password, hashed_password)

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