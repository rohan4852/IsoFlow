"""Unit tests: page-aware PDF extraction."""

import io

from pypdf import PdfWriter

from pdf_extraction import extract_pdf_pages, extract_pdf_text


def _minimal_pdf_with_text(text_lines):
    """Build a minimal valid PDF with one page per text line.

    pypdf cannot author text content, so the content stream is written
    by hand.  Each page gets a single text line.
    """
    # Object ids: 1 catalog, 2 pages, then per page a page object and a
    # contents stream; the font object comes last.
    n_pages = len(text_lines)
    page_obj_ids = [3 + 2 * i for i in range(n_pages)]
    content_ids = [4 + 2 * i for i in range(n_pages)]
    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    font_id = 3 + 2 * n_pages
    rebuilt = []
    rebuilt.append("<< /Type /Catalog /Pages 2 0 R >>")
    rebuilt.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>")
    for i, line in enumerate(text_lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
        rebuilt.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_ids[i]} 0 R >>"
        )
        rebuilt.append(
            f"<< /Length {len(stream)} >>\nstream\n"
            + stream.decode("latin-1")
            + "\nendstream"
        )
    rebuilt.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for idx, obj in enumerate(rebuilt):
        offsets.append(out.tell())
        out.write(f"{idx + 1} 0 obj\n".encode("latin-1"))
        out.write(obj.encode("latin-1"))
        out.write(b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(rebuilt) + 1}\n".encode("latin-1"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode("latin-1"))
    out.write(
        f"trailer\n<< /Size {len(rebuilt) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    )
    return out.getvalue()


def test_extract_preserves_page_boundaries():
    pdf = _minimal_pdf_with_text(["First page sentence.", "Second page sentence."])
    doc = extract_pdf_pages(pdf, "test.pdf")
    assert doc.filename == "test.pdf"
    assert len(doc.pages) == 2
    assert doc.pages[0].page == 1
    assert "First page sentence." in doc.pages[0].text
    assert doc.pages[1].page == 2
    assert "Second page sentence." in doc.pages[1].text
    # Pages must not be merged: page 1 text must not contain page 2 text.
    assert "Second page sentence." not in doc.pages[0].text


def test_extract_keeps_document_identity_per_page():
    pdf = _minimal_pdf_with_text(["Only page."])
    doc = extract_pdf_pages(pdf, "evidence.pdf")
    assert doc.pages[0].document_id == "evidence.pdf"
    assert doc.pages[0].filename == "evidence.pdf"


def test_extract_blank_page_is_flagged():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    doc = extract_pdf_pages(buf.getvalue(), "blank.pdf")
    assert len(doc.pages) == 1
    assert doc.pages[0].text == ""
    assert any("blank" in w.lower() for w in doc.warnings)
    assert doc.likely_scanned is True


def test_extract_invalid_bytes_returns_error_document():
    doc = extract_pdf_pages(b"this is not a pdf", "broken.pdf")
    assert doc.extraction_error is not None
    assert doc.pages == []


def test_extract_text_wrapper_keeps_page_markers():
    pdf = _minimal_pdf_with_text(["Alpha line.", "Beta line."])
    text = extract_pdf_text(pdf)
    assert "[Page 1]" in text
    assert "[Page 2]" in text
    assert "Alpha line." in text
    assert "Beta line." in text


def test_extract_multiple_documents_stay_separate():
    pdf_a = _minimal_pdf_with_text(["Document A content."])
    pdf_b = _minimal_pdf_with_text(["Document B content."])
    doc_a = extract_pdf_pages(pdf_a, "a.pdf")
    doc_b = extract_pdf_pages(pdf_b, "b.pdf")
    assert doc_a.pages[0].document_id == "a.pdf"
    assert doc_b.pages[0].document_id == "b.pdf"
    assert "Document B" not in doc_a.pages[0].text
