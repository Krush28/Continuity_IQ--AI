"""Gap Auditor Agent: finds what is missing, contradictory or risky BEFORE the person leaves.

Stage 1 (always, offline): deterministic checks — owners, rationale, severity, contradictions
across documents, duplicates, missing contacts.
Stage 2 (when GenAI is configured): an autonomous tool-using agent investigates the records and
source text and raises extra questions for the outgoing member or flags records for the manager.
"""
from __future__ import annotations

import re
from itertools import combinations

from sqlalchemy.orm import Session

from ..llm import LLM, LLMError
from ..models import GapQuestion, Record
from ..search import containment, similarity
from .base import ToolAgent, Trace, finish_run, start_run
from .tools import build_tools

CRED_RE = re.compile(r"\b(api key|credential|password|token|secret|access|account|license|server|vpn|ssh)\b", re.I)


def _add(db: Session, project_id: int, question: str, severity: str, kind: str, record_id: int | None, created: list) -> None:
    for g in db.query(GapQuestion).filter_by(project_id=project_id).all():
        if (record_id and g.record_id == record_id and g.kind == kind) or similarity(g.question, question) > 0.7:
            return
    g = GapQuestion(project_id=project_id, record_id=record_id, kind=kind, question=question, severity=severity)
    db.add(g)
    db.flush()
    created.append(g.id)


def rule_checks(db: Session, project_id: int, trace: Trace) -> list[int]:
    created: list[int] = []
    recs = db.query(Record).filter(Record.project_id == project_id, Record.review_state != "rejected").all()
    tasks = [r for r in recs if r.category == "task"]

    for r in tasks:
        if r.status in ("ongoing", "pending") and not r.owner:
            _add(db, project_id, f"Who will own the {r.status} task “{r.title}” after the handover?", "medium", "missing_owner", r.id, created)
        if r.status == "ongoing" and len((r.detail or "") + r.title) < 60:
            _add(db, project_id, f"How far along is “{r.title}” and what exactly remains to be done?", "medium", "missing_progress", r.id, created)
    for r in recs:
        if r.category == "decision" and not r.rationale:
            _add(db, project_id, f"Why was this decided: “{r.title}”? What alternatives were rejected?", "medium", "missing_rationale", r.id, created)
        if r.category == "issue" and r.status == "open":
            if not r.priority:
                _add(db, project_id, f"How severe is the open issue “{r.title}”, and is there a workaround?", "low", "missing_severity", r.id, created)
            elif r.priority in ("high", "critical", "p0", "p1"):
                _add(db, project_id, f"High-priority issue “{r.title}”: what has been tried so far and what is the suspected cause?", "high", "critical_issue", r.id, created)
        if r.category == "dependency" and CRED_RE.search(f"{r.title} {r.detail}"):
            _add(db, project_id, f"Where are the access details for “{r.title}” stored, and who can grant access to the new member?", "high", "access", r.id, created)

    # Contradictions: the same task described with different statuses in different places.
    for a, b in combinations(tasks, 2):
        if "completed" in (a.status, b.status) and a.status != b.status and a.document_id != b.document_id \
                and containment(a.title, b.title) >= 0.75:
            for r, other in ((a, b), (b, a)):
                r.flagged = True
                r.flag_reason = f"Conflicts with R{other.id} ({other.status}, {other.source_location})."
            _add(db, project_id,
                 f"“{a.title}” is marked {a.status} in {a.source_location} but {b.status} in {b.source_location}. Which is correct?",
                 "high", "contradiction", a.id, created)
            trace.add("observation", f"Contradiction: R{a.id} ({a.status}) vs R{b.id} ({b.status})")
    # Duplicates within a category (same text twice).
    for a, b in combinations([r for r in recs if r.category != "task"], 2):
        if a.category == b.category and similarity(a.title, b.title) >= 0.85 and not b.flagged:
            b.flagged = True
            b.flag_reason = f"Possible duplicate of R{a.id}."
    if not any(r.category == "contact" for r in recs):
        _add(db, project_id, "Who should the incoming member contact for questions (client, tech lead, infra/DevOps)?", "high", "missing_contacts", None, created)
    if not any(r.category == "dependency" for r in recs):
        _add(db, project_id, "Which external services, libraries, credentials or other teams does this project depend on?", "medium", "missing_dependencies", None, created)
    trace.add("observation", f"Rule checks raised {len(created)} new questions.")
    return created


def run_gap_auditor(db: Session, project_id: int, llm: LLM, user_id: int | None) -> dict:
    run = start_run(db, project_id, "gap_auditor", llm.label, user_id)
    trace = Trace()
    trace.add("thought", "Checking the knowledge base for missing owners, reasons, severities, contradictions and access details.")
    created = rule_checks(db, project_id, trace)
    agent_created: list[int] = []
    summary = ""
    if llm.available:
        trace.add("thought", "GenAI available: handing over to the autonomous auditor for a deeper review.")
        agent = ToolAgent(
            llm, "Gap Auditor",
            "Your job: make sure nothing important is lost when the outgoing member leaves. Investigate the project "
            "records (tasks, decisions, issues, dependencies, contacts) and source text. Look for: unclear next steps, "
            "risky pending work, undocumented setup/deployment steps, missing test or release info, knowledge that only "
            "one person seems to have. Use ask_outgoing_member for each important gap (max 6, specific, answerable) and "
            "flag_record for records the manager must double-check. Do not repeat questions that already exist.",
            build_tools(db, project_id, writable=True, created_questions=agent_created), max_steps=10)
        existing = "\n".join(f"- {g.question}" for g in db.query(GapQuestion).filter_by(project_id=project_id).all())
        try:
            res = agent.run("Audit this project for handover gaps. Existing questions (do not repeat):\n"
                            f"{existing or '(none)'}\n\nWhen done, call final with args {{\"summary\": \"2-3 sentence audit summary\"}}.", trace)
            summary = str(res.get("summary") or res.get("answer") or "")
        except LLMError as e:
            trace.add("error", f"AI audit stopped: {e}. Rule-based results are kept.")
    open_q = db.query(GapQuestion).filter_by(project_id=project_id, status="open").count()
    flagged = db.query(Record).filter_by(project_id=project_id, flagged=True).filter(Record.review_state == "unreviewed").count()
    if not summary:
        summary = f"{open_q} open question(s) for the outgoing member and {flagged} flagged record(s) need review before approval."
    out = {"summary": summary, "rule_questions": len(created), "agent_questions": len(agent_created), "open_questions": open_q, "flagged": flagged}
    trace.add("final", out)
    finish_run(db, run, trace, out)
    return out
