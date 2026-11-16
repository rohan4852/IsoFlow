"""Excel and CSV export for IsoFlow (evidence-classification-v2).

The previous formatter read a 4-column CSV from disk and coloured every
non-compliant row identically red.  This version preserves the complete
evidence chain in the shared 21-column schema (see
``evidence_model.EXPORT_COLUMNS``), with one row per evidence passage so
no evidence is discarded.

* Excel and CSV use the identical column order and values.
* A ``Summary`` sheet lists the count of each of the seven statuses.
* The header row is frozen and auto-filtered; long text wraps.
* Each status has its own fill colour — review states are not coloured
  identically to non-compliant states.
* Excel is generated in memory; no intermediate report files are written
  to the server filesystem.

Backwards compatibility: :func:`generate_excel_bytes` still accepts a CSV
file path (the legacy 4-column layout is detected and expanded to the new
schema with empty structured fields), a :class:`pandas.DataFrame`, or a
list of :class:`~evidence_model.EvidenceResult`.
"""

from __future__ import annotations

import io
from typing import Any, List, Sequence

import pandas as pd

from evidence_model import (
    EXPORT_COLUMNS,
    EvidenceResult,
    EvidenceStatus,
    results_to_export_rows,
)

__all__ = [
    "generate_excel_bytes",
    "generate_csv_bytes",
    "results_to_dataframe",
    "STATUS_FILL",
]

# Distinct fills per status.  Review states (Needs Review, Conflicting
# Evidence) use amber/blue tones; Non-Compliant uses red; Not Found uses
# grey; Analysis Error uses dark red with white text.
STATUS_FILL = {
    EvidenceStatus.COMPLIANT.value: {"bg_color": "#dcfce7", "font_color": "#166534"},
    EvidenceStatus.PARTIALLY_COMPLIANT.value: {"bg_color": "#fef9c3", "font_color": "#854d0e"},
    EvidenceStatus.NON_COMPLIANT.value: {"bg_color": "#fee2e2", "font_color": "#991b1b"},
    EvidenceStatus.NOT_FOUND.value: {"bg_color": "#f1f5f9", "font_color": "#475569"},
    EvidenceStatus.CONFLICTING_EVIDENCE.value: {"bg_color": "#ffedd5", "font_color": "#9a3412"},
    EvidenceStatus.NEEDS_REVIEW.value: {"bg_color": "#dbeafe", "font_color": "#1e40af"},
    EvidenceStatus.ANALYSIS_ERROR.value: {"bg_color": "#7f1d1d", "font_color": "#ffffff"},
}

_COLUMN_WIDTHS = {
    "Filename": 22,
    "Control ID": 13,
    "Control Name": 26,
    "Requirement": 42,
    "Status": 20,
    "Requirement Coverage": 13,
    "Evidence Type": 20,
    "Evidence Quotation": 62,
    "Source Page": 11,
    "Source Document": 22,
    "Covered Scope": 26,
    "Uncovered Scope": 26,
    "Missing Elements": 30,
    "Conflicts": 30,
    "Exceptions": 30,
    "Reasoning": 48,
    "Confidence": 11,
    "Review Required": 13,
    "Reviewer Decision": 16,
    "Reviewer Comments": 30,
    "Analysis Error": 34,
}

_LEGACY_COLUMNS = {"filename", "control_id", "audit_finding", "evidence"}


def results_to_dataframe(results: Sequence[EvidenceResult]) -> pd.DataFrame:
    """Convert structured results to the 21-column DataFrame."""
    rows = results_to_export_rows(list(results))
    return pd.DataFrame(rows, columns=EXPORT_COLUMNS)


def _coerce_to_dataframe(data: Any) -> pd.DataFrame:
    """Accept results, a DataFrame, or a legacy CSV path and normalise."""
    if isinstance(data, pd.DataFrame):
        df = data.copy()
        if set(map(str.lower, df.columns)) <= _LEGACY_COLUMNS:
            df = _expand_legacy_dataframe(df)
        return _ensure_columns(df)
    if isinstance(data, (list, tuple)) and data and isinstance(data[0], EvidenceResult):
        return results_to_dataframe(data)
    if isinstance(data, str):
        df = pd.read_csv(data)
        if set(map(str.lower, df.columns)) <= _LEGACY_COLUMNS:
            df = _expand_legacy_dataframe(df)
        return _ensure_columns(df)
    raise ValueError(
        "generate_excel_bytes expects a list of EvidenceResult, a DataFrame, "
        "or a CSV file path."
    )


