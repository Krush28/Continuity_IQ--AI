"""Voice Agent: operate ContinuityIQ hands-free.

The browser turns speech into text (Web Speech API, English or Hindi) and speaks the reply back.
This agent turns the text into real actions — run the Gap Auditor, approve records, generate and
approve the handover, add tasks, answer questions, export the PDF, open pages — using the SAME
permission-checked actions as the buttons.

* With GenAI: an autonomous tool-using agent plans and chains actions
  ("approve the safe records and generate the handover from Arjun to Karan").
* Offline: a deterministic intent parser handles the common commands; anything else is treated as
  a question for the Ask agent.
"""
from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import actions, search
from ..auth import project_role
from ..llm import LLM, LLMError
from ..models import GapQuestion, Handover, Project, ProjectMember, User
from .base import Tool, ToolAgent, Trace, finish_run, start_run
from .gap_auditor import run_gap_auditor
from .qa_agent import ask as qa_ask

TABS = {"overview": "", "dashboard": "", "home": "", "documents": "documents", "document": "documents", "files": "documents",
        "upload": "documents", "review": "review", "records": "review", "gaps": "gaps", "gap": "gaps", "gap auditor": "gaps",
        "questions": "gaps", "ask": "ask", "chat": "ask", "handover": "handover", "report": "handover", "search": "search",
        "team": "team", "activity": "team", "quiz": "quiz", "settings": "@settings", "projects": "@projects"}
CATS = {"task": "task", "todo": "task", "decision": "decision", "issue": "issue", "bug": "issue", "problem": "issue",
        "dependency": "dependency", "contact": "contact", "person": "contact", "note": "note"}

HELP = ("You can say: give me the status, run the gap audit, start the exit interview, approve the safe records, "
        "generate the handover from Arjun to Karan, approve the handover, download the PDF, add a pending task, "
        "go to review, start the quiz, or just ask any question about the project.")


def speakable(text: str) -> str:
    text = re.sub(r"\[R\d+\]", "", text)
    text = re.sub(r"[*_`#>]", "", text)
    text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text.replace("\n", ". ")).replace(". .", ".").strip()


