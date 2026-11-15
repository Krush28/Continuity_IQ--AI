"""Local text extraction from PDF (PyMuPDF), DOCX (python-docx), TXT and Markdown.

Output is a list of located units: each keeps its page number and section heading so every
record built from it can point back to exactly where it came from.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from pathlib import Path

BULLET_RE = re.compile(r"^\s*([-*•▪◦●○■□✓✔✗✘]|\[[ xX✓]\]|\d+[.)]|[a-z][.)])\s+")


@dataclass
class Unit:
    page: int
    section: str
    text: str


def _clean(text: str) -> str:
    text = text.replace(" ", " ").replace("​", "")
    return re.sub(r"[ \t]+", " ", text).strip()


def _looks_like_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 80 or BULLET_RE.match(s):
        return False
    if s.endswith((".", ",", ";")) or s.count(" ") > 9:
        return False
    if s.endswith(":") and len(s) < 60:
        return True
    letters = [c for c in s if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8 and len(s) > 3:
        return True
    return bool(re.match(r"^(\d+(\.\d+)*\s+)?[A-Z][\w/&()' -]+$", s)) and len(s.split()) <= 6


# ---------------------------------------------------------------- PDF
def extract_pdf(path: Path) -> tuple[list[Unit], int]:
    import pymupdf

    units: list[Unit] = []
    doc = pymupdf.open(path)
    sizes = []
    pages_lines = []
    for page in doc:
        lines = []
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = _clean("".join(s["text"] for s in spans))
                size = max(s["size"] for s in spans)
                bold = all((s["flags"] & 16) or "Bold" in s["font"] for s in spans)
                sizes.append(size)
                lines.append((text, size, bold, block["number"]))
        pages_lines.append(lines)
    body = statistics.median(sizes) if sizes else 11
    section = ""
    for pno, lines in enumerate(pages_lines, start=1):
        buf: list[str] = []
        last_block = None

        def flush():
            if buf:
                units.append(Unit(pno, section, _clean(" ".join(buf))))
                buf.clear()

        for text, size, bold, blockno in lines:
            is_heading = ((size > body * 1.12 or bold) and _looks_like_heading(text)) or (size > body * 1.4 and len(text) < 90)
            if is_heading:
                flush()
                section = text.rstrip(":").strip()
                last_block = blockno
                continue
            starts_item = bool(BULLET_RE.match(text)) or blockno != last_block
            if starts_item:
                flush()
            buf.append(text)
            last_block = blockno
        flush()
    n = doc.page_count
    doc.close()
    return units, n


# ---------------------------------------------------------------- DOCX
def extract_docx(path: Path) -> tuple[list[Unit], int]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(str(path))
    units: list[Unit] = []
    section = ""
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(el, d)
            text = _clean(p.text)
            if not text:
                continue
            style = (p.style.name or "").lower() if p.style is not None else ""
            bold = bool(p.runs) and all(r.bold for r in p.runs if r.text.strip())
            if style.startswith(("heading", "title")) or (bold and _looks_like_heading(text)):
                section = text.rstrip(":")
                continue
            if "list" in style and not BULLET_RE.match(text):
                text = "- " + text
            units.append(Unit(0, section, text))
        elif tag == "tbl":
            table = Table(el, d)
            rows = [[_clean(c.text) for c in row.cells] for row in table.rows]
            if not rows:
                continue
            header = rows[0]
            has_header = all(h and len(h) < 40 for h in header) and len(rows) > 1
            for row in rows[1 if has_header else 0:]:
                if not any(row):
                    continue
                if has_header:
                    cells = [f"{h}: {v}" for h, v in zip(header, row) if v]
                else:
                    cells = [v for v in row if v]
                units.append(Unit(0, section, " | ".join(dict.fromkeys(cells))))
    return units, 0


# ---------------------------------------------------------------- TXT / MD
def extract_text_file(path: Path) -> tuple[list[Unit], int]:
    units: list[Unit] = []
    section = ""
    para: list[str] = []

    def flush():
        if para:
            units.append(Unit(0, section, _clean(" ".join(para))))
            para.clear()

    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("#"):
            flush()
            section = line.lstrip("#").strip()
            continue
        if _looks_like_heading(line) and (line.endswith(":") or line.isupper()):
            flush()
            section = line.rstrip(":")
            continue
        if BULLET_RE.match(line):
            flush()
            para.append(line)
            flush()
            continue
        para.append(line)
    flush()
    return units, 0


def extract(path: Path) -> tuple[list[Unit], int]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        units, pages = extract_pdf(path)
    elif ext == ".docx":
        units, pages = extract_docx(path)
    elif ext in (".txt", ".md"):
        units, pages = extract_text_file(path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    units = [u for u in units if len(u.text) >= 3]
    return units, pages


def location_label(filename: str, page: int, section: str) -> str:
    parts = [filename]
    if page:
        parts.append(f"p.{page}")
    if section:
        parts.append(f"§ {section[:80]}")
    return " · ".join(parts)
