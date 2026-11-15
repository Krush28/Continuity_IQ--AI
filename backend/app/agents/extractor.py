"""Extraction Agent: GenAI reads located source chunks and returns structured records.

Every AI record must quote an excerpt from the chunk it came from. A grounding verifier checks that
the excerpt really exists in the source; anything that cannot be verified is flagged, and records
pointing at non-existent chunks are dropped. Nothing is inferred beyond the uploaded text.
"""
from __future__ import annotations

import re

from ..llm import LLM, LLMError
from ..search import tokenize
from .base import Trace

CATEGORIES = {"task", "decision", "issue", "dependency", "contact", "note"}
TASK_STATUS = {"completed", "ongoing", "pending"}

SYSTEM = """You are the extraction engine of ContinuityIQ, a project handover system.
You receive numbered chunks of text from a project document. Extract the facts an incoming team
member needs. For each useful fact return one record:
  chunk_id   - the [chunk N] number the fact comes from
  category   - task | decision | issue | dependency | contact | note
  title      - short, specific (max 15 words)
  status     - tasks: completed | ongoing | pending ; issues: open | resolved ; others: ""
  owner      - person responsible, only if the text names one, else ""
  priority   - high | medium | low if stated or obvious from severity words, else ""
  rationale  - decisions only: the reason given in the text, else ""
  excerpt    - an EXACT short quote (5-25 words) copied from that chunk that supports the record
  confidence - 0.0-1.0
Rules: use only the given text; never invent owners, dates or reasons; skip filler, headings and
boilerplate; a chunk may produce 0, 1 or several records; "note" is for project context such as goals or scope.
Reply with JSON: {"records": [ ... ]}"""


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def grounded(excerpt: str, chunk_text: str) -> bool:
    if not excerpt:
        return False
    ne, nc = _norm(excerpt), _norm(chunk_text)
    if ne and ne in nc:
        return True
    et = tokenize(excerpt)
    if not et:
        return False
    ct = set(tokenize(chunk_text))
    return sum(t in ct for t in et) / len(et) >= 0.75


def ai_extract(llm: LLM, filename: str, chunks: list[tuple[int, str, str]], trace: Trace, batch_chars: int = 6000):
    """chunks: list of (chunk_id, location, text). Returns (records_by_chunk, covered_chunk_ids, stats)."""
    by_id = {cid: text for cid, _, text in chunks}
    batches, cur, size = [], [], 0
    for c in chunks:
        if cur and size + len(c[2]) > batch_chars:
            batches.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += len(c[2]) + 40
    if cur:
        batches.append(cur)

    results: dict[int, list[dict]] = {}
    covered: set[int] = set()
    stats = {"batches": len(batches), "ai_records": 0, "verified": 0, "unverified": 0, "dropped": 0, "failed_batches": 0}
    for bi, batch in enumerate(batches, 1):
        body = "\n\n".join(f"[chunk {cid}] ({loc})\n{text}" for cid, loc, text in batch)
        trace.add("action", {"tool": "llm_extract", "args": {"file": filename, "batch": f"{bi}/{len(batches)}", "chunks": len(batch)}})
        try:
            data = llm.chat_json([{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": f"Document: {filename}\n\n{body}"}], max_tokens=3000)
        except LLMError as e:
            stats["failed_batches"] += 1
            trace.add("error", f"Batch {bi} failed, rules will cover it: {e}")
            continue
        items = data.get("records", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        batch_ids = {cid for cid, _, _ in batch}
        covered |= batch_ids
        for it in items:
            if not isinstance(it, dict):
                continue
            try:
                cid = int(it.get("chunk_id"))
            except (TypeError, ValueError):
                stats["dropped"] += 1
                continue
            if cid not in batch_ids:
                stats["dropped"] += 1
                continue
            cat = str(it.get("category", "note")).lower()
            cat = cat if cat in CATEGORIES else "note"
            status = str(it.get("status", "")).lower()
            if cat == "task" and status not in TASK_STATUS:
                status = "pending"
            if cat == "issue" and status not in ("open", "resolved"):
                status = "open"
            if cat not in ("task", "issue"):
                status = ""
            excerpt = str(it.get("excerpt", ""))[:600]
            ok = grounded(excerpt, by_id[cid])
            try:
                conf = max(0.0, min(1.0, float(it.get("confidence", 0.7))))
            except (TypeError, ValueError):
                conf = 0.7
            rec = {
                "category": cat,
                "title": str(it.get("title", ""))[:300] or excerpt[:120],
                "detail": "",
                "status": status,
                "owner": str(it.get("owner", ""))[:120],
                "priority": str(it.get("priority", "")).lower()[:20],
                "rationale": str(it.get("rationale", ""))[:1000],
                "confidence": round(conf if ok else min(conf, 0.35), 2),
                "flagged": not ok,
                "flag_reason": "" if ok else "AI quote could not be verified in the source text — check before approving.",
                "excerpt": excerpt if ok else "",
            }
            # Owners must appear in the source text — otherwise they are hallucinated.
            if rec["owner"] and rec["owner"].split()[0].lower() not in by_id[cid].lower():
                rec["owner"] = ""
            stats["ai_records"] += 1
            stats["verified" if ok else "unverified"] += 1
            results.setdefault(cid, []).append(rec)
        trace.add("observation", f"Batch {bi}: {len(items)} records proposed")
    return results, covered, stats