class VoiceOps:
    """Every action the voice agent can take. Each returns a short sentence and may queue UI actions."""

    def __init__(self, db: Session, user: User, project: Project | None, role: str | None):
        self.db, self.user, self.project, self.role = db, user, project, role
        self.ui: list[dict] = []
        self.refresh = False

    # -- helpers
    def _p(self) -> Project:
        if not self.project:
            raise HTTPException(400, "Open a project first — say 'open project' and its name.")
        return self.project

    def _guard(self, fn, *a, **kw) -> str:
        try:
            return fn(*a, **kw)
        except HTTPException as e:
            return f"I can't do that: {e.detail}"

    def _latest_handover(self, approved_only=False) -> Handover | None:
        q = self.db.query(Handover).filter_by(project_id=self._p().id)
        if approved_only or self.role == "incoming":
            q = q.filter_by(status="approved")
        return q.order_by(Handover.id.desc()).first()

    # -- actions
    def navigate(self, tab: str = "overview", query: str = "") -> str:
        dest = TABS.get(str(tab).lower().strip(), None)
        if dest is None:
            return f"There is no page called {tab}."
        if dest == "@settings":
            self.ui.append({"type": "navigate", "to": "/settings"})
        elif dest == "@projects":
            self.ui.append({"type": "navigate", "to": "/"})
        else:
            p = self._p()
            if self.role == "incoming" and dest in ("documents", "review", "gaps", "team"):
                return "That page is only for the project team."
            self.ui.append({"type": "navigate", "to": f"/projects/{p.id}{'/' + dest if dest else ''}" + (f"?q={query}" if query else "")})
        return f"Opening {tab}."

    def list_projects(self) -> str:
        ids = {m.project_id for m in self.db.query(ProjectMember).filter_by(user_id=self.user.id)}
        ps = self.db.query(Project).filter((Project.owner_id == self.user.id) | Project.id.in_(ids)).all()
        return ("Your projects are: " + ", ".join(p.name for p in ps) + ".") if ps else "You have no projects yet."

    def open_project(self, name: str) -> str:
        ids = {m.project_id for m in self.db.query(ProjectMember).filter_by(user_id=self.user.id)}
        ps = self.db.query(Project).filter((Project.owner_id == self.user.id) | Project.id.in_(ids)).all()
        best = max(ps, key=lambda p: (search.containment(name + " x", p.name + " x"), search.similarity(name, p.name)), default=None)
        if not best or (search.similarity(name, best.name) == 0 and name.lower() not in best.name.lower()):
            return f"I couldn't find a project called {name}. {self.list_projects()}"
        self.project, self.role = best, project_role(self.db, best, self.user)
        self.ui.append({"type": "navigate", "to": f"/projects/{best.id}"})
        return f"Opening {best.name}."

    def create_project(self, name: str, description: str = "") -> str:
        if self.user.role != "manager":
            return "Only managers can create projects."
        p = Project(name=name.strip()[:200].title() if name.islower() else name.strip()[:200], description=description, owner_id=self.user.id)
        self.db.add(p)
        self.db.flush()
        self.db.add(ProjectMember(project_id=p.id, user_id=self.user.id, project_role="manager"))
        self.db.commit()
        self.project, self.role = p, "manager"
        self.ui.append({"type": "navigate", "to": f"/projects/{p.id}/documents"})
        return f"Created the project {p.name}. You can now upload or dictate notes."

    def get_status(self) -> str:
        return actions.status_summary(self.db, self._p())

    def run_gap_audit(self) -> str:
        if self.role not in ("manager", "member"):
            return "Only the project team can run the Gap Auditor."
        out = run_gap_auditor(self.db, self._p().id, LLM.from_db(self.db), self.user.id)
        self.db.commit()
        self.refresh = True
        n = out["rule_questions"] + out["agent_questions"]
        return f"Gap audit done. I found {n} new gaps. {out['summary']} Say 'start the exit interview' to answer them by voice."

    def list_open_questions(self) -> str:
        qs = self.db.query(GapQuestion).filter_by(project_id=self._p().id, status="open").limit(10).all()
        return "\n".join(f"Q{q.id} ({q.severity}): {q.question}" for q in qs) or "There are no open questions."

    def answer_gap_question(self, question_id: int, answer: str) -> str:
        if self.role not in ("manager", "member"):
            return "Only the project team can answer gap questions."
        from ..routers.agents import AnswerIn, answer_question  # reuse the exact API logic
        try:
            answer_question(self._p().id, int(question_id), AnswerIn(answer=answer), self.db, self.user)
        except HTTPException as e:
            return f"Could not save: {e.detail}"
        self.refresh = True
        return f"Saved the answer to question {question_id}."

    def start_exit_interview(self) -> str:
        if self.role not in ("manager", "member"):
            return "The exit interview is for the project team."
        n = self.db.query(GapQuestion).filter_by(project_id=self._p().id, status="open").count()
        if not n:
            return "There are no open gap questions. Run the gap audit first."
        self.ui.append({"type": "interview"})
        return f"Starting the exit interview with {n} questions. Answer after each one, or say skip."

    def approve_safe_records(self) -> str:
        if self.role != "manager":
            return "Only the project manager can approve records."
        ids = actions.safe_record_ids(self.db, self._p().id)
        n = actions.approve_records(self.db, self._p().id, self.user, ids) if ids else 0
        self.refresh = True
        return f"Approved {n} high-confidence, unflagged records. Flagged ones still need your eyes."

    def approve_all_records(self) -> str:
        if self.role != "manager":
            return "Only the project manager can approve records."
        from ..models import Record
        ids = [r.id for r in self.db.query(Record).filter_by(project_id=self._p().id, review_state="unreviewed")]
        n = actions.approve_records(self.db, self._p().id, self.user, ids) if ids else 0
        self.refresh = True
        return f"Approved all {n} remaining records."

    def generate_handover(self, outgoing_name: str = "", incoming_name: str = "") -> str:
        if self.role not in ("manager", "member"):
            return "Only the project team can generate a handover."
        def go():
            h = actions.create_handover(self.db, self._p(), self.user, outgoing_name.title(), incoming_name.title())
            self.refresh = True
            self.ui.append({"type": "navigate", "to": f"/projects/{self._p().id}/handover"})
            return f"Handover version {h.version} is ready, {h.readiness} percent readiness, written by {h.generated_by}."
        return self._guard(go)

    def approve_handover(self, note: str = "") -> str:
        if self.role != "manager":
            return "Only the project manager can approve the handover."
        h = self.db.query(Handover).filter_by(project_id=self._p().id, status="draft").order_by(Handover.id.desc()).first()
        if not h:
            return "There is no draft handover to approve. Generate one first."
        actions.approve_handover(self.db, h, self.user, note)
        self.refresh = True
        return f"Approved handover version {h.version}. The incoming member can read it now."

    def export_handover(self, format: str = "pdf") -> str:
        fmt = {"markdown": "md", "md": "md", "html": "html", "web": "html"}.get(str(format).lower(), "pdf")
        h = self._latest_handover()
        if not h:
            return "There is no handover to export yet."
        name = re.sub(r"\W+", "_", self._p().name).strip("_")
        self.ui.append({"type": "download", "path": f"/projects/{self._p().id}/handovers/{h.id}/export/{fmt}",
                        "filename": f"Handover_{name}_v{h.version}.{fmt}"})
        return f"Downloading handover version {h.version} as {fmt.upper()}."

    def add_record(self, category: str, title: str, status: str = "", owner: str = "", priority: str = "") -> str:
        if self.role not in ("manager", "member"):
            return "Only the project team can add records."
        cat = CATS.get(str(category).lower(), "note")
        r = actions.add_record(self.db, self._p().id, self.user, cat, title.strip().rstrip(".").capitalize(), status, owner.title(),
                               priority, source=f"Added by voice ({self.user.name})")
        self.refresh = True
        bits = [x for x in (r.status, f"owned by {r.owner}" if r.owner else "", f"{r.priority} priority" if r.priority else "") if x]
        return f"Added {cat} R{r.id}: {r.title}" + (f", {', '.join(bits)}" if bits else "") + ". It is waiting for manager review."

    def list_tasks(self, status: str = "pending") -> str:
        from ..models import Record
        cat = "issue" if status == "open" else "task"
        q = self.db.query(Record).filter_by(project_id=self._p().id, category=cat, status=status).filter(Record.review_state != "rejected")
        if self.role == "incoming":
            q = q.filter_by(review_state="approved")
        rows = q.limit(8).all()
        if not rows:
            return f"There are no {status} {cat}s."
        items = "; ".join(f"{r.title}" + (f", owned by {r.owner}" if r.owner else "") for r in rows)
        return f"{len(rows)} {status} {cat}s: {items}."

    def search_project(self, query: str) -> str:
        hits = search.search_records(self.db, self._p().id, query, None, self.role == "incoming", limit=4)
        self.ui.append({"type": "navigate", "to": f"/projects/{self._p().id}/search?q={query}"})
        if not hits:
            return f"Nothing found for {query}."
        return f"Top results for {query}: " + "; ".join(r.title for r, _ in hits[:3]) + "."

    def ask_project(self, question: str) -> str:
        res = qa_ask(self.db, self._p().id, question, LLM.from_db(self.db), self.user.id, self.role == "incoming")
        self.db.commit()
        self.ui.append({"type": "answer", "answer": res["answer"], "sources": res["sources"]})
        return res["answer"]


