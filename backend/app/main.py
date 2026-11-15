from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import Base, engine
from .routers import agents, auth, documents, handover, projects, records, settings_api, voice_insights

Base.metadata.create_all(bind=engine)
if settings.SEED_DEMO:
    from .demo import seed

    seed()

app = FastAPI(title="ContinuityIQ API", version="1.0.0",
              description="Project knowledge & handover management with agentic GenAI and an offline rules engine.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth, projects, documents, records, agents, handover, settings_api, voice_insights):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}


# Serve the built React app (frontend/dist) so one command runs everything.
if settings.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=settings.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = settings.FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(settings.FRONTEND_DIST / "index.html")
