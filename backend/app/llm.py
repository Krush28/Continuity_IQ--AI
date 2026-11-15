"""GenAI provider layer.

One small client that talks to:
  * Ollama (local, fully offline)            provider=ollama
  * Any OpenAI-compatible API (OpenAI, Groq, Gemini's OpenAI endpoint)
  * Anthropic's Messages API                 provider=anthropic
  * none  -> every AI feature falls back to the offline rules/templates engine
  * mock  -> deterministic fake model used by the automated tests

Settings can come from backend/.env or be changed at runtime from the Settings page.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting

DEFAULTS = {
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:7b"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.5-flash"},
    "anthropic": {"base_url": "https://api.anthropic.com", "model": "claude-haiku-5-5"},
    "mock": {"base_url": "", "model": "mock-1"},
    "none": {"base_url": "", "model": ""},
}


class LLMError(RuntimeError):
    pass


def load_config(db: Session | None) -> dict[str, str]:
    cfg = {
        "provider": settings.LLM_PROVIDER,
        "model": settings.LLM_MODEL,
        "api_key": settings.LLM_API_KEY,
        "base_url": settings.LLM_BASE_URL,
    }
    if db is not None:
        for row in db.query(AppSetting).filter(AppSetting.key.like("llm_%")).all():
            key = row.key[4:]
            if key in cfg and row.value != "":
                cfg[key] = row.value
    provider = (cfg["provider"] or "none").lower()
    d = DEFAULTS.get(provider, DEFAULTS["none"])
    cfg["provider"] = provider
    cfg["model"] = cfg["model"] or d["model"]
    cfg["base_url"] = (cfg["base_url"] or d["base_url"]).rstrip("/")
    return cfg


class LLM:
    def __init__(self, cfg: dict[str, str]):
        self.cfg = cfg
        self.provider = cfg["provider"]

    @classmethod
    def from_db(cls, db: Session | None) -> "LLM":
        return cls(load_config(db))

    @property
    def available(self) -> bool:
        if self.provider in ("none", ""):
            return False
        if self.provider in ("openai", "groq", "gemini", "anthropic") and not self.cfg["api_key"]:
            return False
        return True

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.cfg['model']}" if self.available else "offline-rules"

    # ------------------------------------------------------------------ core call
    def chat(self, messages: list[dict[str, str]], json_mode: bool = False, temperature: float = 0.1, max_tokens: int = 2000) -> str:
        if not self.available:
            raise LLMError("No GenAI provider configured")
        if self.provider == "mock":
            return _mock_reply(messages, json_mode)
        if self.provider == "anthropic":
            return self._anthropic(messages, temperature, max_tokens)
        return self._openai_compatible(messages, json_mode, temperature, max_tokens)

    def chat_json(self, messages: list[dict[str, str]], **kw) -> Any:
        last_err = None
        for attempt in range(2):
            text = self.chat(messages, json_mode=True, **kw)
            try:
                return parse_json(text)
            except ValueError as e:
                last_err = e
                messages = messages + [
                    {"role": "assistant", "content": text[:2000]},
                    {"role": "user", "content": "That was not valid JSON. Reply again with ONLY the JSON, no prose."},
                ]
        raise LLMError(f"Model did not return valid JSON: {last_err}")

    def _openai_compatible(self, messages, json_mode, temperature, max_tokens) -> str:
        url = f"{self.cfg['base_url']}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.cfg["api_key"]:
            headers["Authorization"] = f"Bearer {self.cfg['api_key']}"
        body: dict[str, Any] = {
            "model": self.cfg["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            r = httpx.post(url, json=body, headers=headers, timeout=settings.LLM_TIMEOUT)
            if r.status_code == 400 and json_mode:  # some servers reject response_format
                body.pop("response_format", None)
                r = httpx.post(url, json=body, headers=headers, timeout=settings.LLM_TIMEOUT)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"] or ""
        except httpx.HTTPStatusError as e:
            raise LLMError(f"{self.provider} returned {e.response.status_code}: {e.response.text[:300]}") from e
        except (httpx.HTTPError, KeyError, IndexError) as e:
            raise LLMError(f"Could not reach {self.provider} at {self.cfg['base_url']}: {e}") from e

    def _anthropic(self, messages, temperature, max_tokens) -> str:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] != "system"]
        body = {"model": self.cfg["model"], "max_tokens": max_tokens, "temperature": temperature, "messages": convo}
        if system:
            body["system"] = system
        headers = {"x-api-key": self.cfg["api_key"], "anthropic-version": "2023-06-01", "content-type": "application/json"}
        try:
            r = httpx.post(f"{self.cfg['base_url']}/v1/messages", json=body, headers=headers, timeout=settings.LLM_TIMEOUT)
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json().get("content", []))
        except httpx.HTTPStatusError as e:
            raise LLMError(f"anthropic returned {e.response.status_code}: {e.response.text[:300]}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Could not reach anthropic: {e}") from e


def parse_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # find the first balanced JSON object/array
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                c = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                elif c == '"':
                    in_str = True
                elif c == open_c:
                    depth += 1
                elif c == close_c:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(open_c, start + 1)
    raise ValueError("no JSON found")


# ---------------------------------------------------------------------- mock model (tests only)
def _mock_reply(messages: list[dict[str, str]], json_mode: bool) -> str:
    system = messages[0]["content"] if messages else ""
    last = messages[-1]["content"]
    if "MOCK_EXTRACT" in system or "extraction engine" in system:
        ids = [int(x) for x in re.findall(r"\[chunk (\d+)\]", last)]
        records = []
        for cid in ids[:3]:
            m = re.search(rf"\[chunk {cid}\][^\n]*\n(.+)", last)
            excerpt = (m.group(1) if m else "")[:60]
            records.append({"chunk_id": cid, "category": "task", "title": excerpt[:50] or "Task", "status": "pending",
                            "owner": "", "priority": "", "rationale": "", "excerpt": excerpt, "confidence": 0.8})
        return json.dumps({"records": records})
    if "TOOLS AVAILABLE" in system:
        observations = [m for m in messages if m["role"] == "user" and m["content"].startswith("OBSERVATION")]
        if not observations:
            return json.dumps({"thought": "I should search the records first.", "action": "search_records",
                               "args": {"query": re.sub(r"[^\w ]", " ", last)[:80]}})
        ids = re.findall(r"\bR(\d+)\b", observations[-1]["content"])[:3]
        cites = " ".join(f"[R{i}]" for i in ids)
        return json.dumps({"thought": "I have enough evidence.", "action": "final",
                           "args": {"answer": f"Based on the project records {cites}, here is what I found.", "citations": [int(i) for i in ids]}})
    if json_mode:
        return json.dumps({"summary": "Mock project summary.", "next_steps": ["Review pending tasks [R1]"], "first_week": ["Day 1: read handover"], "risks": []})
    return "Mock response."
