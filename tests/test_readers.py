import logging
from pathlib import Path

import pytest
from conftest import ROOT

from shodhaka.analysis.engine import analyze
from shodhaka.documents import model as documents
from shodhaka.documents.readers import ReaderUnavailable
from shodhaka.evaluation.scoring import evaluate

FORMATS = ROOT / "samples" / "acme-arch" / "formats"

pytest.importorskip("pypdf")
pytest.importorskip("docx")


def headings(path):
    doc = documents.load_document(path, path.parent)
    return doc.title, [s.heading for s in doc.sections]


def test_docx_keeps_heading_styles():
    title, heads = headings(FORMATS / "adr-002-billing-invoices.docx")
    assert title.startswith("ADR-002")
    assert heads == ["Preamble", "Context", "Decision", "Reading order data", "Publishing invoices", "Tax calculation"]


def test_pdf_headings_found_by_font_size():
    title, heads = headings(FORMATS / "adr-003-notification-service.pdf")
    assert title.startswith("ADR-003")
    assert heads == ["Preamble", "Context", "Decision", "Data", "Messages"]


def test_pdf_with_one_font_size_falls_back_to_text_rule(tmp_path: Path):
    reportlab = pytest.importorskip("reportlab")  # noqa: F841
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    body = getSampleStyleSheet()["BodyText"]
    lines = ["ADR-009 Search index", "1. Context", "Users search products by name.",
             "2. Data access", "Search reads the catalog database of the Product service directly."]
    path = tmp_path / "adr.pdf"
    SimpleDocTemplate(str(path), pagesize=A4).build([Paragraph(t, body) for t in lines])
    title, heads = headings(path)
    assert title == "ADR-009 Search index"
    assert heads == ["1. Context", "2. Data access"]


def test_formats_find_the_same_gaps_as_markdown(pack, scripted):
    report = analyze(pack, documents.discover(FORMATS), scripted)
    result = evaluate(report, FORMATS / "expected.json")
    assert result["missing_findings"] == [] and result["exact_accuracy"] == 1.0


def test_missing_library_skips_file_with_warning(monkeypatch, caplog, tmp_path: Path):
    def unavailable(path):
        raise ReaderUnavailable('pypdf is not installed: pip install -e ".[docs]"')

    monkeypatch.setitem(documents.READERS, ".pdf", unavailable)
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "b.md").write_text("# B\n\n## Data\nOwns its data.\n")
    with caplog.at_level(logging.WARNING):
        found = documents.discover(tmp_path)
    assert [d.path for d in found] == ["b.md"]
    assert "skipped a.pdf" in caplog.text and "pip install" in caplog.text


def test_unreadable_pdf_is_skipped_not_fatal(caplog, tmp_path: Path):
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf at all")
    with caplog.at_level(logging.WARNING):
        assert documents.discover(tmp_path) == []
    assert "skipped broken.pdf" in caplog.text


def test_bookkeeping_files_are_not_reviewed(tmp_path: Path):
    (tmp_path / "ATTRIBUTION.md").write_text("# Sources\n\n| Repo | Licence |\n")
    (tmp_path / "adr.md").write_text("# ADR\n\n## Data\nOwns its data.\n")
    assert [d.path for d in documents.discover(tmp_path)] == ["adr.md"]
