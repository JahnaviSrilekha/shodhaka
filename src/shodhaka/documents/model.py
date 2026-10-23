"""Find the documents under review and split them into sections.

Markdown is split at `##` headings so each Decider request reads one focused section.
PDF and Word files are converted to the same Markdown shape first (see readers.py).
Configuration files and Dockerfiles are kept whole: deterministic checks read them line by line.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from shodhaka.documents.readers import READERS, ReaderUnavailable

log = logging.getLogger(__name__)

SKIP_FILES = {"expected.json", "ATTRIBUTION.md", "DATA_SOURCES.md"}  # bookkeeping, not documents
MAX_SECTION_CHARS = 6000  # keeps a section well inside Decider's 4,096-token window


@dataclass(frozen=True)
class Section:
    id: str
    heading: str
    text: str
    start_line: int


@dataclass
class Document:
    path: str  # relative to the input root, with forward slashes
    kind: str  # adr | config | dockerfile
    text: str
    title: str = ""
    sections: list[Section] = field(default_factory=list)


def classify(path: Path) -> str | None:
    name = path.name.lower()
    if name == "dockerfile" or name.endswith(".dockerfile"):
        return "dockerfile"
    if path.suffix.lower() in {".yml", ".yaml", ".properties"}:
        return "config"
    if path.suffix.lower() in {".md", ".markdown", ".pdf", ".docx"}:
        return "adr"
    return None


def split_markdown(text: str) -> tuple[str, list[Section]]:
    lines = text.splitlines()
    title = ""
    sections: list[Section] = []
    heading, start, buffer = "Preamble", 1, []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            index = len(sections) + 1
            sections.append(Section(f"s{index}", heading, body[:MAX_SECTION_CHARS], start))

    for number, line in enumerate(lines, start=1):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        match = re.match(r"^#{2,3}\s+(.*)", line)
        if match:
            flush()
            heading, start, buffer = match.group(1).strip(), number, []
        else:
            buffer.append(line)
    flush()
    return title, sections


def load_document(path: Path, root: Path) -> Document | None:
    kind = classify(path)
    if kind is None:
        return None
    relative = path.relative_to(root).as_posix()
    suffix = path.suffix.lower()
    if suffix in READERS:
        try:
            text = READERS[suffix](path)
        except ReaderUnavailable as exc:
            log.warning("skipped %s: %s", relative, exc)
            return None
        except Exception as exc:  # noqa: BLE001 (one unreadable file must not stop the run)
            log.warning("skipped %s: could not read it (%s)", relative, exc)
            return None
        if not text.strip():
            log.warning("skipped %s: no extractable text (scanned PDF? run OCR first)", relative)
            return None
    else:
        text = path.read_text(encoding="utf-8")
    return document_from_text(relative, text)


def document_from_text(relative: str, text: str) -> Document | None:
    """Build a Document from text that was already extracted (or edited by a reviewer in the UI).
    The kind still comes from the original file name, so an edited PDF stays a design doc."""
    path = Path(relative)
    kind = classify(path)
    if kind is None:
        return None
    if kind == "adr":
        title, sections = split_markdown(text)
        return Document(relative, kind, text, title or path.stem, sections)
    return Document(relative, kind, text, path.name, [Section("s1", path.name, text, 1)])


def discover(root: str | Path) -> list[Document]:
    root = Path(root).resolve()
    documents = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name in SKIP_FILES or any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        document = load_document(path, root)
        if document is not None:
            documents.append(document)
    return documents


def sentences(text: str) -> list[str]:
    """Split a section into sentences for evidence quotes (keeps it simple and deterministic)."""
    flat = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z`(])", flat)
    return [p.strip() for p in parts if len(p.strip()) > 3]
