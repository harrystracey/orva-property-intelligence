"""Auth router — login endpoint."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth import authenticate_user, get_current_user
from fastapi import Depends

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
