"""Shared project actions used by both the REST API and the Voice Agent, so a spoken command does
exactly what the button does — with the same permission checks."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .agents.report_writer import build_handover, readiness
from .auth import log
from .config import settings
from .llm import LLM
from .models import Document, GapQuestion, Handover, Project, Record, User
from .pipeline import process_document

VALID_STATUS = {"task": ("completed", "ongoing", "pending"), "issue": ("open", "resolved")}


def need(role: str, *allowed: str) -> None:
    if role not in allowed:
        raise HTTPException(403, f"Only {' or '.join(allowed)} can do that.")


def safe_record_ids(db: Session, project_id: int) -> list[int]:
    return [r.id for r in db.query(Record).filter_by(project_id=project_id, review_state="unreviewed", flagged=False)
            if r.confidence >= 0.7]


def approve_records(db: Session, project_id: int, user: User, ids: list[int]) -> int:
    recs = db.query(Record).filter(Record.project_id == project_id, Record.id.in_(ids)).all()
    for r in recs:
        r.review_state, r.flagged = "approved", False
    log(db, project_id, user, f"approved {len(recs)} record(s)")
    db.commit()
    return len(recs)


def create_handover(db: Session, project: Project, user: User, outgoing: str = "", incoming: str = "") -> Handover:
    if not db.query(Record).filter_by(project_id=project.id, review_state="approved").count():
        raise HTTPException(400, "Approve at least one record in Review before generating a handover.")
    content, score, engine = build_handover(db, project, LLM.from_db(db), user.id, outgoing, incoming)
    version = db.query(Handover).filter_by(project_id=project.id).count() + 1
    h = Handover(project_id=project.id, version=version, outgoing_name=outgoing, incoming_name=incoming,
                 content=content, readiness=score, generated_by=engine, created_by=user.id)
    db.add(h)
    log(db, project.id, user, f"generated handover v{version} ({engine})")
    db.commit()
    return h


def approve_handover(db: Session, h: Handover, user: User, note: str = "") -> Handover:
    h.status, h.approved_by, h.approved_at, h.manager_note = "approved", user.id, datetime.now(timezone.utc), note
    log(db, h.project_id, user, f"approved handover v{h.version}")
    db.commit()
    return h


def add_record(db: Session, project_id: int, user: User, category: str, title: str, status: str = "", owner: str = "",
               priority: str = "", detail: str = "", rationale: str = "", source: str = "") -> Record:
    status = (status or "").lower()
    allowed = VALID_STATUS.get(category)
    status = (status if status in allowed else allowed[-1 if category == "task" else 0]) if allowed else ""
    r = Record(project_id=project_id, category=category, title=title[:500], status=status, owner=owner[:120],
               priority=(priority or "")[:20], detail=detail, rationale=rationale, extracted_by="manual", confidence=1.0,
               source_location=source or f"Added manually by {user.name}")
    db.add(r)
    log(db, project_id, user, f"added {category} “{title[:60]}”")
    db.commit()
    return r


def add_text_document(db: Session, project: Project, user: User, title: str, text: str, use_ai: bool = True):
    """Quick capture: meeting notes, chat exports or voice dictation become a source document."""
    title = (title or "").strip() or f"Note {datetime.now():%d %b %H:%M}"
    safe = re.sub(r"[^\w.\-]+", "_", title)[:60] or "note"
    folder = settings.UPLOAD_DIR / str(project.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex[:8]}_{safe}.md"
    body = text.strip()
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    d = Document(project_id=project.id, filename=f"{title}.md", stored_path=str(path), file_type="md",
                 size_bytes=path.stat().st_size, uploaded_by=user.id)
    db.add(d)
    db.flush()
    stats = process_document(db, d, LLM.from_db(db), user.id, use_ai=use_ai)
    log(db, project.id, user, f"captured note “{title}” → {stats.get('records', 0)} records")
    db.commit()
    return d, stats


def status_summary(db: Session, project: Project) -> str:
    rd = readiness(db, project.id)
    recs = db.query(Record).filter(Record.project_id == project.id, Record.review_state != "rejected").all()
    tasks = [r for r in recs if r.category == "task"]
    cnt = lambda s: sum(t.status == s for t in tasks)
    unrev = sum(r.review_state == "unreviewed" for r in recs)
    open_q = db.query(GapQuestion).filter_by(project_id=project.id, status="open").count()
    issues = sum(r.category == "issue" and r.status == "open" for r in recs)
    h = db.query(Handover).filter_by(project_id=project.id).order_by(Handover.id.desc()).first()
    hs = f"Latest handover is version {h.version}, {h.status}." if h else "No handover generated yet."
    return (f"{project.name} is {rd['score']} percent ready for handover. "
            f"There are {cnt('completed')} completed, {cnt('ongoing')} ongoing and {cnt('pending')} pending tasks, "
            f"{issues} open issues, {unrev} records waiting for review and {open_q} open gap questions. {hs}")
