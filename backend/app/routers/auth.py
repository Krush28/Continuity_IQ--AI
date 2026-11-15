from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import create_token, current_user, hash_password, verify_password
from ..db import get_db
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=190)
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="member", pattern="^(manager|member|incoming)$")


class LoginIn(BaseModel):
    email: str
    password: str


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email")
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "An account with this email already exists")
    u = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    db.commit()
    return {"token": create_token(u), "user": user_out(u)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return {"token": create_token(u), "user": user_out(u)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)
