# ContinuityIQ — Agentic project handover system

> When someone leaves, their knowledge stays.

ContinuityIQ turns scattered project files (requirements, technical notes, task lists, bug lists, DB change logs, pending-work notes) into a **source-linked, manager-approved handover** for the person taking over. It's powered by **four AI agents** and falls back to an **offline rules engine**, so it always works, even with no internet.

## What makes it different

| | |
|---|---|
| **Extraction Agent** (GenAI) | Reads every PDF/DOCX/TXT/MD and turns it into tasks, decisions, issues, dependencies, contacts and context. Each AI record must quote the source text, and a **grounding verifier** checks that quote. Anything it can't verify gets flagged, and invented owners are removed. |
| **Gap Auditor** (agentic) | Finds what would be lost if the person left today: **contradictions between documents** (e.g. "Payment gateway" marked *done* in one file and *pending* in another), tasks with no owner, decisions with no reason, undocumented credentials and critical bugs. With GenAI on, an autonomous agent then uses tools to investigate the records and raise its own questions. |
| **Handover Writer** (GenAI) | Builds the report from **manager-approved records only**. AI writes the overview, next steps, a **first-week plan** and risks. Every line cites `[R#]` records, and citations that point to non-existent records are removed. |
| **Ask ContinuityIQ** (agentic RAG) | The new member asks questions in plain language. The agent searches step by step, cites its sources, and says *"not in the records"* rather than guessing. |
| **Full agent trace** | Every thought, tool call and observation (including voice commands) is logged and shown in the UI, so the AI's reasoning can be inspected. |
| **Handover readiness score** | A live 0–100% score: records reviewed, owners assigned, reasons recorded, gaps answered. |
| **Human in the loop** | Members upload and answer questions, the manager approves records and the final handover, and the incoming member gets read-only access. |

## 🎙 Voice Agent — run everything by voice

Click the mic button (bottom-right) or press **Alt+V**, in **English or हिन्दी**. The Voice Agent does real work through the same permission-checked actions as the buttons:

| Say… | It does |
|---|---|
| "Give me the status" / "brief me" | Speaks the readiness, task counts, open issues and questions |
| "Run the gap audit" | Runs the Gap Auditor agent |
| "Start the exit interview" | **Voice exit interview**: reads each gap question aloud to the person leaving, listens to the answer and saves it ("skip", "repeat", "not relevant", "stop") |
| "Approve the safe records" / "approve all records" | Manager approval |
| "Generate the handover from Arjun Mehta to Karan Shah" | Runs the Handover Writer and opens the report |
| "Approve the handover" · "Download the PDF" | Approves the latest draft · downloads the export |
| "Add a pending high priority task write API docs owned by Karan Shah" | Creates a record, sent to the manager for review |
| "What's pending?" · "What bugs are open?" | Speaks the list |
| "Open project ShopEase" · "Create project Mobile App" | Opens or creates a project |
| Any question ("Where are the payment API keys?") | Answers with sources via the Ask agent |

Turn on **Hands-free conversation** and the mic reopens after every reply. With GenAI on, the Voice Agent plans and **chains several actions from one sentence** ("approve the safe records and generate the handover"). Offline, a built-in intent parser handles the commands above. Speech uses the browser's Web Speech API (Chrome/Edge): no key and no cost.

## More features

- **Knowledge risk map**: shows who holds the open work and how much, flags single points of failure ("bus factor"), and lists tasks nobody owns.
- **Onboarding quiz**: a multiple-choice quiz for the incoming member, built only from approved records (status, owners, reasons behind decisions, which document to open, who to contact). Every answer links to its source, and the score goes to the manager's activity log.
- **Quick capture**: paste meeting notes or WhatsApp/Slack exports, or **dictate** them. The note becomes a source document and is extracted like any upload.

## Architecture

```
React (Vite) ──REST──► FastAPI ──► SQLAlchemy ──► SQLite (default) / MySQL
                          │
                          ├── extraction.py   PyMuPDF + python-docx (page & section kept)
                          ├── rules.py        offline categoriser (always on)
                          ├── llm.py          Ollama · Groq · Gemini · OpenAI · Anthropic · none
                          ├── agents/         ReAct tool-using agent runtime + 5 agents (incl. voice)
                          ├── actions.py      shared actions used by buttons AND voice
                          ├── insights.py     knowledge-risk map + onboarding quiz
                          ├── search.py       BM25 keyword search (no vector DB)
                          └── report.py       HTML / Markdown / PDF export
uploads/  original files, linked from every record
```

