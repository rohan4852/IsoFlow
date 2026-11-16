"""Unit tests: evidence model, schema validation, quotation verification."""

import pytest

from evidence_model import (
    Coverage,
    EvidencePassage,
    EvidenceResult,
    EvidenceStatus,
    EvidenceType,
    PageText,
    ValidationError,
    result_to_export_rows,
    validate_model_result,
    verify_quote,
)

PAGES = [
    PageText(filename="policy.pdf", page=1, text="Access reviews are performed periodically for all privileged accounts.", document_id="policy.pdf"),
    PageText(filename="policy.pdf", page=2, text="Multi-factor authentication is required for administrators.", document_id="policy.pdf"),
    PageText(filename="records.pdf", page=1, text="Training completion for Q3 2026 was 82% of staff.", document_id="records.pdf"),
]


def test_verify_quote_exact_match():
    found = verify_quote("Multi-factor authentication is required for administrators.", PAGES)
    assert found == ("policy.pdf", 2)


def test_verify_quote_normalises_whitespace():
    found = verify_quote("Multi-factor   authentication\nis required for administrators.", PAGES)
    assert found == ("policy.pdf", 2)


def test_verify_quote_fabricated_returns_none():
    assert verify_quote("All users must use hardware security keys.", PAGES) is None


def test_verify_quote_paraphrase_is_not_a_quote():
    assert verify_quote("MFA is required for admins.", PAGES) is None


def test_verify_quote_searches_all_documents():
    found = verify_quote("Training completion for Q3 2026 was 82% of staff.", PAGES)
    assert found == ("records.pdf", 1)


def test_verify_quote_empty_returns_none():
    assert verify_quote("   ", PAGES) is None


def test_evidence_result_requires_filename_and_control_id():
    with pytest.raises(ValidationError):
        EvidenceResult(filename="", control_id="A.1")
    with pytest.raises(ValidationError):
        EvidenceResult(filename="x.pdf", control_id="")


def test_evidence_result_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        EvidenceResult(filename="x.pdf", control_id="A.1", confidence=1.5)
    with pytest.raises(ValidationError):
        EvidenceResult(filename="x.pdf", control_id="A.1", confidence="high")


def test_analysis_error_requires_error_text():
    with pytest.raises(ValidationError):
        EvidenceResult(filename="x.pdf", control_id="A.1", status=EvidenceStatus.ANALYSIS_ERROR)


def test_status_coercion_rejects_unknown():
    with pytest.raises(ValidationError):
        EvidenceResult(filename="x.pdf", control_id="A.1", status="Mostly Fine")


def test_validate_rejects_wrong_control_id():
    payload = {
        "control_id": "NS-02",
        "status": "Compliant",
        "requirement_coverage": "Full",
        "evidence": [],
        "reasoning": "x",
    }
    with pytest.raises(ValidationError, match="mismatch"):
        validate_model_result(payload, "NS-01", PAGES, "policy.pdf")


def test_validate_rejects_non_object():
    with pytest.raises(ValidationError):
        validate_model_result(["not", "an", "object"], "NS-01", PAGES, "policy.pdf")


def test_validate_rejects_unknown_status():
    payload = {"control_id": "NS-01", "status": "Kinda Compliant", "evidence": []}
    with pytest.raises(ValidationError):
        validate_model_result(payload, "NS-01", PAGES, "policy.pdf")


def test_validate_drops_unverified_quote_and_downgrades_compliant():
    payload = {
        "control_id": "NS-01",
        "status": "Compliant",
        "requirement_coverage": "Full",
        "evidence": [
            {"quote": "All users must use hardware security keys.", "source_document": "policy.pdf", "page": 1, "evidence_type": "Policy"},
            {"quote": "Access reviews are performed periodically for all privileged accounts.", "source_document": "policy.pdf", "page": 1, "evidence_type": "Policy"},
        ],
        "reasoning": "Found evidence.",
    }
    result = validate_model_result(payload, "NS-01", PAGES, "policy.pdf")
    assert result.status == EvidenceStatus.NEEDS_REVIEW
    assert len(result.evidence) == 1
    assert result.review_required is True
    assert any("could not be verified" in m for m in result.missing_elements)


