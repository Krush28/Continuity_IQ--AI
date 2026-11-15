"""End-to-end test of the full handover flow, offline (rules) and with the mock GenAI provider.

Run:  cd backend && python -m pytest -q tests
"""
import os
import uuid
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/test.db"
os.environ["UPLOAD_DIR"] = f"{TMP}/uploads"
os.environ["LLM_PROVIDER"] = "none"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent.parent / "sample_docs"
c = TestClient(app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def register(name, email, role):
    r = c.post("/api/auth/register", json={"name": name, "email": email, "password": "secret123", "role": role})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def setup_project():
    mgr = register("Priya Nair", f"priya{uuid.uuid4().hex[:6]}@x.in", "manager")
    p = c.post("/api/projects", json={"name": "ShopEase", "description": "Order management"}, headers=auth(mgr)).json()
    files = [("files", (f.name, f.read_bytes())) for f in sorted(SAMPLES.iterdir())]
    r = c.post(f"/api/projects/{p['id']}/documents", files=files, headers=auth(mgr))
    assert r.status_code == 200, r.text
    for res in r.json()["results"]:
        assert "error" not in res, res
        assert res["stats"]["records"] > 0, res
    return mgr, p["id"]


def test_full_offline_flow():
    mgr, pid = setup_project()
    h = auth(mgr)
    recs = c.get(f"/api/projects/{pid}/records", headers=h).json()
    assert len(recs) > 25
    assert all(r["source_location"] for r in recs)

    # Gap auditor finds the deliberate contradiction (payment gateway done vs pending)
    out = c.post(f"/api/projects/{pid}/agents/gap-audit", headers=h).json()
    assert out["rule_questions"] > 0
    qs = c.get(f"/api/projects/{pid}/questions", headers=h).json()
    assert any(q["kind"] == "contradiction" and "Payment gateway" in q["question"] for q in qs), [q["question"] for q in qs]

    # Answer a question and check it fills the gap
    owner_q = next(q for q in qs if q["kind"] == "missing_owner")
    c.post(f"/api/projects/{pid}/questions/{owner_q['id']}", json={"answer": "Karan Shah"}, headers=h)
    assert any(r["owner"] == "Karan Shah" for r in c.get(f"/api/projects/{pid}/records", headers=h).json())

    # Search with source
    s = c.get(f"/api/projects/{pid}/search", params={"q": "razorpay keys"}, headers=h).json()
    assert s["records"] and s["source"]

    # Handover cannot be generated before approval
    assert c.post(f"/api/projects/{pid}/handovers", json={}, headers=h).status_code == 400
    ids = [r["id"] for r in c.get(f"/api/projects/{pid}/records", headers=h).json()]
    assert c.post(f"/api/projects/{pid}/records/review", json={"ids": ids, "state": "approved"}, headers=h).json()["updated"] == len(ids)

    ho = c.post(f"/api/projects/{pid}/handovers", json={"outgoing_name": "Arjun Mehta", "incoming_name": "Karan Shah"}, headers=h).json()
    assert ho["content"]["pending"] and ho["content"]["completed"] and ho["content"]["next_steps"]
    assert c.post(f"/api/projects/{pid}/handovers/{ho['id']}/approve", json={"manager_note": "ok"}, headers=h).json()["status"] == "approved"
    for fmt in ("html", "md", "pdf"):
        r = c.get(f"/api/projects/{pid}/handovers/{ho['id']}/export/{fmt}", headers=h)
        assert r.status_code == 200 and len(r.content) > 500, fmt

    # Incoming member: read-only, sees approved data only, can ask
    inc = register("Karan Shah", "karan@x.in", "incoming")
    c.post(f"/api/projects/{pid}/members", json={"email": "karan@x.in", "project_role": "incoming"}, headers=h)
    hi = auth(inc)
    assert c.post(f"/api/projects/{pid}/records", json={"category": "note", "title": "hack"}, headers=hi).status_code == 403
    assert len(c.get(f"/api/projects/{pid}/handovers", headers=hi).json()) == 1
    a = c.post(f"/api/projects/{pid}/ask", json={"question": "Where are the Razorpay API keys?"}, headers=hi).json()
    assert a["citations"] and "Bitwarden" in str(a["sources"])

    # Outsider has no access
    out = register("Eve", "eve@x.in", "member")
    assert c.get(f"/api/projects/{pid}/records", headers=auth(out)).status_code == 403


def test_mock_genai_agents():
    mgr, _ = setup_project()
    h = auth(mgr)
    c.put("/api/settings/ai", json={"provider": "mock", "model": "", "base_url": ""}, headers=h)
    try:
        assert c.post("/api/settings/ai/test", headers=h).json()["ok"]
        p = c.post("/api/projects", json={"name": "AI project"}, headers=h).json()
        f = SAMPLES / "03_Task_Status.docx"
        r = c.post(f"/api/projects/{p['id']}/documents", files=[("files", (f.name, f.read_bytes()))], headers=h).json()
        assert r["results"][0]["stats"]["engine"] == "ai+rules"
        recs = c.get(f"/api/projects/{p['id']}/records", headers=h).json()
        assert any(x["extracted_by"] == "ai" for x in recs)
        a = c.post(f"/api/projects/{p['id']}/ask", json={"question": "inventory sync status"}, headers=h).json()
        assert a["engine"].startswith("mock")
        run = c.get(f"/api/projects/{p['id']}/agents/runs/{a['run_id']}", headers=h).json()
        kinds = [s["kind"] for s in run["trace"]]
        assert "action" in kinds and "observation" in kinds and "final" in kinds
        g = c.post(f"/api/projects/{p['id']}/agents/gap-audit", headers=h).json()
        assert "summary" in g
    finally:
        c.put("/api/settings/ai", json={"provider": "none", "model": "", "base_url": ""}, headers=h)


def test_voice_agent_and_insights():
    mgr, pid = setup_project()
    h = auth(mgr)
    v = lambda text, project=pid: c.post("/api/voice/command", json={"text": text, "project_id": project}, headers=h).json()
    assert "ready for handover" in v("give me the status")["speech"]
    r = v("run the gap audit")
    assert "Gap audit done" in r["speech"] and r["refresh"]
    assert v("start the exit interview")["actions"][0]["type"] == "interview"
    assert "Approved" in v("approve the high confidence records")["speech"]
    r = v("add a pending high priority task set up CI pipeline owned by karan shah")
    assert "Set up ci pipeline" in r["speech"] and "Karan Shah" in r["speech"] and "high" in r["speech"]
    v("approve all records")
    r = v("generate the handover from arjun mehta to karan shah")
    assert "Handover version" in r["speech"] and r["actions"][0]["to"].endswith("/handover")
    assert "Approved handover" in v("approve the handover")["speech"]
    r = v("download the handover as pdf")
    assert r["actions"][0]["type"] == "download" and r["actions"][0]["path"].endswith("/pdf")
    assert v("go to review")["actions"][0]["to"].endswith("/review")
    r = v("where are the razorpay api keys?")
    assert r["answer"] and "Bitwarden" in str(r["answer"])
    r = v("open project shopease", None)
    assert r["actions"][0]["to"].startswith("/projects/")
    # insights
    ppl = c.get(f"/api/projects/{pid}/people", headers=h).json()
    assert ppl["people"] and ppl["people"][0]["name"]
    qz = c.get(f"/api/projects/{pid}/quiz?seed=1", headers=h).json()["questions"]
    assert len(qz) >= 5 and all(0 <= q["answer"] < len(q["options"]) for q in qz)
    # quick capture
    r = c.post(f"/api/projects/{pid}/documents/text", json={"title": "Standup 14 Nov", "text": "## Pending\n- Write API docs for the warehouse sync, owner: Karan Shah\n## Decisions\n- We chose Locust over JMeter because the team knows Python."}, headers=h)
    assert r.status_code == 200 and r.json()["stats"]["records"] >= 2
