"""Rule-based categoriser: the offline engine that always works, with or without GenAI.

Each source unit becomes a structured record (task / decision / issue / dependency / contact / note).
Items the rules cannot classify confidently are flagged for human review instead of guessed.
"""
from __future__ import annotations

import re

from .extraction import BULLET_RE

SECTION_HINTS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\b(completed|done|finished|accomplished|delivered)\b", re.I), "task", "completed"),
    (re.compile(r"\b(ongoing|in[- ]progress|current work|wip|work in progress|active)\b", re.I), "task", "ongoing"),
    (re.compile(r"\b(pending|to-?do|backlog|next steps?|remaining|open tasks|upcoming|pending work|not started)\b", re.I), "task", "pending"),
    (re.compile(r"\b(tasks?|task status|work items?|status|progress|sprint)\b", re.I), "task", ""),
    (re.compile(r"\b(decisions?|architecture|design choices?|technical notes?|tech stack|approach|database changes?|schema changes?|migrations?)\b", re.I), "decision", ""),
    (re.compile(r"\b(bugs?|issues?|known issues|problems?|defects?|errors?|risks?|blockers?)\b", re.I), "issue", "open"),
    (re.compile(r"\b(dependenc(y|ies)|integrations?|third[- ]party|external services?|prerequisites?|credentials|environment)\b", re.I), "dependency", ""),
    (re.compile(r"\b(contacts?|people|stakeholders?|who to ask|team|points? of contact|owners?)\b", re.I), "contact", ""),
    (re.compile(r"\b(deployment|infrastructure|hosting|setup|environments?)\b", re.I), "note", ""),
    (re.compile(r"\b(overview|introduction|summary|scope|requirements?|objectives?|goals?|background|purpose|about)\b", re.I), "note", ""),
]

STATUS_COMPLETED = re.compile(r"(\[[xX✓]\]|✓|✔|\b(done|completed?|finished|implemented|deployed|merged|shipped|closed|fixed|resolved)\b)", re.I)
STATUS_ONGOING = re.compile(r"\b(in[- ]progress|ongoing|wip|working on|partially|half[- ]?way|under development|being (built|developed|tested)|\d{1,2}\s?%)\b", re.I)
STATUS_PENDING = re.compile(r"(\[ \]|\b(pending|to-?do|not started|yet to|remaining|planned|need(s)? to|to be done|waiting|backlog|blocked)\b)", re.I)

KW_DECISION = re.compile(r"\b(decided|decision|we chose|chose|chosen|agreed|opted|went with|switched to|will use|use[sd]? .* (instead of|over)|because|rationale|trade-?off)\b", re.I)
KW_ISSUE = re.compile(r"\b(bug|crash(es)?|fails?|failing|failure|error|exception|broken|issue|defect|leak|timeout|slow|incorrect|not working|regression)\b", re.I)
KW_DEPENDENCY = re.compile(r"\b(depends on|dependent on|dependency|blocked by|requires?|waiting (on|for)|api key|third[- ]party|external|vendor|library|package|service account|credentials?)\b", re.I)
KW_CONTACT = re.compile(r"([\w.+-]+@[\w-]+\.[\w.]+|\b(contact|reach out to|ask|point of contact|poc)\b)", re.I)
KW_TASK = re.compile(r"\b(implement|build|create|add|fix|write|test|deploy|design|integrate|update|refactor|migrate|set ?up|configure|document|review|finish|complete)\b", re.I)

KV_RE = re.compile(r"(?:^|\|)\s*([A-Za-z][A-Za-z /]{1,24}?)\s*:\s*([^|]+)")
OWNER_RE = re.compile(r"\b(?:owner|assigned to|assignee|responsible|handled by|led by|poc)\s*[:\-]?\s*([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)")
AT_RE = re.compile(r"@([A-Z][a-zA-Z]+)")
PRIORITY_RE = re.compile(r"\b(high|medium|low|critical|p[0-3])\b(?:\s*priority)?", re.I)
RATIONALE_RE = re.compile(r"\b(?:because|since|as|so that|due to|rationale[: ]|reason[: ])\s+(.+)", re.I)


def _strip_bullet(text: str) -> str:
    return BULLET_RE.sub("", text, count=1).strip()


def _kv(text: str) -> dict[str, str]:
    if ":" not in text or "|" not in text:
        return {}
    return {k.strip().lower(): v.strip() for k, v in KV_RE.findall(text)}


def _status_from(text: str) -> str:
    # Order matters: "in progress" beats "done" mentions; explicit "pending" beats generic words.
    if STATUS_ONGOING.search(text):
        return "ongoing"
    if STATUS_PENDING.search(text):
        return "pending"
    if STATUS_COMPLETED.search(text):
        return "completed"
    return ""


