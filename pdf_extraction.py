"""Page-aware PDF extraction for IsoFlow (evidence-classification-v2).

The previous implementation joined every page of a PDF into one long
string, losing page boundaries and source filenames.  This module preserves
one :class:`~evidence_model.PageText` per page, so every quotation returned
by the engine can be traced to its source document and page.

Extraction health is reported, not hidden:

* blank pages are listed as warnings;
* a PDF that yields no extractable text at all is flagged;
* a PDF with pages but almost no extractable text is flagged as
  likely scanned / image-only (no OCR is performed — see README);
* a PDF that cannot be parsed at all produces an
  :class:`~evidence_model.ExtractedDocument` with ``extraction_error`` set
  instead of silently returning empty text.
"""

from __future__ import annotations

import io
import re
from typing import List, Optional

from evidence_model import ExtractedDocument, PageText

__all__ = ["extract_pdf_pages", "extract_pdf_text", "clean_text"]

_WHITESPACE_RUN = re.compile(r"[\t\r ]+")
_NEWLINE_RUN = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalise extracted text: drop NULs, collapse whitespace runs."""
    text = text.replace("\x00", " ")
    text = _WHITESPACE_RUN.sub(" ", text)
    text = _NEWLINE_RUN.sub("\n\n", text)
    return text.strip()


def extract_pdf_pages(
    pdf_bytes: bytes,
    filename: str,
    document_id: Optional[str] = None,
) -> ExtractedDocument:
    """Extract a PDF page by page.

    ``pdf_bytes`` is the raw PDF content; ``filename`` is the original
    uploaded name (preserved on every page).  ``document_id`` defaults to
    the filename and distinguishes documents when several PDFs share a
    name.
    """
    doc_id = document_id or filename
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:  # unreadable / corrupt PDF
        return ExtractedDocument(
            filename=filename,
            document_id=doc_id,
            pages=[],
            warnings=[f"Could not parse PDF: {exc}"],
            extraction_error=f"PDF parse failed: {exc}",
        )

    pages: List[PageText] = []
    warnings: List[str] = []
    try:
        raw_pages = list(reader.pages)
    except Exception as exc:
        return ExtractedDocument(
            filename=filename,
            document_id=doc_id,
            pages=[],
            warnings=[f"Could not read PDF pages: {exc}"],
            extraction_error=f"PDF page read failed: {exc}",
        )

    if not raw_pages:
        warnings.append("PDF contains no pages.")
        return ExtractedDocument(
            filename=filename,
            document_id=doc_id,
            pages=[],
            warnings=warnings,
            extraction_error="PDF contains no pages.",
        )

    for index, raw_page in enumerate(raw_pages, start=1):
        try:
            text = raw_page.extract_text() or ""
        except Exception as exc:  # one bad page must not lose the rest
            warnings.append(f"Page {index}: text extraction failed ({exc}).")
            text = ""
        text = clean_text(text)
        if not text:
            warnings.append(f"Page {index}: no extractable text (blank page).")
        pages.append(
            PageText(
                filename=filename,
                page=index,
                text=text,
                document_id=doc_id,
            )
        )

    doc = ExtractedDocument(
        filename=filename,
        document_id=doc_id,
        pages=pages,
        warnings=warnings,
    )
    if doc.total_chars == 0:
        doc.warnings.append(
            "No extractable text in this PDF. It may be a scanned or "
            "image-only document; IsoFlow does not perform OCR, so no "
            "evidence can be found in it."
        )
    elif doc.likely_scanned:
        doc.warnings.append(
            "Very little extractable text for the page count; this PDF is "
            "likely scanned or image-based. Evidence may be incomplete."
        )
    return doc


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Backwards-compatible helper: joined text of all pages.

    Kept for callers that need a single string (for example the gap-analysis
    combined-text path).  Page boundaries are marked with ``[Page N]`` so
    the joined text still carries traceability.  Prefer
    :func:`extract_pdf_pages` for new code.
    """
    doc = extract_pdf_pages(pdf_bytes, filename="document.pdf")
    return doc.text
