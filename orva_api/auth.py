"""
JWT authentication for ORVA API.
Replaces streamlit-authenticator YAML credentials.
"""

import json
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS, USERS_FILE

security = HTTPBearer()

# Fallback users when USERS_FILE doesn't exist, preserving the prior behavior
# so existing deployments keep working. New deployments should set USERS_FILE
# and delete the fallback.
_FALLBACK_USERS = {
    "harry": {
        "name": "Harry",
        "email": "admin@orva.app",
        "password_hash": "PLACEHOLDER_HASH_SEE_AUTH_CONFIG",
    }
}


def _load_users() -> dict:
    """Load users from USERS_FILE; fall back to _FALLBACK_USERS if missing."""
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return data
            print(f"[auth] {USERS_FILE} is empty or malformed; using fallback users")
        except Exception as e:
            print(f"[auth] failed to read {USERS_FILE} ({e}); using fallback users")
    return _FALLBACK_USERS


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


def _decode_token(token: str) -> dict:
    """Decode a JWT and resolve the user. Raises HTTPException(401) on failure."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if username not in USERS:
            raise HTTPException(status_code=401, detail="Invalid user")
        return {"username": username, "name": payload.get("name")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    return _decode_token(credentials.credentials)


# Optional-bearer variant for endpoints that may also accept a query-string
# token (EventSource can't send Authorization headers). Endpoints using this
# MUST resolve the token themselves via `get_user_from_request`.
_optional_bearer = HTTPBearer(auto_error=False)


def get_user_from_request(
    request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> dict:
    """
    Resolve the current user from either the Authorization header or a
    `?token=` query parameter. Use this only on SSE / EventSource endpoints
    where the browser cannot attach Authorization. For every other endpoint
    use `get_current_user` (header-only).
    """
    token: str | None = None
    if credentials is not None:
        token = credentials.credentials
    if not token:
        token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing auth token")
    return _decode_token(token)