# ------------------------------------------------------------------ offline intent parser
def _owner_split(text: str) -> tuple[str, str]:
    m = re.search(r"\s+(?:owned by|assigned to|owner is|for)\s+([a-z]+(?:\s[a-z]+)?)\s*$", text, re.I)
    return (text[: m.start()], m.group(1)) if m else (text, "")


def rule_route(ops: VoiceOps, text: str) -> str:
    t = text.lower().strip().rstrip(".?!")
    t = re.sub(r"^(hey|ok|okay|please|hi)\s+(continuity\s*iq\s*)?,?\s*", "", t)
    t = re.sub(r"\bplease\b|\bcan you\b|\bcould you\b", "", t).strip()
    g = ops._guard

    if re.search(r"\b(help|what can you do|commands)\b", t):
        return HELP
    if re.search(r"\b(list|show|what are) (my |all )?projects\b", t):
        return ops.list_projects()
    m = re.search(r"\b(?:create|make|start) (?:a )?(?:new )?project (?:called |named )?(.+)", t)
    if m:
        return ops.create_project(m.group(1))
    m = re.search(r"\b(?:open|go to|switch to) (?:the )?project (.+)", t)
    if m:
        return ops.open_project(m.group(1))
    if re.search(r"\b(start|begin|do|run)\b.*\binterview\b|\binterview me\b", t):
        return g(ops.start_exit_interview)
    if re.search(r"\b(run|start|do)\b.*\b(gap|audit)|\bfind (the )?(gaps|missing)|\bwhat('s| is) missing\b", t):
        return g(ops.run_gap_audit)
    if re.search(r"\bapprove\b.*\b(handover|report)\b|\bpublish\b.*\bhandover\b", t):
        m = re.search(r"\bwith (?:a )?note (.+)", t)
        return g(ops.approve_handover, m.group(1) if m else "")
    if re.search(r"\bapprove\b.*\b(high[- ]?confidence|safe|confident|good)\b", t):
        return g(ops.approve_safe_records)
    if re.search(r"\bapprove (all|every|everything)\b", t):
        return g(ops.approve_all_records)
    m = re.search(r"\b(?:generate|create|make|build|write|prepare)\b (?:a |the |new )?hand ?over(?: report)?(?: (?:from|for) ([a-z]+(?: [a-z]+)?) to ([a-z]+(?: [a-z]+)?))?", t)
    if m:
        return g(ops.generate_handover, m.group(1) or "", m.group(2) or "")
    if re.search(r"\b(download|export)\b", t):
        f = re.search(r"\b(pdf|html|markdown|md)\b", t)
        return g(ops.export_handover, f.group(1) if f else "pdf")
    m = re.match(r"(?:add|create|record|log)\s+(?:a |an |new )?((?:(?:pending|ongoing|completed|done|open|resolved|high|medium|low|priority)\s+)*)"
                 r"(task|todo|decision|issue|bug|problem|dependency|contact|person|note)\b[\s:,-]*(.+)", t)
    if m:
        words, cat, rest = m.group(1).split(), m.group(2), m.group(3)
        title, owner = _owner_split(rest)
        status = next((w for w in words if w in ("pending", "ongoing", "completed", "open", "resolved")), "completed" if "done" in words else "")
        prio = next((w for w in words if w in ("high", "medium", "low")), "")
        mp = re.search(r",?\s*(high|medium|low) priority", title)
        if mp:
            prio, title = mp.group(1), title[: mp.start()]
        return g(ops.add_record, cat, title, status, owner, prio)
    m = re.search(r"\b(?:go to|open|show(?: me)?|take me to|switch to)\b (?:the )?([a-z ]+?)(?: page| tab)?$", t)
    if m and m.group(1).strip() in TABS:
        return g(ops.navigate, m.group(1).strip())
    if re.search(r"\b(start|take|begin)\b.*\bquiz\b|\btest me\b", t):
        return g(ops.navigate, "quiz")
    if re.search(r"\b(status|readiness|how ready|progress|summary|summari[sz]e|update me|brief me)\b", t):
        return g(ops.get_status)
    m = re.search(r"\b(pending|ongoing|in progress|completed|done|finished)\b.*\b(tasks?|work)\b|\bwhat('?s| is| are)? (still )?(pending|ongoing|in progress|completed|done)\b", t)
    if m:
        w = next(x for x in m.groups() if x and x not in ("tasks", "task", "work", "still", "s", "'s", " is", " are"))
        return g(ops.list_tasks, {"in progress": "ongoing", "done": "completed", "finished": "completed"}.get(w, w))
    if re.search(r"\b(open|known|current) (issues|bugs)\b|\bwhat bugs\b", t):
        return g(ops.list_tasks, "open")
    if re.search(r"\bopen questions\b|\bwhat questions\b", t):
        return g(ops.list_open_questions)
    m = re.match(r"(?:search|look up|find)(?: for)? (.+)", t)
    if m:
        return g(ops.search_project, m.group(1))
    if ops.project is None:
        return "Open a project first, for example say: open project ShopEase. " + ops.list_projects()
    return g(ops.ask_project, text)


