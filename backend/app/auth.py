from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import ActivityLog, Project, ProjectMember, User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def project_role(db: Session, project: Project, user: User) -> str | None:
    if project.owner_id == user.id:
        return "manager"
    m = db.query(ProjectMember).filter_by(project_id=project.id, user_id=user.id).first()
    return m.project_role if m else None


def get_project_for(db: Session, project_id: int, user: User, allowed: tuple[str, ...] = ("manager", "member", "incoming")):
    """Project-level access control: the user must belong to the project with an allowed role."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    role = project_role(db, project, user)
    if role is None:
        raise HTTPException(403, "You are not a member of this project")
    if role not in allowed:
        raise HTTPException(403, f"This action needs one of these roles: {', '.join(allowed)}")
    return project, role


def log(db: Session, project_id: int, user: User | None, action: str) -> None:
    db.add(ActivityLog(project_id=project_id, user_name=user.name if user else "system", action=action[:255]))