def _expand_legacy_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Map the old 4-column audit CSV onto the new 21-column schema."""
    lower = {c.lower(): c for c in df.columns}
    out = pd.DataFrame(
        {
            "Filename": df[lower.get("filename", df.columns[0])] if "filename" in lower else "",
            "Control ID": df[lower.get("control_id", df.columns[0])] if "control_id" in lower else "",
            "Control Name": "",
            "Requirement": "",
            "Status": df[lower.get("audit_finding", df.columns[0])] if "audit_finding" in lower else "",
            "Requirement Coverage": "",
            "Evidence Type": "",
            "Evidence Quotation": df[lower.get("evidence", df.columns[0])] if "evidence" in lower else "",
            "Source Page": "",
            "Source Document": "",
            "Covered Scope": "",
            "Uncovered Scope": "",
            "Missing Elements": "",
            "Conflicts": "",
            "Exceptions": "",
            "Reasoning": "",
            "Confidence": "",
            "Review Required": "",
            "Reviewer Decision": "",
            "Reviewer Comments": "",
            "Analysis Error": "",
        }
    )
    return out


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column in EXPORT_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df[EXPORT_COLUMNS]


def generate_csv_bytes(data: Any) -> bytes:
    """Generate the 21-column CSV (same schema as the Excel export)."""
    df = _coerce_to_dataframe(data)
    return df.to_csv(index=False).encode("utf-8")


def generate_excel_bytes(data: Any) -> bytes:
    """Generate the styled Excel workbook in memory.

    Sheets: ``Audit_Trail`` (one row per evidence passage) and ``Summary``
    (per-status counts).  The header row is frozen with an auto-filter;
    text wraps; each status has its own fill.
    """
    df = _coerce_to_dataframe(data)

    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine="xlsxwriter")
    df.to_excel(writer, sheet_name="Audit_Trail", index=False)

    workbook = writer.book
    worksheet = writer.sheets["Audit_Trail"]

    header_format = workbook.add_format(
        {"bold": True, "bg_color": "#0f172a", "font_color": "white", "border": 1}
    )
    standard_format = workbook.add_format(
        {"border": 1, "text_wrap": True, "valign": "top"}
    )
    status_formats = {
        status: workbook.add_format(
            {"border": 1, "text_wrap": True, "valign": "top", **style}
        )
        for status, style in STATUS_FILL.items()
    }

    for col_num, value in enumerate(df.columns.values):
        worksheet.write(0, col_num, value, header_format)

    status_col = df.columns.get_loc("Status")
    for row_num in range(1, len(df) + 1):
        status = str(df.iloc[row_num - 1, status_col])
        row_status_format = status_formats.get(status, standard_format)
        for col_num in range(len(df.columns)):
            value = df.iloc[row_num - 1, col_num]
            cell = "" if pd.isna(value) else value
            fmt = row_status_format if col_num == status_col else standard_format
            worksheet.write(row_num, col_num, cell, fmt)

    for col_num, column in enumerate(df.columns):
        width = _COLUMN_WIDTHS.get(column, 20)
        worksheet.set_column(col_num, col_num, width)

    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)

    # Summary sheet with per-status counts.
    summary = worksheet_summary_data(df)
    summary_sheet = workbook.add_worksheet("Summary")
    summary_sheet.write(0, 0, "Status", header_format)
    summary_sheet.write(0, 1, "Count", header_format)
    for row_num, (status, count) in enumerate(summary, start=1):
        fmt = status_formats.get(status, standard_format)
        summary_sheet.write(row_num, 0, status, fmt)
        summary_sheet.write(row_num, 1, count, standard_format)
    summary_sheet.write(len(summary) + 1, 0, "Total controls (rows)", standard_format)
    summary_sheet.write(len(summary) + 1, 1, len(df), standard_format)
    summary_sheet.set_column(0, 0, 24)
    summary_sheet.set_column(1, 1, 10)

    writer.close()
    return output.getvalue()


def worksheet_summary_data(df: pd.DataFrame) -> List[tuple]:
    """Per-status counts in a stable order for the Summary sheet."""
    counts = df["Status"].value_counts().to_dict() if "Status" in df.columns else {}
    ordered = [
        (status.value, int(counts.get(status.value, 0)))
        for status in EvidenceStatus
    ]
    return ordered
