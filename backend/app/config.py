"""Central configuration. Values come from environment variables or backend/.env.

Secrets (JWT secret, DB password, LLM API key) never live in source code.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


class Settings:
    APP_NAME = "ContinuityIQ"
    DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'continuityiq.db'}"
    JWT_SECRET = os.getenv("JWT_SECRET") or "dev-only-secret-change-me-in-backend-env-file"
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR") or str(BASE_DIR / "uploads"))
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

    # GenAI provider: none | ollama | openai | groq | gemini | anthropic | mock
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()
    LLM_MODEL = os.getenv("LLM_MODEL", "")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
    LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90"))

    # Hosted demo: SEED_DEMO loads the demo project at start; DEMO_MODE locks the shared AI settings.
    SEED_DEMO = os.getenv("SEED_DEMO", "false").lower() == "true"
    DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

    FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
