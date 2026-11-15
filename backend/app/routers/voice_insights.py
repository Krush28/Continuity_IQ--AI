from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agents.voice_agent import handle
from ..auth import current_user, get_project_for, log
from ..db import get_db
from ..insights import knowledge_risk, quiz
from ..models import User

router = APIRouter(tags=["voice & insights"])


class VoiceIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    project_id: int | None = None
    lang: str = "en-IN"


class QuizResult(BaseModel):
    score: int
    total: int


@router.post("/api/voice/command")
def voice_command(body: VoiceIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Voice Agent: a spoken (transcribed) command → real actions + a reply to speak."""
    return handle(db, user, body.text.strip(), body.project_id, body.lang)


@router.get("/api/projects/{project_id}/people")
def people(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user)
    return knowledge_risk(db, project_id)


@router.get("/api/projects/{project_id}/quiz")
def get_quiz(project_id: int, seed: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _, role = get_project_for(db, project_id, user)
    return {"questions": quiz(db, project_id, approved_only=(role == "incoming"), seed=seed)}


@router.post("/api/projects/{project_id}/quiz/result")
def quiz_result(project_id: int, body: QuizResult, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user)
    log(db, project_id, user, f"completed the onboarding quiz: {body.score}/{body.total}")
    db.commit()
    return {"ok": True}
