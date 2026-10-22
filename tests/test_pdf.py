import builtins

import pytest

from llm_wiki.sources import add_source, extract
from llm_wiki.storage import WikiError


def write_pdf(path, *, blank=False, encrypted=False):
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    if not blank:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 20 200 Td (Delivery: November 15, 2026.) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("test-password")
    writer.write(path)


def test_pdf_with_text_extracts_page_evidence(project, tmp_path):
    path = tmp_path / "contract.pdf"
    write_pdf(path)
    with project.operation():
        source = add_source(project, path)
        text = extract(project, source)
    assert "[Página 1]" in text
    assert "November 15, 2026" in text
    assert project.state()["sources"][source["id"]]["ingested_sha256"] is None


@pytest.mark.parametrize("mode", ["blank", "encrypted"])
def test_unreadable_pdf_stays_pending(project, tmp_path, mode):
    path = tmp_path / "document.pdf"
    write_pdf(path, blank=mode == "blank", encrypted=mode == "encrypted")
    with project.operation():
        source = add_source(project, path)
        with pytest.raises(WikiError, match="OCR|cifrado"):
            extract(project, source)
    assert project.state()["sources"][source["id"]]["ingested_sha256"] is None


def test_invalid_pdf_reports_failure(project, tmp_path):
    pytest.importorskip("pypdf")
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a PDF")
    with project.operation():
        source = add_source(project, path)
        with pytest.raises(WikiError, match="No se pudo leer"):
            extract(project, source)


def test_missing_pdf_extra_has_actionable_message(project, tmp_path, monkeypatch):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"%PDF-1.4")
    original_import = builtins.__import__

    def without_pdf(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("PDF extra unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_pdf)
    with project.operation():
        source = add_source(project, path)
        with pytest.raises(WikiError, match="extra 'pdf'"):
            extract(project, source)
