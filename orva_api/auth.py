"""
JWT authentication for ORVA API.
Replaces streamlit-authenticator YAML credentials.
"""

import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS

security = HTTPBearer()

# Hardcoded users (migrated from credentials.yaml)
# In production, move to database
USERS = {
    "harry": {
        "name": "Harry",
        "email": "admin@orva.app",
        "password_hash": "PLACEHOLDER_HASH_SEE_AUTH_CONFIG",
    }
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode(), hashed_password.encode()
    )


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "name": USERS[username]["name"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def authenticate_user(username: str, password: str) -> str | None:
    user = USERS.get(username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return create_token(username)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        payload = jwt.decode(
            credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        username = payload.get("sub")
        if username not in USERS:
            raise HTTPException(status_code=401, detail="Invalid user")
        return {"username": username, "name": payload.get("name")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
