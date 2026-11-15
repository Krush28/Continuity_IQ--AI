"""Handover Writer Agent: builds the handover from APPROVED records only.

Structured sections (completed / ongoing / pending / decisions / issues / dependencies / contacts /
documents) are assembled deterministically so nothing can be hallucinated. GenAI, when available,
writes the narrative parts — project overview, recommended next steps, first-week plan, risks —
and every claim must cite approved records as [R<id>]. Citations to unknown records are removed.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..llm import LLM, LLMError
from ..models import Document, GapQuestion, Project, Record
from .base import Trace, finish_run, start_run
from .tools import fmt_record

PRIO = {"critical": 0, "p0": 0, "high": 1, "p1": 1, "medium": 2, "p2": 2, "low": 3, "p3": 3, "": 4}


def rec_dict(r: Record) -> dict:
    return {"id": r.id, "title": r.title, "detail": r.detail, "status": r.status, "owner": r.owner, "priority": r.priority,
            "rationale": r.rationale, "source": r.source_location, "excerpt": r.source_excerpt[:300], "category": r.category}


def readiness(db: Session, project_id: int) -> dict:
    recs = db.query(Record).filter(Record.project_id == project_id).all()
    live = [r for r in recs if r.review_state != "rejected"]
    total = len(live) or 1
    reviewed = sum(r.review_state == "approved" for r in live) / total
    open_tasks = [r for r in live if r.category == "task" and r.status in ("ongoing", "pending")]
    owned = (sum(bool(r.owner) for r in open_tasks) / len(open_tasks)) if open_tasks else 1
    decisions = [r for r in live if r.category == "decision"]
    reasoned = (sum(bool(r.rationale) for r in decisions) / len(decisions)) if decisions else 1
    qs = db.query(GapQuestion).filter_by(project_id=project_id).all()
    open_high = sum(g.status == "open" and g.severity == "high" for g in qs)
    open_any = sum(g.status == "open" for g in qs)
    answered = (sum(g.status != "open" for g in qs) / len(qs)) if qs else (0 if not recs else 1)
    has_contacts = any(r.category == "contact" for r in live)
    flagged = sum(r.flagged and r.review_state == "unreviewed" for r in live)
    score = 100 * (0.35 * reviewed + 0.15 * owned + 0.10 * reasoned + 0.30 * answered + 0.10 * has_contacts)
    score -= min(20, open_high * 5)
    if not recs:
        score = 0
    checks = [
        {"label": "Records reviewed by manager", "value": f"{round(reviewed * 100)}%", "ok": reviewed >= 0.9},
        {"label": "Open tasks with an owner", "value": f"{round(owned * 100)}%", "ok": owned >= 0.8},
        {"label": "Decisions with a recorded reason", "value": f"{round(reasoned * 100)}%", "ok": reasoned >= 0.8},
        {"label": "Gap questions answered", "value": f"{len(qs) - open_any}/{len(qs)}", "ok": open_any == 0 and bool(qs)},
        {"label": "Contacts listed", "value": "yes" if has_contacts else "no", "ok": has_contacts},
        {"label": "Flagged records still unreviewed", "value": str(flagged), "ok": flagged == 0},
    ]
    return {"score": max(0, min(100, round(score))), "checks": checks}


def _clean_citations(text: str, valid: set[int]) -> str:
    return re.sub(r"\[R(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in valid else "", text)


def _template_narrative(project: Project, sec: dict) -> dict:
    notes = sec["overview_notes"]
    overview = project.description or ""
    if notes:
        overview = (overview + " " if overview else "") + " ".join(f"{n['title']} [R{n['id']}]" for n in notes[:4])
    overview = overview or f"Handover for {project.name}."
    stats = f" Status: {len(sec['completed'])} completed, {len(sec['ongoing'])} ongoing and {len(sec['pending'])} pending tasks; {len(sec['issues'])} known issues."
    steps = []
    for t in sec["ongoing"][:4]:
        steps.append(f"Continue “{t['title']}”{' with ' + t['owner'] if t['owner'] else ''} [R{t['id']}]")
    for i in [i for i in sec["issues"] if i["status"] == "open"][:3]:
        steps.append(f"Investigate open issue “{i['title']}” [R{i['id']}]")
    for t in sec["pending"][:4]:
        steps.append(f"Start pending task “{t['title']}” [R{t['id']}]")
    week = ["Day 1: Read this handover and the important documents listed below."]
    if sec["dependencies"]:
        week.append("Day 2: Get access to dependencies: " + ", ".join(f"{d['title'][:40]} [R{d['id']}]" for d in sec["dependencies"][:3]) + ".")
    if sec["contacts"]:
        week.append("Day 3: Meet the contacts: " + ", ".join(f"{c['owner'] or c['title'][:30]} [R{c['id']}]" for c in sec["contacts"][:3]) + ".")
    if sec["ongoing"]:
        week.append(f"Day 4: Pick up the ongoing task “{sec['ongoing'][0]['title']}” [R{sec['ongoing'][0]['id']}].")
    week.append("Day 5: Review open issues with the manager and agree priorities.")
    risks = [f"Open {i['priority'] or ''} issue: {i['title']} [R{i['id']}]".replace("  ", " ") for i in sec["issues"] if i["status"] == "open"][:5]
    return {"overview": overview + stats, "next_steps": steps or ["No open work recorded."], "first_week": week, "risks": risks}


def build_handover(db: Session, project: Project, llm: LLM, user_id: int | None, outgoing: str, incoming: str) -> tuple[dict, int, str]:
    run = start_run(db, project.id, "handover_writer", llm.label, user_id, f"{outgoing} -> {incoming}")
    trace = Trace()
    approved = db.query(Record).filter_by(project_id=project.id, review_state="approved").order_by(Record.id).all()
    trace.add("observation", f"Using {len(approved)} manager-approved records.")
    by = lambda cat, status=None: [rec_dict(r) for r in approved if r.category == cat and (status is None or r.status == status)]
    sort_p = lambda xs: sorted(xs, key=lambda x: PRIO.get(x["priority"], 4))
    sec = {
        "completed": by("task", "completed"),
        "ongoing": sort_p(by("task", "ongoing")),
        "pending": sort_p(by("task", "pending")),
        "decisions": by("decision"),
        "issues": sort_p(by("issue")),
        "dependencies": by("dependency"),
        "contacts": by("contact"),
        "overview_notes": by("note"),
    }
    docs = db.query(Document).filter_by(project_id=project.id, status="processed").all()
    counts = {}
    for r in approved:
        if r.document_id:
            counts[r.document_id] = counts.get(r.document_id, 0) + 1
    sec["documents"] = sorted([{"id": d.id, "filename": d.filename, "type": d.file_type, "pages": d.pages, "records": counts.get(d.id, 0)} for d in docs], key=lambda x: -x["records"])
    qa = db.query(GapQuestion).filter_by(project_id=project.id).all()
    sec["answered_questions"] = [{"q": g.question, "a": g.answer, "by": g.answered_by} for g in qa if g.status == "answered"]
    sec["open_questions"] = [{"q": g.question, "severity": g.severity} for g in qa if g.status == "open"]

    narrative = _template_narrative(project, sec)
    engine = "templates"
    if llm.available and approved:
        trace.add("thought", "Writing the narrative sections with GenAI, grounded in approved records.")
        ctx = "\n".join(fmt_record(r, long=True) for r in approved[:120])
        qa_text = "\n".join(f"Q: {x['q']}\nA: {x['a']}" for x in sec["answered_questions"]) or "(none)"
        prompt = (
            f"Project: {project.name}\nDescription: {project.description}\nOutgoing: {outgoing}\nIncoming: {incoming}\n\n"
            f"APPROVED RECORDS:\n{ctx}\n\nANSWERS FROM OUTGOING MEMBER:\n{qa_text}\n\n"
            "Write JSON with keys:\n"
            ' "overview": 3-5 sentence project overview for the incoming member,\n'
            ' "next_steps": 4-8 concrete recommended next steps, ordered by priority,\n'
            ' "first_week": 5 items, a day-by-day plan for the incoming member\'s first week,\n'
            ' "risks": up to 5 risks to watch.\n'
            "Every sentence/item must cite the records it relies on as [R<id>]. Use only the records above."
        )
        try:
            trace.add("action", {"tool": "llm_write", "args": {"records": len(approved)}})
            data = llm.chat_json([{"role": "system", "content": "You write precise, factual project handover documents. Never invent facts."},
                                  {"role": "user", "content": prompt}], max_tokens=2500, temperature=0.2)
            valid = {r.id for r in approved}
            if isinstance(data, dict) and data.get("overview"):
                narrative = {
                    "overview": _clean_citations(str(data.get("overview", "")), valid),
                    "next_steps": [_clean_citations(str(x), valid) for x in (data.get("next_steps") or [])][:10] or narrative["next_steps"],
                    "first_week": [_clean_citations(str(x), valid) for x in (data.get("first_week") or [])][:7] or narrative["first_week"],
                    "risks": [_clean_citations(str(x), valid) for x in (data.get("risks") or [])][:6],
                }
                engine = llm.label
                trace.add("observation", "Narrative written and citations validated.")
        except LLMError as e:
            trace.add("error", f"GenAI writing failed, using templates: {e}")
    content = {"project": {"name": project.name, "description": project.description}, "outgoing": outgoing,
               "incoming": incoming, **narrative, **sec}
    score = readiness(db, project.id)
    content["readiness"] = score
    trace.add("final", {"engine": engine, "readiness": score["score"]})
    finish_run(db, run, trace, {"engine": engine, "readiness": score["score"]})
    return content, score["score"], engine
