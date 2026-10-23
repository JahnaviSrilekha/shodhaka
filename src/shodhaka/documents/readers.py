"""Turn PDF and Word files into Markdown-style text so they split into sections like any ADR.

Word: real heading styles (Title, Heading 1..3) become `#`/`##` lines; tables become pipe rows.
PDF:  there are no heading styles, so headings are found by font size: a line set larger than
      the body text becomes a `##` heading. If a PDF uses one size throughout, a conservative
      text rule is used instead (short numbered or Title Case lines without a full stop).

Both libraries are optional: `pip install -e ".[docs]"`. Without them the files are skipped
with a clear message instead of failing the run.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


class ReaderUnavailable(RuntimeError):
    pass


# --------------------------------------------------------------------------- Word


def docx_to_markdown(path: Path) -> str:
    try:
        import docx  # python-docx
    except ImportError as exc:
        raise ReaderUnavailable('python-docx is not installed: pip install -e ".[docs]"') from exc

    document = docx.Document(str(path))
    lines: list[str] = []
    body = document.element.body
    paragraphs = {p._element: p for p in document.paragraphs}
    tables = {t._element: t for t in document.tables}
    for child in body.iterchildren():  # keeps paragraphs and tables in document order
        if child in paragraphs:
            p = paragraphs[child]
            text = p.text.strip()
            if not text:
                continue
            style = (p.style.name or "").lower() if p.style is not None else ""
            if style == "title":
                lines.append(f"# {text}")
            elif style.startswith("heading"):
                level = re.findall(r"\d+", style)
                depth = int(level[0]) if level else 1
                lines.append(f"{'#' * min(depth + 1, 3)} {text}")
            else:
                lines.append(text)
            lines.append("")
        elif child in tables:
            for row in tables[child].rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                lines.append(" | ".join(cells))
            lines.append("")
    return "\n".join(lines).strip() + "\n"


# --------------------------------------------------------------------------- PDF

HEADING_TEXT = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s+)?[A-Z][\w ,/&()'’\-–]{1,70}$")


def _looks_like_heading(line: str) -> bool:
    words = line.split()
    return bool(HEADING_TEXT.match(line)) and 1 <= len(words) <= 8 and not line.endswith((".", ",", ";", ":"))


def pdf_to_markdown(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ReaderUnavailable('pypdf is not installed: pip install -e ".[docs]"') from exc

    reader = PdfReader(str(path))
    lines: list[tuple[str, float]] = []  # (text, font size)
    for page in reader.pages:
        current: list[str] = []
        sizes: list[float] = []

        def visit(text, cm, tm, font_dict, font_size):
            size = abs(font_size * (tm[3] if tm[3] else 1.0))
            parts = text.split("\n")
            for i, part in enumerate(parts):
                if part.strip():
                    current.append(part)
                    sizes.append(size)
                if i < len(parts) - 1:
                    flush()

        def flush():
            line = " ".join("".join(current).split())
            if line:
                lines.append((line, max(sizes) if sizes else 0.0))
            current.clear()
            sizes.clear()

        page.extract_text(visitor_text=visit)
        flush()

    if not lines:
        return ""
    body_size = Counter(round(size, 1) for _, size in lines).most_common(1)[0][0]
    sized = any(size > body_size + 0.5 for _, size in lines)

    out: list[str] = []
    title_done = False
    for text, size in lines:
        larger = size > body_size + 0.5
        if sized:
            is_heading = larger and len(text.split()) <= 12
        else:
            is_heading = _looks_like_heading(text)
        if is_heading and not title_done:
            out += [f"# {text}", ""]
            title_done = True
        elif is_heading:
            out += ["", f"## {text}", ""]
        else:
            out.append(text)
    return "\n".join(out).strip() + "\n"


READERS = {".docx": docx_to_markdown, ".pdf": pdf_to_markdown}
