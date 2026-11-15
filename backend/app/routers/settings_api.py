from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..llm import DEFAULTS, LLM, LLMError, load_config
from ..models import AppSetting, User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class AIConfigIn(BaseModel):
    provider: str
    model: str = ""
    api_key: str | None = None  # None = keep the existing key
    base_url: str = ""


def _public(cfg: dict) -> dict:
    llm = LLM(cfg)
    key = cfg.get("api_key") or ""
    return {"provider": cfg["provider"], "model": cfg["model"], "base_url": cfg["base_url"],
            "has_key": bool(key), "key_hint": f"…{key[-4:]}" if len(key) > 8 else "", "available": llm.available,
            "label": llm.label, "providers": {k: v for k, v in DEFAULTS.items() if k != "mock"}}


@router.get("/ai")
def get_ai(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _public(load_config(db))


@router.put("/ai")
def set_ai(body: AIConfigIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role != "manager":
        raise HTTPException(403, "Only managers can change AI settings")
    if settings.DEMO_MODE:
        raise HTTPException(403, "AI settings are locked on this public demo. Run your own copy to change them.")
    if body.provider not in DEFAULTS:
        raise HTTPException(422, "Unknown provider")
    values = {"llm_provider": body.provider, "llm_model": body.model.strip(), "llm_base_url": body.base_url.strip()}
    if body.api_key is not None:
        values["llm_api_key"] = body.api_key.strip()
    for k, v in values.items():
        row = db.get(AppSetting, k)
        if row:
            row.value = v
        else:
            db.add(AppSetting(key=k, value=v))
    db.commit()
    return _public(load_config(db))


@router.post("/ai/test")
def test_ai(db: Session = Depends(get_db), user: User = Depends(current_user)):
    llm = LLM.from_db(db)
    if not llm.available:
        return {"ok": False, "message": "No GenAI provider configured — ContinuityIQ runs in offline rules mode."}
    try:
        reply = llm.chat_json([{"role": "user", "content": 'Reply with JSON {"status": "ok"}'}], max_tokens=50)
        return {"ok": True, "message": f"Connected to {llm.label}. Reply: {reply}"}
    except LLMError as e:
        return {"ok": False, "message": str(e)}
