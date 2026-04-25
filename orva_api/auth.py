"""
JWT authentication for ORVA API.
Replaces streamlit-authenticator YAML credentials.
"""

import json
import logging
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS, USERS_FILE
from .tenant_context import DEFAULT_TENANT_ID

logger = logging.getLogger("orva_api.auth")

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
            logger.warning("%s is empty or malformed; using fallback users", USERS_FILE)
        except Exception as e:
            logger.warning("failed to read %s (%s); using fallback users", USERS_FILE, e)
    return _FALLBACK_USERS


USERS = _load_users()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode(), hashed_password.encode()
    )


def create_token(username: str) -> str:
    """
    Mint a JWT for `username`. Includes a `tenant` claim drawn from the
    user record (USERS[username]["tenant"]) or DEFAULT_TENANT_ID if the
    user record predates multi-tenant. Existing single-tenant deployments
    therefore continue minting tokens with tenant='orva' automatically.
    """
    user = USERS[username]
    payload = {
        "sub": username,
        "name": user["name"],
        "tenant": user.get("tenant") or DEFAULT_TENANT_ID,
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
    """Decode a JWT and resolve the user. Raises HTTPException(401) on failure.

    The returned dict surfaces `username`, `name`, and `tenant`. Older
    tokens that lack the `tenant` claim are tolerated -- callers using
    `tenant_context.current_tenant_id()` will fall back to the default.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if username not in USERS:
            raise HTTPException(status_code=401, detail="Invalid user")
        return {
            "username": username,
            "name": payload.get("name"),
            "tenant": payload.get("tenant") or DEFAULT_TENANT_ID,
        }
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
