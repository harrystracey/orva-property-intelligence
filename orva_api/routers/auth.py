"""Auth router — login and password management."""

import bcrypt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ..auth import authenticate_user, get_current_user, verify_password, USERS, _save_users

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    name: str
    username: str


class MeResponse(BaseModel):
    username: str
    name: str


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    token = authenticate_user(req.username, req.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    from ..auth import USERS
    return LoginResponse(
        token=token,
        name=USERS[req.username]["name"],
        username=req.username,
    )


@router.get("/me", response_model=MeResponse)
def me(user: dict = Depends(get_current_user)):
    return MeResponse(**user)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    username = user["username"]
    if username not in USERS:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(req.current_password, USERS[username]["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    new_hash = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt()).decode()
    USERS[username]["password_hash"] = new_hash
    _save_users(USERS)
    return {"status": "ok"}
