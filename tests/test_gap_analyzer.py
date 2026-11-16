"""Unit tests: gap analyzer (batch processing, citation verification, summary)."""

from types import SimpleNamespace

import pytest

import gap_analyzer
from conftest import FakeModel, FakeModelText
from fixtures.northstar_fixture import (
    CONTROLS,
    DOC_NAME,
    MOCK_PAYLOADS,
    POLICY_PAGES,
)


def _gap_payload(control_id):
    """Convert a main-audit mock payload to the gap-analyzer batch shape."""
    payload = dict(MOCK_PAYLOADS[control_id])
    payload["id"] = payload.pop("control_id")
    return payload


def _framework_controls(ids):
    controls = []
    for cid, name, req in CONTROLS:
        if cid in ids:
            controls.append(SimpleNamespace(
                id=cid, name=name, category="Test", section="Test", requirement=req,
            ))
    return controls


def test_evaluate_batch_verifies_citations_and_adjudicates(monkeypatch):
    monkeypatch.setattr(gap_analyzer.time, "sleep", lambda *_: None)
    model = FakeModel({cid: _gap_payload(cid) for cid in ["NS-02", "NS-07", "NS-14"]})
    controls = _framework_controls(["NS-02", "NS-07", "NS-14"])
    document_text = "\n\n".join(f"[Page {p.page}]\n{p.text}" for p in POLICY_PAGES)
    results = gap_analyzer.evaluate_batch(model, document_text, controls, pages=POLICY_PAGES, filename=DOC_NAME)
    by_id = {r.id: r for r in results}
    assert by_id["NS-02"].status == "Partially Compliant"
    assert by_id["NS-07"].status == "Conflicting Evidence"
    assert by_id["NS-14"].status == "Not Found"
    # Citations must point at real pages.
    assert "p. 1" in by_id["NS-02"].evidenceCitation
    assert "p. 3" in by_id["NS-07"].evidenceCitation or "p. 4" in by_id["NS-07"].evidenceCitation


def test_evaluate_batch_drops_fabricated_quotation(monkeypatch):
    monkeypatch.setattr(gap_analyzer.time, "sleep", lambda *_: None)
    bad = _gap_payload("NS-02")
    bad["evidence"] = [
        {"quote": "Every user must carry a hardware token.", "source_document": DOC_NAME, "page": 1, "evidence_type": "Policy"},
        {"quote": "Multi-factor authentication is required for administrators.", "source_document": DOC_NAME, "page": 1, "evidence_type": "Policy"},
    ]
    bad["status"] = "Compliant"
    bad["requirement_coverage"] = "Full"
    model = FakeModel({"NS-02": bad})
    controls = _framework_controls(["NS-02"])
    document_text = "\n\n".join(f"[Page {p.page}]\n{p.text}" for p in POLICY_PAGES)
    results = gap_analyzer.evaluate_batch(model, document_text, controls, pages=POLICY_PAGES, filename=DOC_NAME)
    assert len(results[0].evidence) == 1
    assert results[0].status != "Compliant"


def test_evaluate_batch_malformed_json_raises_after_retry(monkeypatch):
    # evaluate_batch raises after its one corrective retry; run_gap_analysis
    # converts that failure into per-control Analysis Error results.
    monkeypatch.setattr(gap_analyzer.time, "sleep", lambda *_: None)
    model = FakeModelText('[{"id": "NS-02", "status": ')
    controls = _framework_controls(["NS-02"])
    document_text = "\n\n".join(f"[Page {p.page}]\n{p.text}" for p in POLICY_PAGES)
    with pytest.raises(RuntimeError, match="Batch response invalid"):
        gap_analyzer.evaluate_batch(model, document_text, controls, pages=POLICY_PAGES, filename=DOC_NAME)


def test_run_gap_analysis_batch_failure_becomes_analysis_error(monkeypatch):
    monkeypatch.setattr(gap_analyzer.time, "sleep", lambda *_: None)
    model = FakeModelText('[{"id": "NS-02", "status": ')
    controls = _framework_controls(["NS-02"])
    combined = "\n\n".join(p.text for p in POLICY_PAGES)
    results = gap_analyzer.run_gap_analysis(combined, model, controls, pages=POLICY_PAGES, filename=DOC_NAME)
    assert len(results) == 1
    assert results[0].status == "Analysis Error"
    assert results[0].analysis_error


def test_run_gap_analysis_full_framework_with_patched_sleep(monkeypatch):
    monkeypatch.setattr(gap_analyzer.time, "sleep", lambda *_: None)
    model = FakeModel({cid: _gap_payload(cid) for cid, _, _ in CONTROLS})
    controls = _framework_controls([cid for cid, _, _ in CONTROLS])
    combined = "\n\n".join(p.text for p in POLICY_PAGES)
    results = gap_analyzer.run_gap_analysis(combined, model, controls, pages=POLICY_PAGES, filename=DOC_NAME)
    assert len(results) == 30
    assert [r.id for r in results] == [cid for cid, _, _ in CONTROLS]
    by_id = {r.id: r for r in results}
    assert by_id["NS-13"].status == "Non-Compliant"
    assert by_id["NS-21"].status == "Not Found"
    assert by_id["NS-26"].status == "Conflicting Evidence"


def test_compute_analysis_summary_excludes_errors_from_compliance():
    results = [
        SimpleNamespace(status="Compliant"),
        SimpleNamespace(status="Partially Compliant"),
        SimpleNamespace(status="Analysis Error"),
        SimpleNamespace(status="Analysis Error"),
    ]
    # compute_analysis_summary expects AnalysisResult-like objects with
    # category/section attributes too.
    for r in results:
        r.category = "Test"
        r.section = "Test"
    summary = gap_analyzer.compute_analysis_summary(results)
    assert summary["total_controls"] == 4
    assert summary["compliant_count"] == 1
    assert summary["error_count"] == 2
    # Compliance % over successfully evaluated controls only: 1 of 2.
    assert summary["compliance_percentage"] == 50.0


def test_export_results_to_dict_uses_21_column_schema(monkeypatch):
    monkeypatch.setattr(gap_analyzer.time, "sleep", lambda *_: None)
    model = FakeModel({cid: _gap_payload(cid) for cid in ["NS-02"]})
    controls = _framework_controls(["NS-02"])
    document_text = "\n\n".join(f"[Page {p.page}]\n{p.text}" for p in POLICY_PAGES)
    results = gap_analyzer.evaluate_batch(model, document_text, controls, pages=POLICY_PAGES, filename=DOC_NAME)
    rows = gap_analyzer.export_results_to_dict(results)
    assert len(rows) == 1
    assert len(rows[0]) == 21
    assert rows[0]["Control ID"] == "NS-02"
    assert rows[0]["Status"] == "Partially Compliant"
    assert rows[0]["Source Page"] == 1
