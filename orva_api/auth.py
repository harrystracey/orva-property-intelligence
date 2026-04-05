"""
JWT authentication for ORVA API.
Replaces streamlit-authenticator YAML credentials.
Users loaded from client_data/users.json (not hardcoded).
"""

import json
import logging
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS, CLIENT_DATA_DIR

logger = logging.getLogger("orva_api")

security = HTTPBearer()

USERS_FILE = CLIENT_DATA_DIR / "users.json"


def _load_users() -> dict:
    """Load users from client_data/users.json."""
    if not USERS_FILE.exists():
        logger.error("users.json not found at %s", USERS_FILE)
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)


def _save_users(users: dict):
    """Save users back to client_data/users.json."""
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


USERS = _load_users()


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
