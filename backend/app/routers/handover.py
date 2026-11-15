import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import actions, report
from ..auth import current_user, get_project_for
from ..db import get_db
from ..models import Handover, User

router = APIRouter(prefix="/api/projects/{project_id}/handovers", tags=["handover"])


class GenerateIn(BaseModel):
    outgoing_name: str = ""
    incoming_name: str = ""


class ApproveIn(BaseModel):
    manager_note: str = ""


def h_out(h: Handover, full: bool = True) -> dict:
    out = {"id": h.id, "version": h.version, "status": h.status, "outgoing_name": h.outgoing_name, "incoming_name": h.incoming_name,
           "readiness": h.readiness, "generated_by": h.generated_by, "created_at": h.created_at, "approved_at": h.approved_at,
           "manager_note": h.manager_note}
    if full:
        out["content"] = h.content
    return out


def _get(db, project_id, hid, role) -> Handover:
    h = db.get(Handover, hid)
    if not h or h.project_id != project_id or (role == "incoming" and h.status != "approved"):
        raise HTTPException(404, "Handover not found")
    return h


@router.get("")
def list_handovers(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _, role = get_project_for(db, project_id, user)
    q = db.query(Handover).filter_by(project_id=project_id)
    if role == "incoming":
        q = q.filter_by(status="approved")
    return [h_out(h, False) for h in q.order_by(Handover.id.desc())]


@router.post("")
def generate(project_id: int, body: GenerateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    project, _ = get_project_for(db, project_id, user, ("manager", "member"))
    return h_out(actions.create_handover(db, project, user, body.outgoing_name, body.incoming_name))


@router.get("/{hid}")
def get_handover(project_id: int, hid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _, role = get_project_for(db, project_id, user)
    return h_out(_get(db, project_id, hid, role))


@router.post("/{hid}/approve")
def approve(project_id: int, hid: int, body: ApproveIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project_for(db, project_id, user, ("manager",))
    return h_out(actions.approve_handover(db, _get(db, project_id, hid, "manager"), user, body.manager_note))


@router.get("/{hid}/export/{fmt}")
def export(project_id: int, hid: int, fmt: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    project, role = get_project_for(db, project_id, user)
    h = _get(db, project_id, hid, role)
    meta = {"status": h.status, "version": h.version, "manager_note": h.manager_note}
    base = re.sub(r"\W+", "_", project.name).strip("_") or "project"
    fname = f"Handover_{base}_v{h.version}"
    if fmt == "html":
        return HTMLResponse(report.to_html(h.content, meta), headers={"Content-Disposition": f'attachment; filename="{fname}.html"'})
    if fmt == "md":
        return PlainTextResponse(report.to_markdown(h.content, meta), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="{fname}.md"'})
    if fmt == "pdf":
        return Response(report.to_pdf(h.content, meta), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})
    raise HTTPException(400, "Format must be html, md or pdf")
