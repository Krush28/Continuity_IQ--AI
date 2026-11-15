"""Offline keyword search (BM25) over records and raw source text. No vector DB needed."""
from __future__ import annotations

import math
import re
from collections import Counter

from sqlalchemy.orm import Session

from .models import Chunk, Document, Record

STOP = set("""a an the and or of to in on for with is are was were be been it this that at by from as
we you i our your their they he she his her not no yes do does did has have had will would should can
could what which who whom when where why how all any each into about over than then there here so if""".split())


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9][a-z0-9_+#.-]*", text.lower())
    out = []
    for t in toks:
        t = t.strip(".-")
        if not t or t in STOP:
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.N = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.N) if self.N else 0
        df = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        self.tf = [Counter(d) for d in docs]

    def score(self, query: list[str], i: int) -> float:
        s, dl = 0.0, len(self.docs[i]) or 1
        for t in query:
            f = self.tf[i].get(t)
            if not f:
                continue
            s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
        return s


def record_text(r: Record) -> str:
    return " ".join(filter(None, [r.title, r.detail, r.owner, r.rationale, r.category, r.status, r.source_excerpt]))


def search_records(db: Session, project_id: int, query: str, category: str | None = None,
                   approved_only: bool = False, limit: int = 10) -> list[tuple[Record, float]]:
    q = db.query(Record).filter(Record.project_id == project_id, Record.review_state != "rejected")
    if category:
        q = q.filter(Record.category == category)
    if approved_only:
        q = q.filter(Record.review_state == "approved")
    records = q.all()
    if not records:
        return []
    qt = tokenize(query)
    if not qt:
        return [(r, 0.0) for r in records[:limit]]
    bm = BM25([tokenize(record_text(r)) for r in records])
    scored = [(r, bm.score(qt, i)) for i, r in enumerate(records)]
    scored = [x for x in scored if x[1] > 0]
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


def search_chunks(db: Session, project_id: int, query: str, limit: int = 8) -> list[tuple[Chunk, Document, float]]:
    rows = db.query(Chunk, Document).join(Document, Chunk.document_id == Document.id).filter(Chunk.project_id == project_id).all()
    if not rows:
        return []
    qt = tokenize(query)
    bm = BM25([tokenize(f"{c.section} {c.text}") for c, _ in rows])
    scored = [(c, d, bm.score(qt, i)) for i, (c, d) in enumerate(rows)]
    scored = [x for x in scored if x[2] > 0]
    scored.sort(key=lambda x: -x[2])
    return scored[:limit]


def similarity(a: str, b: str) -> float:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def containment(a: str, b: str) -> float:
    """Share of the shorter text's terms found in the longer one (good for 'same item, more detail')."""
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if len(ta) < 2 or len(tb) < 2:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def highlight(text: str, query: str, width: int = 220) -> str:
    """Return a short snippet of text around the first query hit."""
    terms = [t for t in tokenize(query)]
    low = text.lower()
    pos = min([low.find(t) for t in terms if low.find(t) >= 0] or [0])
    start = max(0, pos - width // 3)
    snippet = text[start : start + width]
    return ("…" if start else "") + snippet + ("…" if start + width < len(text) else "")
