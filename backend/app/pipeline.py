"""Document processing pipeline: validate → extract text → categorise (rules + GenAI) → store with source."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from . import rules
from .agents.base import Trace, finish_run, start_run
from .agents.extractor import ai_extract
from .extraction import extract, location_label
from .llm import LLM
from .models import Chunk, Document, Record


def process_document(db: Session, doc: Document, llm: LLM, user_id: int | None = None, use_ai: bool = True) -> dict:
    # Re-processing replaces earlier auto-extracted records (manual and agent records are kept).
    db.query(Record).filter(Record.document_id == doc.id, Record.extracted_by.in_(["rules", "ai"])).delete(synchronize_session=False)
    db.query(Chunk).filter(Chunk.document_id == doc.id).delete(synchronize_session=False)
    db.flush()

    ai_on = use_ai and llm.available
    run = start_run(db, doc.project_id, "extraction", llm.label if ai_on else "offline-rules", user_id, doc.filename)
    trace = Trace()
    try:
        units, pages = extract(Path(doc.stored_path))
    except Exception as e:  # corrupt or scanned file
        doc.status, doc.error = "failed", f"Could not read file: {e}"
        trace.add("error", doc.error)
        finish_run(db, run, trace, {"error": doc.error}, "failed")
        return {"records": 0, "error": doc.error}

    doc.pages = pages
    if not units:
        doc.status = "failed"
        doc.error = "No text found. Scanned PDFs need OCR (planned); please upload a text-based PDF or DOCX."
        trace.add("error", doc.error)
        finish_run(db, run, trace, {"error": doc.error}, "failed")
        return {"records": 0, "error": doc.error}

    chunks: list[Chunk] = []
    for i, u in enumerate(units):
        c = Chunk(document_id=doc.id, project_id=doc.project_id, seq=i, page=u.page, section=u.section[:255], text=u.text)
        db.add(c)
        chunks.append(c)
    db.flush()
    trace.add("observation", f"Extracted {len(chunks)} text units from {pages or 'n/a'} pages with local parsers.")

    rule_out = {c.id: rules.categorise(c.text, c.section) for c in chunks}
    trace.add("observation", f"Rules engine categorised {sum(1 for v in rule_out.values() if v)} units.")

    ai_out, covered, stats = {}, set(), {}
    if ai_on:
        trace.add("thought", "GenAI is available: running the Extraction Agent with source-grounding verification.")
        ai_out, covered, stats = ai_extract(
            llm, doc.filename, [(c.id, location_label(doc.filename, c.page, c.section), c.text) for c in chunks], trace)
        trace.add("observation", f"AI stats: {stats}")

    created = 0
    for c in chunks:
        loc = location_label(doc.filename, c.page, c.section)
        candidates: list[tuple[dict, str]] = []
        if c.id in covered:
            candidates = [(r, "ai") for r in ai_out.get(c.id, [])]
            rr = rule_out.get(c.id)
            # AI judged the chunk irrelevant, but rules were confident: keep the rule record.
            if not candidates and rr and rr["confidence"] >= 0.75 and rr["category"] != "note":
                candidates = [(rr, "rules")]
        elif rule_out.get(c.id):
            candidates = [(rule_out[c.id], "rules")]
        for rec, by in candidates:
            db.add(Record(
                project_id=doc.project_id, document_id=doc.id, chunk_id=c.id,
                category=rec["category"], title=rec["title"], detail=rec.get("detail", ""), status=rec["status"],
                owner=rec["owner"], priority=rec["priority"], rationale=rec["rationale"], confidence=rec["confidence"],
                source_location=loc[:255], source_excerpt=(rec.get("excerpt") or c.text)[:2000],
                extracted_by=by, flagged=rec["flagged"], flag_reason=rec["flag_reason"],
            ))
            created += 1

    doc.status, doc.error = "processed", ""
    doc.extracted_by = "ai+rules" if ai_on and covered else "rules"
    out = {"records": created, "chunks": len(chunks), "pages": pages, "engine": doc.extracted_by, **stats}
    trace.add("final", out)
    finish_run(db, run, trace, out)
    return out