# ------------------------------------------------------------------ GenAI planner
def _tools(ops: VoiceOps) -> list[Tool]:
    T = lambda name, desc, args, fn: Tool(name, desc, args, lambda **kw: ops._guard(fn, **kw))
    tools = [
        T("list_projects", "List the user's projects.", {}, ops.list_projects),
        T("open_project", "Open a project by (approximate) name.", {"name": "str"}, ops.open_project),
        T("create_project", "Create a new project (managers).", {"name": "str", "description": "optional str"}, ops.create_project),
        T("navigate", "Open a page: overview, documents, review, gaps, ask, handover, search, team, quiz, settings, projects.", {"tab": "str"}, ops.navigate),
    ]
    if ops.project:
        tools += [
            T("get_status", "Spoken status summary: readiness, tasks, issues, open questions.", {}, ops.get_status),
            T("run_gap_audit", "Run the Gap Auditor agent.", {}, ops.run_gap_audit),
            T("list_open_questions", "List open gap questions with their ids.", {}, ops.list_open_questions),
            T("answer_gap_question", "Save an answer to a gap question.", {"question_id": "int", "answer": "str"}, ops.answer_gap_question),
            T("start_exit_interview", "Start the voice exit interview (reads open gap questions aloud).", {}, ops.start_exit_interview),
            T("approve_safe_records", "Manager: approve high-confidence, unflagged records.", {}, ops.approve_safe_records),
            T("approve_all_records", "Manager: approve ALL remaining records. Only if explicitly asked.", {}, ops.approve_all_records),
            T("generate_handover", "Generate a handover report.", {"outgoing_name": "optional str", "incoming_name": "optional str"}, ops.generate_handover),
            T("approve_handover", "Manager: approve the latest draft handover.", {"note": "optional str"}, ops.approve_handover),
            T("export_handover", "Download the latest handover.", {"format": "pdf|html|md"}, ops.export_handover),
            T("add_record", "Add a record.", {"category": "task|decision|issue|dependency|contact|note", "title": "str",
                                              "status": "optional: pending|ongoing|completed|open|resolved", "owner": "optional str", "priority": "optional high|medium|low"}, ops.add_record),
            T("list_tasks", "List tasks by status (pending|ongoing|completed) or open issues (open).", {"status": "str"}, ops.list_tasks),
            T("search_project", "Keyword search, also opens the search page.", {"query": "str"}, ops.search_project),
            T("ask_project", "Answer a question about the project from its records (with citations).", {"question": "str"}, ops.ask_project),
        ]
    return tools