def test_validate_corrects_wrong_page_reference():
    payload = {
        "control_id": "NS-01",
        "status": "Partially Compliant",
        "requirement_coverage": "Partial",
        "evidence": [
            {"quote": "Multi-factor authentication is required for administrators.", "source_document": "policy.pdf", "page": 1, "evidence_type": "Policy"},
        ],
        "reasoning": "Partial.",
    }
    result = validate_model_result(payload, "NS-01", PAGES, "policy.pdf")
    assert result.evidence[0].page == 2  # corrected to the verified page


def test_validate_downgrades_compliant_with_only_fabricated_evidence():
    # A Compliant claim whose only quotation is fabricated is downgraded
    # to Needs Review (per the mandate: mark affected results Needs
    # Review or Analysis Error), never silently accepted as Compliant.
    payload = {
        "control_id": "NS-01",
        "status": "Compliant",
        "requirement_coverage": "Full",
        "evidence": [
            {"quote": "Invented quotation here.", "source_document": "policy.pdf", "page": 1, "evidence_type": "Policy"},
        ],
        "reasoning": "No real evidence.",
    }
    result = validate_model_result(payload, "NS-01", PAGES, "policy.pdf")
    assert result.status == EvidenceStatus.NEEDS_REVIEW
    assert result.evidence == []
    assert result.review_required is True


def test_validate_rejects_compliant_with_no_evidence_field():
    # A Compliant payload that supplies no evidence at all is rejected
    # outright (the model must not claim compliance with nothing behind it).
    payload = {
        "control_id": "NS-01",
        "status": "Compliant",
        "requirement_coverage": "Full",
        "evidence": [],
        "reasoning": "No evidence supplied.",
    }
    with pytest.raises(ValidationError, match="Compliant result requires"):
        validate_model_result(payload, "NS-01", PAGES, "policy.pdf")


def test_validate_rejects_invalid_page_reference():
    payload = {
        "control_id": "NS-01",
        "status": "Partially Compliant",
        "requirement_coverage": "Partial",
        "evidence": [
            {"quote": "Access reviews are performed periodically for all privileged accounts.", "source_document": "policy.pdf", "page": 0, "evidence_type": "Policy"},
        ],
        "reasoning": "x",
    }
    with pytest.raises(ValidationError):
        validate_model_result(payload, "NS-01", PAGES, "policy.pdf")


def test_result_to_export_rows_one_row_per_passage():
    result = EvidenceResult(
        filename="policy.pdf",
        control_id="NS-01",
        control_name="Access reviews",
        requirement="Reviews happen.",
        status=EvidenceStatus.PARTIALLY_COMPLIANT,
        requirement_coverage=Coverage.PARTIAL,
        evidence=[
            EvidencePassage(quote="Access reviews are performed periodically for all privileged accounts.", source_document="policy.pdf", page=1, evidence_type=EvidenceType.POLICY),
            EvidencePassage(quote="Multi-factor authentication is required for administrators.", source_document="policy.pdf", page=2, evidence_type=EvidenceType.POLICY),
        ],
        reasoning="Partial coverage.",
    )
    rows = result_to_export_rows(result)
    assert len(rows) == 2
    assert len(rows[0]) == 21
    assert rows[0]["Evidence Quotation"].startswith("Access reviews")
    assert rows[1]["Evidence Quotation"].startswith("Multi-factor")
    assert rows[0]["Status"] == "Partially Compliant"
    assert rows[0]["Source Page"] == 1
    assert rows[1]["Source Page"] == 2


def test_result_to_export_rows_no_evidence_still_one_row():
    result = EvidenceResult(
        filename="policy.pdf",
        control_id="NS-14",
        status=EvidenceStatus.NOT_FOUND,
        requirement_coverage=Coverage.NONE,
        reasoning="Nothing found.",
    )
    rows = result_to_export_rows(result)
    assert len(rows) == 1
    assert rows[0]["Evidence Quotation"] == ""
    assert rows[0]["Status"] == "Not Found"


def test_result_json_round_trip():
    result = EvidenceResult(
        filename="policy.pdf",
        control_id="NS-01",
        status=EvidenceStatus.NEEDS_REVIEW,
        requirement_coverage=Coverage.UNKNOWN,
        reasoning="Ambiguous.",
    )
    restored = EvidenceResult.from_dict(result.to_dict())
    assert restored.control_id == result.control_id
    assert restored.status == result.status
    assert restored.requirement_coverage == result.requirement_coverage