def _normalise_status(value: str) -> str:
    v = value.lower()
    if STATUS_ONGOING.search(v):
        return "ongoing"
    if STATUS_PENDING.search(v) or v in {"open", "new"}:
        return "pending"
    if STATUS_COMPLETED.search(v):
        return "completed"
    return ""


def _title(text: str, kv: dict[str, str]) -> str:
    for key in ("task", "title", "item", "bug", "issue", "decision", "name", "description", "work item", "feature"):
        if kv.get(key):
            return kv[key][:300]
    m = re.match(r"^([A-Za-z][^:]{6,70}):\s+\S", text)
    if m and len(m.group(1).split()) >= 2:
        return m.group(1).strip()
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    first = re.sub(r"\s*[-–—]\s*(done|completed|in progress|pending|ongoing)\.?$", "", first, flags=re.I)
    return first[:300]


def categorise(text: str, section: str) -> dict | None:
    raw = text.strip()
    body = _strip_bullet(raw)
    if len(body) < 4:
        return None
    kv = _kv(body)

    sec_cat, sec_status = "", ""
    for pattern, cat, status in SECTION_HINTS:
        if section and pattern.search(section):
            sec_cat, sec_status = cat, status
            break

    # line-level signals
    line_cat = ""
    if kv and any(k in kv for k in ("status", "task", "assignee", "owner", "progress")) and not any(k in kv for k in ("bug", "severity")):
        line_cat = "task"
    elif kv and any(k in kv for k in ("bug", "severity", "issue")):
        line_cat = "issue"
    elif KW_DECISION.search(body):
        line_cat = "decision"
    elif KW_ISSUE.search(body) and not STATUS_COMPLETED.search(body[:20]):
        line_cat = "issue"
    elif KW_DEPENDENCY.search(body):
        line_cat = "dependency"
    elif KW_CONTACT.search(body) and re.search(r"[A-Z][a-z]+", body):
        line_cat = "contact" if "@" in body or re.search(r"\b(contact|ask|poc)\b", body, re.I) else ""
    elif _status_from(body) or KW_TASK.search(body.split(" ")[0] if body else ""):
        line_cat = "task"

    category = sec_cat or line_cat or "note"
    confidence = 0.3
    flag_reason = ""
    if sec_cat and line_cat and sec_cat != line_cat:
        # Strong line signals in a generic section win, otherwise trust the section.
        starts_with_action = bool(re.match(r"(need(s)? to|must|should|fix|finish|write|set ?up|get|add|create|implement|build|complete|start|update|migrate|test)\b", body, re.I))
        if sec_cat == "task" and starts_with_action:
            category = "task"
        elif sec_cat in ("note", "task") and line_cat in ("decision", "issue", "dependency"):
            category = line_cat
        confidence = 0.55
    elif sec_cat and line_cat:
        confidence = 0.9
    elif sec_cat:
        confidence = 0.75
    elif line_cat:
        confidence = 0.6
    else:
        flag_reason = "Could not be categorised by rules — please confirm the category."

    status = ""
    if category == "task":
        status = _normalise_status(kv.get("status", "")) or _status_from(body) or sec_status
        if not status:
            status = "pending"
            confidence = min(confidence, 0.5)
            flag_reason = flag_reason or "Task status is unclear — confirm whether it is completed, ongoing or pending."
        elif sec_status and _status_from(body) and _status_from(body) != sec_status and not kv.get("status"):
            flag_reason = f"Listed under '{section}' but the text suggests '{_status_from(body)}' — please confirm."
            confidence = 0.45
    elif category == "issue":
        status = "resolved" if STATUS_COMPLETED.search(kv.get("status", "") or body) and not STATUS_PENDING.search(body) else "open"

    owner = kv.get("owner") or kv.get("assignee") or kv.get("assigned to") or kv.get("responsible") or ""
    if not owner:
        m = OWNER_RE.search(body) or AT_RE.search(body)
        owner = m.group(1) if m else ""
    if category == "contact" and not owner:
        m = re.match(r"(?:(?:ask|contact|reach out to|email|call|talk to|speak to)\s+)?([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", body, re.I)
        owner = m.group(1) if m else ""

    priority = (kv.get("priority") or kv.get("severity") or "").lower()
    if not priority:
        m = PRIORITY_RE.search(body)
        priority = m.group(1).lower() if m else ""

    rationale = ""
    if category == "decision":
        rationale = kv.get("reason") or kv.get("rationale") or kv.get("why") or ""
        if not rationale:
            m = RATIONALE_RE.search(body)
            rationale = m.group(1).strip() if m else ""

    return {
        "category": category,
        "title": _title(body, kv),
        "detail": "" if kv else (body if len(body) > len(_title(body, kv)) + 3 else ""),
        "status": status,
        "owner": owner[:120],
        "priority": priority[:20],
        "rationale": rationale[:1000],
        "confidence": round(confidence, 2),
        "flagged": bool(flag_reason),
        "flag_reason": flag_reason,
    }