def handle(db: Session, user: User, text: str, project_id: int | None, lang: str = "en-IN") -> dict:
    project = db.get(Project, project_id) if project_id else None
    role = project_role(db, project, user) if project else None
    if project and role is None:
        project = None
    ops = VoiceOps(db, user, project, role)
    llm = LLM.from_db(db)
    run = start_run(db, project.id if project else 0, "voice", llm.label, user.id, text) if project else None
    trace = Trace()
    speech, engine = "", "offline-intents"
    if llm.available:
        language = "Hindi (Devanagari script)" if lang.startswith("hi") else "English"
        agent = ToolAgent(llm, "Voice Operator",
                          f"You operate the ContinuityIQ app for {user.name} (global role {user.role}"
                          f"{f', project role {role} in project {project.name!r}' if project else ', no project open'}) by voice. "
                          "Carry out the spoken request with the tools — chain several tools when asked. Never approve anything the user "
                          "did not ask to approve. For questions about the project, use ask_project. "
                          f"Then call final with args {{\"speech\": \"1-3 short spoken sentences in {language}, no markdown, no [R#]\"}}.",
                          _tools(ops), max_steps=6)
        try:
            res = agent.run(f"Spoken request: {text}", trace)
            speech, engine = str(res.get("speech") or res.get("answer") or ""), llm.label
        except LLMError as e:
            trace.add("error", f"GenAI unavailable, using offline intents: {e}")
    if not speech:
        trace.add("thought", "Routing with the offline intent parser.")
        speech = rule_route(ops, text)
        trace.add("final", {"speech": speech})
    if run:
        finish_run(db, run, trace, {"speech": speech[:1500], "ui": ops.ui})
    else:
        db.commit()
    answer = next((a for a in ops.ui if a["type"] == "answer"), None)
    return {"speech": speakable(speech), "display": speech, "actions": [a for a in ops.ui if a["type"] != "answer"],
            "answer": answer, "refresh": ops.refresh, "engine": engine, "run_id": run.id if run else None,
            "project_id": ops.project.id if ops.project else None}
