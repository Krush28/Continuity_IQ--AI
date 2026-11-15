from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agents.gap_auditor import run_gap_auditor
from ..agents.qa_agent import ask
from ..auth import current_user, get_project_for, log
from ..db import get_db
from ..llm import LLM
from ..models import AgentRun, GapQuestion, Record, User

router = APIRouter(prefix="/api/projects/{project_id}", tags=["agents"])


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class AnswerIn(BaseModel):
    answer: str = ""
    status: str = Field(default="answered", pattern="^(answered|dismissed|open)$")
    save_as_record: bool = True


def q_out(g: GapQuestion) -> dict:
    return {"id": g.id, "record_id": g.record_id, "kind": g.kind, "question": g.question, "severity": g.severity,
            "answer": g.answer, "status": g.status, "answered_by": g.answered_by, "created_at": g.created_at}


@router.post("/agents/gap-audit")
def gap_audit(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user, ("manager", "member"))
    out = run_gap_auditor(db, project_id, LLM.from_db(db), user.id)
    log(db, project_id, user, f"ran Gap Auditor: {out['rule_questions'] + out['agent_questions']} new questions")
    db.commit()
    return out


@router.get("/questions")
def questions(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user)
    sev = {"high": 0, "medium": 1, "low": 2}
    qs = db.query(GapQuestion).filter_by(project_id=project_id).all()
    return [q_out(g) for g in sorted(qs, key=lambda g: (g.status != "open", sev.get(g.severity, 3), g.id))]


@router.post("/questions/{qid}")
def answer_question(project_id: int, qid: int, body: AnswerIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user, ("manager", "member"))
    g = db.get(GapQuestion, qid)
    if not g or g.project_id != project_id:
        raise HTTPException(404, "Question not found")
    g.answer, g.status, g.answered_by = body.answer.strip(), body.status, user.name
    if body.status == "answered" and not g.answer:
        raise HTTPException(422, "Write an answer first")
    # Fill the gap directly where we can.
    r = db.get(Record, g.record_id) if g.record_id else None
    if body.status == "answered" and r:
        if g.kind == "missing_owner" and len(g.answer) <= 60:
            r.owner = g.answer
        elif g.kind == "missing_rationale":
            r.rationale = g.answer
        elif g.kind == "missing_severity":
            low = g.answer.lower()
            r.priority = next((p for p in ("critical", "high", "medium", "low") if p in low), r.priority)
            r.detail = (r.detail + "\n" if r.detail else "") + f"Clarification: {g.answer}"
        else:
            r.detail = (r.detail + "\n" if r.detail else "") + f"Clarification ({user.name}): {g.answer}"
        r.flagged, r.flag_reason = False, ""
    elif body.status == "answered" and body.save_as_record:
        db.add(Record(project_id=project_id, category="contact" if g.kind == "missing_contacts" else
                      "dependency" if g.kind == "missing_dependencies" else "note",
                      title=g.answer[:300], detail=f"Answer to: {g.question}", extracted_by="agent", confidence=1.0,
                      source_location=f"Gap question Q{g.id}, answered by {user.name}", source_excerpt=g.answer))
    log(db, project_id, user, f"{body.status} question Q{g.id}")
    db.commit()
    return q_out(g)


@router.post("/ask")
def ask_question(project_id: int, body: AskIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _, role = get_project_for(db, project_id, user)
    res = ask(db, project_id, body.question, LLM.from_db(db), user.id, approved_only=(role == "incoming"))
    db.commit()
    return res


@router.get("/agents/runs")
def runs(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user)
    return [{"id": r.id, "agent": r.agent, "provider": r.provider, "status": r.status, "input": r.input, "output": r.output,
             "steps": len(r.trace or []), "started_at": r.started_at, "finished_at": r.finished_at}
            for r in db.query(AgentRun).filter_by(project_id=project_id).order_by(AgentRun.id.desc()).limit(50)]


@router.get("/agents/runs/{run_id}")
def run_detail(project_id: int, run_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user)
    r = db.get(AgentRun, run_id)
    if not r or r.project_id != project_id:
        raise HTTPException(404, "Run not found")
    return {"id": r.id, "agent": r.agent, "provider": r.provider, "status": r.status, "input": r.input,
            "output": r.output, "trace": r.trace, "started_at": r.started_at, "finished_at": r.finished_at}
