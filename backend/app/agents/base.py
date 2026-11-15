"""A small, provider-agnostic agent runtime.

The agent works in a Reason → Act → Observe loop. Each step the model replies with JSON:
    {"thought": "...", "action": "<tool name>|final", "args": {...}}
We run the tool, feed the observation back, and repeat until "final" or the step budget runs out.
JSON-in-text (instead of a vendor's native tool-calling) keeps it working with small local models
via Ollama as well as with hosted APIs. Every step is recorded in a trace shown in the UI.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..llm import LLM, LLMError
from ..models import AgentRun


@dataclass
class Tool:
    name: str
    description: str
    args: dict[str, str]
    fn: Callable[..., Any]


@dataclass
class Trace:
    steps: list[dict] = field(default_factory=list)
    t0: float = field(default_factory=time.time)

    def add(self, kind: str, content: Any, **extra) -> None:
        self.steps.append({"step": len(self.steps) + 1, "kind": kind, "content": content,
                           "ms": int((time.time() - self.t0) * 1000), **extra})


def start_run(db: Session, project_id: int, agent: str, provider: str, user_id: int | None, input_text: str = "") -> AgentRun:
    run = AgentRun(project_id=project_id, agent=agent, provider=provider, started_by=user_id, input=input_text[:2000])
    db.add(run)
    db.flush()
    return run


def finish_run(db: Session, run: AgentRun, trace: Trace, output: dict, status: str = "completed") -> AgentRun:
    run.trace = trace.steps
    run.output = output
    run.status = status
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return run


class ToolAgent:
    def __init__(self, llm: LLM, name: str, role: str, tools: list[Tool], max_steps: int = 8):
        self.llm = llm
        self.name = name
        self.role = role
        self.tools = {t.name: t for t in tools}
        self.max_steps = max_steps

    def _system_prompt(self) -> str:
        tool_lines = "\n".join(
            f"- {t.name}({', '.join(f'{k}: {v}' for k, v in t.args.items())}): {t.description}" for t in self.tools.values()
        )
        return (
            f"You are {self.name}, an agent inside ContinuityIQ, a project handover system.\n{self.role}\n\n"
            "RULES:\n"
            "- Use ONLY information returned by tools. Never invent facts, names, dates or statuses.\n"
            "- Refer to records as [R<id>] when you rely on them.\n"
            "- Call one tool per step. Be efficient: stop as soon as you have enough evidence.\n\n"
            f"TOOLS AVAILABLE:\n{tool_lines}\n- final(...): finish. Put the result in args as described in your task.\n\n"
            'Reply with ONLY a JSON object: {"thought": "short reasoning", "action": "<tool name or final>", "args": {...}}'
        )

    def run(self, task: str, trace: Trace) -> dict:
        messages = [{"role": "system", "content": self._system_prompt()}, {"role": "user", "content": task}]
        for _ in range(self.max_steps):
            try:
                reply = self.llm.chat_json(messages, max_tokens=1200)
            except LLMError as e:
                trace.add("error", str(e))
                raise
            if not isinstance(reply, dict):
                reply = {"action": "final", "args": {"answer": str(reply)}}
            thought = str(reply.get("thought", ""))[:600]
            action = str(reply.get("action", "final"))
            args = reply.get("args") or {}
            if thought:
                trace.add("thought", thought)
            if action == "final":
                trace.add("final", args)
                return args
            tool = self.tools.get(action)
            if not tool:
                obs = f"Unknown tool '{action}'. Available: {', '.join(self.tools)} or final."
            else:
                trace.add("action", {"tool": action, "args": args})
                try:
                    obs = tool.fn(**{k: v for k, v in args.items() if k in tool.args})
                except Exception as e:  # tool errors are fed back to the model, not raised
                    obs = f"Tool error: {e}"
            obs_text = obs if isinstance(obs, str) else json.dumps(obs, default=str)
            trace.add("observation", obs_text[:1500])
            messages.append({"role": "assistant", "content": json.dumps(reply)[:3000]})
            messages.append({"role": "user", "content": f"OBSERVATION from {action}:\n{obs_text[:6000]}"})
        trace.add("error", "Step budget reached; asking the agent to conclude.")
        messages.append({"role": "user", "content": "Step budget reached. Reply now with action=final and your best result."})
        reply = self.llm.chat_json(messages, max_tokens=1200)
        args = (reply or {}).get("args", {}) if isinstance(reply, dict) else {}
        trace.add("final", args)
        return args
