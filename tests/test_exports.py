"""Unit tests: Excel and CSV exports (shared 21-column schema)."""

import io

import openpyxl
import pandas as pd
import pytest

from evidence_model import (
    EXPORT_COLUMNS,
    Coverage,
    EvidencePassage,
    EvidenceResult,
    EvidenceStatus,
    EvidenceType,
)
from excel_formatter import (
    STATUS_FILL,
    generate_csv_bytes,
    generate_excel_bytes,
    results_to_dataframe,
)


def _sample_results():
    return [
        EvidenceResult(
            filename="policy.pdf",
            control_id="NS-02",
            control_name="Multi-factor authentication",
            requirement="MFA is required for all users",
            status=EvidenceStatus.PARTIALLY_COMPLIANT,
            requirement_coverage=Coverage.PARTIAL,
            evidence=[
                EvidencePassage(quote="Multi-factor authentication is required for administrators.", source_document="policy.pdf", page=1, evidence_type=EvidenceType.POLICY),
            ],
            covered_scope=["Administrators"],
            uncovered_scope=["Non-admin users"],
            missing_elements=["MFA evidence for non-admin users."],
            reasoning="MFA covers administrators only.",
            review_required=True,
        ),
        EvidenceResult(
            filename="policy.pdf",
            control_id="NS-14",
            control_name="Physical access logging",
            requirement="Physical access to the server room is logged and reviewed monthly",
            status=EvidenceStatus.NOT_FOUND,
            requirement_coverage=Coverage.NONE,
            evidence=[],
            missing_elements=["Server-room access logs."],
            reasoning="No relevant evidence was found.",
        ),
        EvidenceResult(
            filename="policy.pdf",
            control_id="NS-13",
            control_name="Finding remediation",
            requirement="High findings are remediated within 30 days of identification",
            status=EvidenceStatus.NON_COMPLIANT,
            requirement_coverage=Coverage.PARTIAL,
            evidence=[
                EvidencePassage(quote="Finding F-22, identified 2026-01-15, remains open as of 2026-11-01 with no approved exception.", source_document="policy.pdf", page=4, evidence_type=EvidenceType.OPERATIONAL_RECORD),
            ],
            reasoning="Finding F-22 is overdue with no approved exception.",
            review_required=True,
        ),
    ]


def test_export_schema_has_21_columns():
    assert len(EXPORT_COLUMNS) == 21
    assert EXPORT_COLUMNS[0] == "Filename"
    assert EXPORT_COLUMNS[4] == "Status"
    assert EXPORT_COLUMNS[-1] == "Analysis Error"


def test_csv_export_matches_schema_and_rows():
    results = _sample_results()
    csv_bytes = generate_csv_bytes(results)
    df = pd.read_csv(io.BytesIO(csv_bytes))
    assert list(df.columns) == EXPORT_COLUMNS
    assert len(df) == 3
    assert df.iloc[0]["Control ID"] == "NS-02"
    assert df.iloc[0]["Status"] == "Partially Compliant"
    assert df.iloc[0]["Source Page"] == 1
    assert df.iloc[1]["Status"] == "Not Found"
    assert df.iloc[2]["Status"] == "Non-Compliant"


def test_csv_and_excel_schemas_are_consistent():
    results = _sample_results()
    csv_df = pd.read_csv(io.BytesIO(generate_csv_bytes(results)))
    xlsx = generate_excel_bytes(results)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx), data_only=True)
    ws = wb["Audit_Trail"]
    header = [c.value for c in ws[1]]
    assert header == EXPORT_COLUMNS
    assert list(csv_df.columns) == header
    assert ws.max_row - 1 == len(csv_df)


def test_excel_has_summary_sheet_with_per_status_counts():
    results = _sample_results()
    wb = openpyxl.load_workbook(io.BytesIO(generate_excel_bytes(results)), data_only=True)
    assert "Summary" in wb.sheetnames
    ws = wb["Summary"]
    rows = {r[0]: r[1] for r in ws.iter_rows(min_row=2, values_only=True) if r[0]}
    assert rows["Partially Compliant"] == 1
    assert rows["Not Found"] == 1
    assert rows["Non-Compliant"] == 1
    assert rows["Compliant"] == 0
    assert rows["Needs Review"] == 0


def test_excel_header_is_frozen_and_filtered():
    wb = openpyxl.load_workbook(io.BytesIO(generate_excel_bytes(_sample_results())))
    ws = wb["Audit_Trail"]
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref is not None


def test_excel_status_fills_differ_per_status():
    # Review states must not be coloured identically to non-compliant states.
    assert STATUS_FILL["Non-Compliant"]["bg_color"] != STATUS_FILL["Needs Review"]["bg_color"]
    assert STATUS_FILL["Non-Compliant"]["bg_color"] != STATUS_FILL["Conflicting Evidence"]["bg_color"]
    assert STATUS_FILL["Compliant"]["bg_color"] != STATUS_FILL["Partially Compliant"]["bg_color"]
    assert set(STATUS_FILL) == {s.value for s in EvidenceStatus}


def test_excel_multiple_passages_one_row_each():
    result = EvidenceResult(
        filename="policy.pdf",
        control_id="NS-07",
        control_name="Audit log retention",
        requirement="Retention is defined",
        status=EvidenceStatus.CONFLICTING_EVIDENCE,
        requirement_coverage=Coverage.UNKNOWN,
        evidence=[
            EvidencePassage(quote="Audit logs are retained for 90 days.", source_document="policy.pdf", page=3, evidence_type=EvidenceType.POLICY),
            EvidencePassage(quote="Audit logs are retained for one year.", source_document="policy.pdf", page=4, evidence_type=EvidenceType.POLICY),
        ],
        conflicts=["Page 3 says 90 days; page 4 says one year."],
        reasoning="Contradictory retention periods.",
        review_required=True,
    )
    df = results_to_dataframe([result])
    assert len(df) == 2
    assert df.iloc[0]["Source Page"] == 3
    assert df.iloc[1]["Source Page"] == 4
    assert df.iloc[0]["Conflicts"] == df.iloc[1]["Conflicts"]


def test_excel_rejects_invalid_input():
    with pytest.raises(ValueError):
        generate_excel_bytes(12345)


def test_csv_reviewer_decision_round_trips():
    result = _sample_results()[0]
    result.reviewer_decision = "Partially Compliant"
    result.reviewer_comments = "Confirmed by reviewer."
    df = pd.read_csv(io.BytesIO(generate_csv_bytes([result])))
    assert df.iloc[0]["Reviewer Decision"] == "Partially Compliant"
    assert df.iloc[0]["Reviewer Comments"] == "Confirmed by reviewer."