The agent loop uses plain JSON (`{"thought","action","args"}`) rather than vendor-specific tool calling, so it works with small **local models via Ollama** as well as hosted APIs.

## Run it (one command after setup)

Requirements: Python 3.11+ and Node 18+.

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # set JWT_SECRET

# 2. Frontend (build once)
cd ../frontend
npm install && npm run build

# 3. Demo data (users + ShopEase project + 6 sample docs)
cd ..
python scripts/make_sample_docs.py
python scripts/seed_demo.py

# 4. Start
cd backend
uvicorn app.main:app --port 8000
```

Open **http://localhost:8000**. API docs are at **/docs**.

Demo logins (password `demo123`):
- `manager@demo.in`: Priya Nair, the project manager
- `arjun@demo.in`: Arjun Mehta, the outgoing developer
- `karan@demo.in`: Karan Shah, the incoming member (read-only, approved data only)

Frontend dev mode with hot reload: run `npm run dev` in `frontend/` (it proxies `/api` to :8000) and open http://localhost:5173.

## Turning on GenAI

Use the **AI settings** page (as a manager), or set the values in `backend/.env`:

| Provider | Setup |
|---|---|
| **Ollama, fully offline** | Install from ollama.com, then `ollama pull qwen2.5:7b`. Set `LLM_PROVIDER=ollama` |
| **Groq** (fast, free tier) | `LLM_PROVIDER=groq`, `LLM_API_KEY=...` |
| **Gemini** | `LLM_PROVIDER=gemini`, `LLM_API_KEY=...` |
| OpenAI / Anthropic | `LLM_PROVIDER=openai` or `anthropic`, plus a key |

Click **Save and test connection**. If the AI call fails at any point, the agents fall back to the rules engine and log it in the trace.

## MySQL

```sql
CREATE DATABASE continuityiq CHARACTER SET utf8mb4;
```
Set `DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/continuityiq` in `backend/.env`. The tables are created automatically on start.

## Demo script (5 minutes)

1. Sign in as the manager and open **ShopEase**. The overview shows the readiness ring and the 5-step flow.
2. **Documents**: 6 scattered files have been turned into 43 records, each with its source.
3. **Gap Auditor**: click *Run*. It catches the payment-gateway **contradiction**, tasks with no owner and VPN/credential access gaps. Answer one question, then *Copy questions* to send to the outgoing member.
4. **Review**: click any 📄 source to see the exact paragraph highlighted. Use *Approve high-confidence*, then fix or approve the rest.
5. **Handover**: generate, then approve. Export as PDF, HTML or Markdown.
6. **Voice finale:** open the mic and say *"run the gap audit"* → *"start the exit interview"* (answer two questions out loud) → *"approve the safe records"* → *"generate the handover from Arjun Mehta to Karan Shah"* → *"approve the handover"* → *"download the PDF"*.
7. Sign in as `karan@demo.in`. Take the **Onboarding quiz**, then **Ask** "Where are the payment API keys?" and get a cited answer. Click *How did the agent find this?* to see the trace.

## Tests

```bash
cd backend && python -m pytest -q tests
```
These cover the voice agent commands, the quiz, the risk map, quick capture, and the full upload → audit → review → handover → approve → incoming-member flow, access control, all three exports, and the GenAI agent loop (using a mock model).

## Security

- Passwords are hashed with bcrypt, and logins use JWT. Secrets live in `.env`, never in code.
- Access is checked per project and per role (manager / member / incoming). Incoming members only see approved data.
- Uploads are checked for type and size, magic bytes are verified, filenames are sanitised, and the original files stay on local disk.
- The AI can only reach one project's data through scoped tools. AI output is verified against the source before anyone trusts it.

## Project structure

```
backend/app/        FastAPI app (routers/, agents/, pipeline, rules, llm, search, report)
backend/tests/      end-to-end tests
frontend/src/       React app (pages/, pages/tabs/, components/)
sample_docs/        demo handover files (slide 10 scenario)
scripts/            sample-doc generator and demo seeder
```
