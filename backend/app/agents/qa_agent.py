"""Ask ContinuityIQ: a research agent the incoming member can question in plain language.

It searches records and source text step by step and answers ONLY from what it found, citing
[R<id>] records. If the answer was never uploaded, it says so and suggests who to ask.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from .. import search
from ..llm import LLM, LLMError
from ..models import Record
from .base import ToolAgent, Trace, finish_run, start_run
from .tools import build_tools

NOT_FOUND = "I couldn't find this in the uploaded project records."


def _who_to_ask(db: Session, project_id: int) -> str:
    c = db.query(Record).filter_by(project_id=project_id, category="contact").filter(Record.review_state != "rejected").first()
    return f" You could ask {c.owner or c.title} [R{c.id}]." if c else " Ask the project manager to add it."


def _fallback_answer(db: Session, project_id: int, question: str, approved_only: bool, trace: Trace) -> dict:
    trace.add("action", {"tool": "search_records", "args": {"query": question}})
    hits = search.search_records(db, project_id, question, None, approved_only, limit=5)
    trace.add("observation", f"{len(hits)} matching records")
    if not hits:
        return {"answer": NOT_FOUND + _who_to_ask(db, project_id), "citations": []}
    top = hits[0][1]
    hits = [h for h in hits if h[1] >= top * 0.35]
    lines = []
    for r, _ in hits:
        meta = ", ".join(x for x in [r.status, f"owner: {r.owner}" if r.owner else "", f"why: {r.rationale}" if r.rationale else ""] if x)
        lines.append(f"- **{r.title}**{' (' + meta + ')' if meta else ''} [R{r.id}]")
    return {"answer": "Here is what the project records say:\n" + "\n".join(lines), "citations": [r.id for r, _ in hits]}


def ask(db: Session, project_id: int, question: str, llm: LLM, user_id: int | None, approved_only: bool) -> dict:
    run = start_run(db, project_id, "ask", llm.label, user_id, question)
    trace = Trace()
    result = None
    if llm.available:
        agent = ToolAgent(
            llm, "ContinuityIQ Assistant",
            "You answer questions from a new team member taking over this project. Search the records (and the raw "
            "source text when needed), then answer clearly and briefly in markdown. Cite every fact as [R<id>]. If the "
            f"information is not in the tools' results, say exactly: \"{NOT_FOUND}\" and suggest a contact from the records.",
            build_tools(db, project_id, approved_only=approved_only), max_steps=6)
        try:
            res = agent.run(f"Question: {question}\n\nWhen done, call final with args {{\"answer\": \"markdown answer with [R<id>] citations\"}}.", trace)
            answer = str(res.get("answer", "")).strip()
            valid = {r.id for r in db.query(Record.id).filter(Record.project_id == project_id).all()}
            cites = sorted({int(x) for x in re.findall(r"\[R(\d+)\]", answer)} & valid)
            answer = re.sub(r"\[R(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in valid else "", answer)
            if answer:
                result = {"answer": answer, "citations": cites}
        except LLMError as e:
            trace.add("error", f"AI unavailable, using offline search: {e}")
    if result is None:
        result = _fallback_answer(db, project_id, question, approved_only, trace)
    recs = db.query(Record).filter(Record.id.in_(result["citations"])).all() if result["citations"] else []
    result["sources"] = [{"id": r.id, "title": r.title, "category": r.category, "status": r.status,
                          "source": r.source_location, "excerpt": r.source_excerpt[:400]} for r in recs]
    result["engine"] = llm.label if llm.available else "offline-search"
    result["run_id"] = run.id
    trace.add("final", {"citations": result["citations"]})
    finish_run(db, run, trace, {"answer": result["answer"][:2000], "citations": result["citations"]})
    return result
