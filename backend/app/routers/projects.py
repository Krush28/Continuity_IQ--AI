from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..agents.report_writer import readiness
from ..auth import current_user, get_project_for, log, project_role
from ..db import get_db
from ..models import ActivityLog, AgentRun, Document, GapQuestion, Handover, Project, ProjectMember, Record, User

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = ""


class MemberIn(BaseModel):
    email: str
    project_role: str = Field(default="member", pattern="^(manager|member|incoming)$")


def project_out(db: Session, p: Project, user: User) -> dict:
    counts = dict(db.query(Record.category, func.count()).filter(Record.project_id == p.id, Record.review_state != "rejected").group_by(Record.category).all())
    return {"id": p.id, "name": p.name, "description": p.description, "created_at": p.created_at,
            "my_role": project_role(db, p, user),
            "documents": db.query(Document).filter_by(project_id=p.id).count(),
            "records": sum(counts.values()), "counts": counts,
            "open_questions": db.query(GapQuestion).filter_by(project_id=p.id, status="open").count(),
            "readiness": readiness(db, p.id)["score"]}


@router.get("")
def list_projects(db: Session = Depends(get_db), user: User = Depends(current_user)):
    ids = {m.project_id for m in db.query(ProjectMember).filter_by(user_id=user.id)}
    projects = db.query(Project).filter((Project.owner_id == user.id) | (Project.id.in_(ids))).order_by(Project.created_at.desc()).all()
    return [project_out(db, p, user) for p in projects]


@router.post("")
def create_project(body: ProjectIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role != "manager":
        raise HTTPException(403, "Only managers can create projects")
    p = Project(name=body.name.strip(), description=body.description.strip(), owner_id=user.id)
    db.add(p)
    db.flush()
    db.add(ProjectMember(project_id=p.id, user_id=user.id, project_role="manager"))
    log(db, p.id, user, f"created project “{p.name}”")
    db.commit()
    return project_out(db, p, user)


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p, role = get_project_for(db, project_id, user)
    out = project_out(db, p, user)
    tasks = dict(db.query(Record.status, func.count()).filter(Record.project_id == p.id, Record.category == "task", Record.review_state != "rejected").group_by(Record.status).all())
    review = dict(db.query(Record.review_state, func.count()).filter(Record.project_id == p.id).group_by(Record.review_state).all())
    out.update({
        "tasks": tasks, "review": review,
        "flagged": db.query(Record).filter_by(project_id=p.id, flagged=True, review_state="unreviewed").count(),
        "readiness_detail": readiness(db, p.id),
        "members": [{"id": m.user.id, "name": m.user.name, "email": m.user.email, "project_role": m.project_role} for m in p.members],
        "handovers": db.query(Handover).filter_by(project_id=p.id).count(),
        "approved_handover": db.query(Handover).filter_by(project_id=p.id, status="approved").count() > 0,
        "activity": [{"user": a.user_name, "action": a.action, "at": a.created_at} for a in
                     db.query(ActivityLog).filter_by(project_id=p.id).order_by(ActivityLog.id.desc()).limit(15)],
        "agent_runs": db.query(AgentRun).filter_by(project_id=p.id).count(),
    })
    return out


@router.patch("/{project_id}")
def update_project(project_id: int, body: ProjectIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p, _ = get_project_for(db, project_id, user, ("manager",))
    p.name, p.description = body.name, body.description
    db.commit()
    return project_out(db, p, user)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p, _ = get_project_for(db, project_id, user, ("manager",))
    if p.owner_id != user.id:
        raise HTTPException(403, "Only the project owner can delete it")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/{project_id}/members")
def add_member(project_id: int, body: MemberIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p, _ = get_project_for(db, project_id, user, ("manager",))
    u = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not u:
        raise HTTPException(404, "No user with that email — ask them to register first")
    m = db.query(ProjectMember).filter_by(project_id=p.id, user_id=u.id).first()
    if m:
        m.project_role = body.project_role
    else:
        db.add(ProjectMember(project_id=p.id, user_id=u.id, project_role=body.project_role))
    log(db, p.id, user, f"added {u.name} as {body.project_role}")
    db.commit()
    return {"ok": True}


@router.delete("/{project_id}/members/{user_id}")
def remove_member(project_id: int, user_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p, _ = get_project_for(db, project_id, user, ("manager",))
    if user_id == p.owner_id:
        raise HTTPException(400, "The owner cannot be removed")
    db.query(ProjectMember).filter_by(project_id=p.id, user_id=user_id).delete()
    db.commit()
    return {"ok": True}
