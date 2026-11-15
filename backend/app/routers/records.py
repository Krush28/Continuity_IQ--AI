from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import search
from ..auth import current_user, get_project_for, log
from ..db import get_db
from ..models import Chunk, Document, Record, User

router = APIRouter(prefix="/api/projects/{project_id}", tags=["records"])

CATS = "^(task|decision|issue|dependency|contact|note)$"


class RecordIn(BaseModel):
    category: str = Field(pattern=CATS)
    title: str = Field(min_length=2, max_length=500)
    detail: str = ""
    status: str = ""
    owner: str = ""
    priority: str = ""
    rationale: str = ""


class RecordPatch(BaseModel):
    category: str | None = Field(default=None, pattern=CATS)
    title: str | None = None
    detail: str | None = None
    status: str | None = None
    owner: str | None = None
    priority: str | None = None
    rationale: str | None = None


class ReviewIn(BaseModel):
    ids: list[int]
    state: str = Field(pattern="^(approved|rejected|unreviewed)$")


def rec_out(r: Record) -> dict:
    return {k: getattr(r, k) for k in ("id", "document_id", "chunk_id", "category", "title", "detail", "status", "owner", "priority",
                                       "rationale", "confidence", "source_location", "source_excerpt", "extracted_by",
                                       "review_state", "flagged", "flag_reason", "updated_at")}


def _valid_status(category: str, status: str) -> str:
    status = (status or "").lower()
    if category == "task":
        return status if status in ("completed", "ongoing", "pending") else "pending"
    if category == "issue":
        return status if status in ("open", "resolved") else "open"
    return ""


@router.get("/records")
def list_records(project_id: int, category: str = "", status: str = "", review_state: str = "", flagged: bool | None = None,
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    _, role = get_project_for(db, project_id, user)
    q = db.query(Record).filter_by(project_id=project_id)
    if role == "incoming":
        q = q.filter_by(review_state="approved")
    if category:
        q = q.filter_by(category=category)
    if status:
        q = q.filter_by(status=status)
    if review_state:
        q = q.filter_by(review_state=review_state)
    if flagged is not None:
        q = q.filter_by(flagged=flagged)
    return [rec_out(r) for r in q.order_by(Record.category, Record.id)]


@router.post("/records")
def create_record(project_id: int, body: RecordIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user, ("manager", "member"))
    r = Record(project_id=project_id, **body.model_dump(), extracted_by="manual", confidence=1.0,
               source_location=f"Added manually by {user.name}", source_excerpt="")
    r.status = _valid_status(r.category, r.status)
    db.add(r)
    log(db, project_id, user, f"added {r.category} “{r.title[:60]}”")
    db.commit()
    return rec_out(r)


@router.patch("/records/{record_id}")
def update_record(project_id: int, record_id: int, body: RecordPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user, ("manager", "member"))
    r = db.get(Record, record_id)
    if not r or r.project_id != project_id:
        raise HTTPException(404, "Record not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    r.status = _valid_status(r.category, r.status)
    r.flagged, r.flag_reason = False, ""
    r.confidence = 1.0
    if r.review_state == "approved":
        r.review_state = "unreviewed"  # edits need a fresh approval
    db.commit()
    return rec_out(r)


@router.post("/records/review")
def review(project_id: int, body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user, ("manager",))
    recs = db.query(Record).filter(Record.project_id == project_id, Record.id.in_(body.ids)).all()
    for r in recs:
        r.review_state = body.state
        if body.state == "approved":
            r.flagged = False
    log(db, project_id, user, f"{body.state} {len(recs)} record(s)")
    db.commit()
    return {"updated": len(recs)}


@router.delete("/records/{record_id}")
def delete_record(project_id: int, record_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user, ("manager", "member"))
    r = db.get(Record, record_id)
    if not r or r.project_id != project_id:
        raise HTTPException(404, "Record not found")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/records/{record_id}/source")
def record_source(project_id: int, record_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user)
    r = db.get(Record, record_id)
    if not r or r.project_id != project_id:
        raise HTTPException(404, "Record not found")
    c = db.get(Chunk, r.chunk_id) if r.chunk_id else None
    d = db.get(Document, r.document_id) if r.document_id else None
    ctx = []
    if c:
        ctx = [{"id": x.id, "text": x.text, "section": x.section, "page": x.page, "current": x.id == c.id}
               for x in db.query(Chunk).filter(Chunk.document_id == c.document_id, Chunk.seq.between(c.seq - 2, c.seq + 2)).order_by(Chunk.seq)]
    return {"record": rec_out(r), "document": {"id": d.id, "filename": d.filename} if d else None, "context": ctx}


@router.get("/search")
def keyword_search(project_id: int, q: str, category: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    _, role = get_project_for(db, project_id, user)
    recs = search.search_records(db, project_id, q, category or None, approved_only=(role == "incoming"), limit=25)
    out = {"records": [{**rec_out(r), "score": round(s, 2)} for r, s in recs], "source": []}
    if role != "incoming":
        out["source"] = [{"chunk_id": c.id, "document_id": d.id, "filename": d.filename, "page": c.page, "section": c.section,
                          "snippet": search.highlight(c.text, q), "score": round(s, 2)} for c, d, s in search.search_chunks(db, project_id, q, 10)]
    return out
