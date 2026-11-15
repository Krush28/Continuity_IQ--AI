"""Insights: knowledge-risk map (who holds what) and the onboarding quiz for the incoming member."""
from __future__ import annotations

import random
import re
from collections import defaultdict

from sqlalchemy.orm import Session

from .models import Document, Record

HIGH = {"high", "critical", "p0", "p1"}


def _name(owner: str) -> str:
    owner = re.sub(r"\s+", " ", owner or "").strip()
    return " ".join(w.capitalize() for w in owner.split()[:2])


def knowledge_risk(db: Session, project_id: int) -> dict:
    """Bus-factor view: how much open knowledge sits with each person, and where nobody owns the work."""
    recs = db.query(Record).filter(Record.project_id == project_id, Record.review_state != "rejected").all()
    people: dict[str, dict] = defaultdict(lambda: {"open_tasks": 0, "high_open": 0, "completed": 0, "other": 0, "contact": False, "items": []})
    unowned = []
    for r in recs:
        n = _name(r.owner)
        if r.category == "task" and r.status in ("ongoing", "pending") and not n:
            unowned.append({"id": r.id, "title": r.title, "status": r.status, "priority": r.priority})
        if not n:
            continue
        p = people[n]
        if r.category == "contact":
            p["contact"] = True
        elif r.category == "task" and r.status in ("ongoing", "pending"):
            p["open_tasks"] += 1
            p["high_open"] += r.priority in HIGH
            p["items"].append({"id": r.id, "title": r.title, "status": r.status})
        elif r.category == "task":
            p["completed"] += 1
        else:
            p["other"] += 1
    total_open = sum(p["open_tasks"] for p in people.values()) + len(unowned)
    out = []
    for n, p in people.items():
        share = p["open_tasks"] / total_open if total_open else 0
        load = p["open_tasks"] * 2 + p["high_open"] * 2 + p["completed"] + p["other"]
        risk = "high" if (share >= 0.4 or p["high_open"] >= 2) else "medium" if (p["open_tasks"] >= 1 or p["completed"] >= 3) else "low"
        out.append({"name": n, **{k: v for k, v in p.items() if k != "items"}, "items": p["items"][:6],
                    "share": round(share * 100), "load": load, "risk": risk})
    out.sort(key=lambda x: -x["load"])
    warnings = []
    for p in out:
        if p["risk"] == "high":
            warnings.append(f"{p['name']} holds {p['share']}% of the open work ({p['open_tasks']} tasks, {p['high_open']} high priority). "
                            "If they leave, this knowledge must be handed over first.")
    if unowned:
        warnings.append(f"{len(unowned)} open task(s) have no owner at all.")
    return {"people": out, "unowned": unowned, "warnings": warnings, "total_open": total_open}


def quiz(db: Session, project_id: int, approved_only: bool, n: int = 8, seed: int | None = None) -> list[dict]:
    """Multiple-choice knowledge check built ONLY from records, so every answer is verifiable."""
    rnd = random.Random(seed)
    q = db.query(Record).filter(Record.project_id == project_id, Record.review_state != "rejected")
    recs = q.filter(Record.review_state == "approved").all() if approved_only else q.all()
    docs = {d.id: d.filename for d in db.query(Document).filter_by(project_id=project_id)}
    names = sorted({_name(r.owner) for r in recs if r.owner})
    out: list[dict] = []

    def add(question, correct, distractors, rec, why):
        opts = list(dict.fromkeys([correct] + [d for d in distractors if d and d != correct]))[:4]
        if len(opts) < 3:
            return
        rnd.shuffle(opts)
        out.append({"question": question, "options": opts, "answer": opts.index(correct), "record_id": rec.id,
                    "explanation": why, "source": rec.source_location})

    from .search import containment
    tasks = [r for r in recs if r.category == "task" and r.status and not r.flagged
             and not any(o.id != r.id and o.category == "task" and o.status != r.status and containment(o.title, r.title) >= 0.75 for o in recs)]
    for r in rnd.sample(tasks, min(3, len(tasks))):
        add(f"What is the current status of “{r.title}”?", r.status, ["completed", "ongoing", "pending"], r,
            f"It is {r.status}" + (f", owned by {r.owner}." if r.owner else "."))
    owned = [r for r in recs if r.category == "task" and r.owner]
    for r in rnd.sample(owned, min(2, len(owned))):
        add(f"Who owns “{r.title}”?", _name(r.owner), rnd.sample([x for x in names if x != _name(r.owner)], min(3, len(names) - 1)), r,
            f"{_name(r.owner)} is recorded as the owner.")
    dec = [r for r in recs if r.category == "decision" and r.rationale]
    for r in rnd.sample(dec, min(2, len(dec))):
        others = [d.rationale for d in dec if d.id != r.id]
        short = re.split(r"\s+(?:because|since|as|so that)\s+", r.title, maxsplit=1)[0]
        add(f"Why did the team decide: “{short[:110]}”?", r.rationale[:160], [o[:160] for o in rnd.sample(others, min(3, len(others)))], r,
            "This is the reason written in the technical notes.")
    issues = [r for r in recs if r.category == "issue" and r.priority in ("high", "medium", "low")]
    for r in rnd.sample(issues, min(1, len(issues))):
        add(f"How severe is this issue: “{r.title[:110]}”?", r.priority, ["high", "medium", "low"], r, f"It is marked {r.priority} priority.")
    with_doc = [r for r in recs if r.document_id in docs and r.category in ("dependency", "decision", "issue")]
    if len(set(docs.values())) >= 3:
        for r in rnd.sample(with_doc, min(2, len(with_doc))):
            add(f"Which document should you open to find: “{r.title[:100]}”?", docs[r.document_id],
                rnd.sample([f for f in set(docs.values()) if f != docs[r.document_id]], min(3, len(docs) - 1)), r,
                f"It comes from {r.source_location}.")
    contacts = [r for r in recs if r.category == "contact" and r.owner]
    for r in rnd.sample(contacts, min(1, len(contacts))):
        topic = re.sub(r"\([^)]*\)", "", r.title)
        topic = re.sub(rf"^(ask|contact)?\s*{re.escape(r.owner)}\s*", "", topic, flags=re.I)
        topic = re.sub(r"[\w.+-]+@[\w.-]+", "", topic).strip(" -–:(),.").lstrip("- ").replace(" - ", ", ") or r.title
        add(f"Who should you contact for: “{topic[:110]}”?", _name(r.owner),
            rnd.sample([x for x in names if x != _name(r.owner)], min(3, max(0, len(names) - 1))), r, f"{r.title}")
    rnd.shuffle(out)
    return out[:n]
