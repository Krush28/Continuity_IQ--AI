"""Tools the agents can call. Each is scoped to one project so an agent can never read other projects."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import search
from ..models import Chunk, Document, GapQuestion, Record
from .base import Tool


def fmt_record(r: Record, long: bool = False) -> str:
    bits = [f"R{r.id}", r.category]
    if r.status:
        bits.append(r.status)
    head = f"[{' | '.join(bits)}] {r.title}"
    extra = []
    if r.owner:
        extra.append(f"owner={r.owner}")
    if r.priority:
        extra.append(f"priority={r.priority}")
    if r.rationale:
        extra.append(f"why={r.rationale[:200]}")
    if r.review_state != "unreviewed":
        extra.append(f"review={r.review_state}")
    if r.flagged:
        extra.append("FLAGGED")
    extra.append(f"source={r.source_location}")
    out = head + " (" + ", ".join(extra) + ")"
    if long and r.detail:
        out += f"\n   detail: {r.detail[:400]}"
    return out


def build_tools(db: Session, project_id: int, approved_only: bool = False, writable: bool = False,
                created_questions: list | None = None) -> list[Tool]:
    def _q():
        q = db.query(Record).filter(Record.project_id == project_id, Record.review_state != "rejected")
        return q.filter(Record.review_state == "approved") if approved_only else q

    def search_records(query: str, category: str = "") -> str:
        hits = search.search_records(db, project_id, query, category or None, approved_only, limit=8)
        if not hits:
            return "No matching records."
        return "\n".join(fmt_record(r, long=True) for r, _ in hits)

    def search_source(query: str) -> str:
        hits = search.search_chunks(db, project_id, query, limit=5)
        if not hits:
            return "No matching source text."
        return "\n".join(f"[S{c.id}] {d.filename} p.{c.page or '-'} § {c.section or '-'}: {c.text[:500]}" for c, d, _ in hits)

    def list_records(category: str = "", status: str = "") -> str:
        q = _q()
        if category:
            q = q.filter(Record.category == category)
        if status:
            q = q.filter(Record.status == status)
        rows = q.order_by(Record.id).limit(60).all()
        return "\n".join(fmt_record(r) for r in rows) or "No records."

    def get_record(record_id: int) -> str:
        r = db.get(Record, int(record_id))
        if not r or r.project_id != project_id:
            return "Record not found."
        return fmt_record(r, long=True) + f"\n   source excerpt: {r.source_excerpt[:600]}"

    def read_source(chunk_id: int) -> str:
        c = db.get(Chunk, int(chunk_id))
        if not c or c.project_id != project_id:
            return "Source not found."
        d = db.get(Document, c.document_id)
        return f"{d.filename} p.{c.page or '-'} § {c.section or '-'}:\n{c.text}"

    def list_documents() -> str:
        docs = db.query(Document).filter_by(project_id=project_id).all()
        return "\n".join(f"D{d.id} {d.filename} ({d.file_type}, {d.status})" for d in docs) or "No documents."

    tools = [
        Tool("search_records", "Keyword search over structured project records.", {"query": "str", "category": "optional: task|decision|issue|dependency|contact|note"}, search_records),
        Tool("search_source", "Keyword search over the raw text of uploaded documents.", {"query": "str"}, search_source),
        Tool("list_records", "List records by category and/or status.", {"category": "optional", "status": "optional: completed|ongoing|pending|open|resolved"}, list_records),
        Tool("get_record", "Get one record with its source excerpt.", {"record_id": "int"}, get_record),
        Tool("list_documents", "List uploaded documents.", {}, list_documents),
    ]
    if not approved_only:
        tools.append(Tool("read_source", "Read the full source paragraph of a chunk id S<id>.", {"chunk_id": "int"}, read_source))

    if writable:
        bucket = created_questions if created_questions is not None else []

        def ask_outgoing_member(question: str, severity: str = "medium", record_id: int | None = None) -> str:
            for existing in db.query(GapQuestion).filter_by(project_id=project_id).all():
                if search.similarity(existing.question, question) > 0.6:
                    return f"Similar question already exists (Q{existing.id}); not added."
            rid = None
            if record_id:
                r = db.get(Record, int(record_id))
                rid = r.id if r and r.project_id == project_id else None
            g = GapQuestion(project_id=project_id, record_id=rid, kind="agent", question=question[:1000],
                            severity=severity if severity in ("high", "medium", "low") else "medium")
            db.add(g)
            db.flush()
            bucket.append(g.id)
            return f"Question Q{g.id} recorded."

        def flag_record(record_id: int, reason: str) -> str:
            r = db.get(Record, int(record_id))
            if not r or r.project_id != project_id:
                return "Record not found."
            r.flagged = True
            r.flag_reason = (reason or "Flagged by Gap Auditor")[:500]
            return f"R{r.id} flagged."

        tools += [
            Tool("ask_outgoing_member", "Record a question the outgoing member must answer before handover.",
                 {"question": "str", "severity": "high|medium|low", "record_id": "optional int"}, ask_outgoing_member),
            Tool("flag_record", "Flag a record for the manager to check.", {"record_id": "int", "reason": "str"}, flag_record),
        ]
    return tools
