import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import actions

from ..auth import current_user, get_project_for, log
from ..config import settings
from ..db import get_db
from ..llm import LLM
from ..models import Chunk, Document, Record, User
from ..pipeline import process_document

router = APIRouter(prefix="/api/projects/{project_id}/documents", tags=["documents"])

MAGIC = {".pdf": b"%PDF", ".docx": b"PK"}


def doc_out(db: Session, d: Document) -> dict:
    return {"id": d.id, "filename": d.filename, "file_type": d.file_type, "size_bytes": d.size_bytes, "pages": d.pages,
            "status": d.status, "error": d.error, "extracted_by": d.extracted_by, "uploaded_at": d.uploaded_at,
            "records": db.query(Record).filter_by(document_id=d.id).count(),
            "chunks": db.query(Chunk).filter_by(document_id=d.id).count()}


@router.get("")
def list_documents(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user)
    return [doc_out(db, d) for d in db.query(Document).filter_by(project_id=project_id).order_by(Document.id.desc())]


@router.post("")
async def upload(project_id: int, files: list[UploadFile] = File(...), use_ai: bool = Query(True),
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    project, _ = get_project_for(db, project_id, user, ("manager", "member"))
    llm = LLM.from_db(db)
    results = []
    for f in files:
        name = Path(f.filename or "file").name
        ext = Path(name).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            results.append({"filename": name, "error": f"Unsupported type {ext}. Use PDF, DOCX, TXT or MD."})
            continue
        data = await f.read()
        if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
            results.append({"filename": name, "error": f"File larger than {settings.MAX_UPLOAD_MB} MB"})
            continue
        if not data:
            results.append({"filename": name, "error": "File is empty"})
            continue
        if ext in MAGIC and not data.startswith(MAGIC[ext]):
            results.append({"filename": name, "error": "File content does not match its extension"})
            continue
        folder = settings.UPLOAD_DIR / str(project.id)
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.\-]+", "_", name)
        path = folder / f"{uuid.uuid4().hex[:8]}_{safe}"
        path.write_bytes(data)
        d = Document(project_id=project.id, filename=name, stored_path=str(path), file_type=ext[1:], size_bytes=len(data), uploaded_by=user.id)
        db.add(d)
        db.flush()
        stats = process_document(db, d, llm, user.id, use_ai=use_ai)
        log(db, project.id, user, f"uploaded {name} → {stats.get('records', 0)} records")
        db.commit()
        results.append({"filename": name, "document": doc_out(db, d), "stats": stats})
    return {"results": results}


@router.post("/{doc_id}/reprocess")
def reprocess(project_id: int, doc_id: int, use_ai: bool = Query(True), db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user, ("manager", "member"))
    d = db.get(Document, doc_id)
    if not d or d.project_id != project_id:
        raise HTTPException(404, "Document not found")
    stats = process_document(db, d, LLM.from_db(db), user.id, use_ai=use_ai)
    log(db, project_id, user, f"re-processed {d.filename}")
    db.commit()
    return {"document": doc_out(db, d), "stats": stats}


@router.get("/{doc_id}/file")
def download(project_id: int, doc_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user)
    d = db.get(Document, doc_id)
    if not d or d.project_id != project_id or not Path(d.stored_path).exists():
        raise HTTPException(404, "File not found")
    return FileResponse(d.stored_path, filename=d.filename)


@router.get("/{doc_id}/chunks")
def chunks(project_id: int, doc_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user, ("manager", "member"))
    return [{"id": c.id, "page": c.page, "section": c.section, "text": c.text}
            for c in db.query(Chunk).filter_by(document_id=doc_id, project_id=project_id).order_by(Chunk.seq)]


@router.delete("/{doc_id}")
def delete(project_id: int, doc_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user, ("manager", "member"))
    d = db.get(Document, doc_id)
    if not d or d.project_id != project_id:
        raise HTTPException(404, "Document not found")
    Path(d.stored_path).unlink(missing_ok=True)
    db.query(Record).filter_by(document_id=d.id).delete()
    log(db, project_id, user, f"deleted {d.filename}")
    db.delete(d)
    db.commit()
    return {"ok": True}


class NoteIn(BaseModel):
    title: str = Field(default="", max_length=150)
    text: str = Field(min_length=10, max_length=200_000)
    use_ai: bool = True


@router.post("/text")
def capture_text(project_id: int, body: NoteIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Quick capture: paste meeting notes / chat exports or dictate by voice — stored as a source document."""
    project, _ = get_project_for(db, project_id, user, ("manager", "member"))
    d, stats = actions.add_text_document(db, project, user, body.title, body.text, body.use_ai)
    return {"document": doc_out(db, d), "stats": stats}
