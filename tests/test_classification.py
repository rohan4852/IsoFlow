"""Unit tests: Stage B deterministic adjudication."""

from datetime import date

from classification import (
    adjudicate,
    check_recency,
    detect_conflict_signals,
    error_result,
    extract_dates,
    extract_review_interval_days,
    infer_requirement_kind,
)
from evidence_model import (
    Coverage,
    EvidencePassage,
    EvidenceResult,
    EvidenceStatus,
    EvidenceType,
)


def _result(status="Partially Compliant", coverage=Coverage.PARTIAL, evidence=None, **kw):
    return EvidenceResult(
        filename="policy.pdf",
        control_id="NS-01",
        control_name="Test control",
        requirement=kw.pop("requirement", "Access reviews are performed for all privileged accounts"),
        status=status,
        requirement_coverage=coverage,
        evidence=evidence or [],
        **kw,
    )


def _passage(quote, page=1, evidence_type=EvidenceType.POLICY, doc="policy.pdf"):
    return EvidencePassage(quote=quote, source_document=doc, page=page, evidence_type=evidence_type)


def test_adjudicate_no_evidence_is_not_found_not_non_compliant():
    result = _result(status="Non-Compliant", coverage=Coverage.FULL, evidence=[])
    out = adjudicate(result)
    assert out.status == EvidenceStatus.NOT_FOUND
    assert out.requirement_coverage == Coverage.NONE
    assert out.missing_elements


def test_adjudicate_conflicts_beat_partial_coverage():
    result = _result(
        status="Partially Compliant",
        coverage=Coverage.PARTIAL,
        evidence=[_passage("Audit logs are retained for 90 days.", 3)],
        conflicts=["Page 3 says 90 days; page 4 says one year."],
    )
    out = adjudicate(result)
    assert out.status == EvidenceStatus.CONFLICTING_EVIDENCE
    assert out.review_required is True


def test_adjudicate_partial_coverage():
    result = _result(
        coverage=Coverage.PARTIAL,
        requirement="Multi-factor authentication is required for all users",
        evidence=[_passage("MFA is required for administrators.", 1)],
        uncovered_scope=["Non-admin users"],
    )
    out = adjudicate(result)
    assert out.status == EvidenceStatus.PARTIALLY_COMPLIANT


def test_adjudicate_policy_only_for_operational_requirement_is_not_found():
    result = _result(
        status="Needs Review",
        coverage=Coverage.UNKNOWN,
        requirement="Database backups must be restore-tested quarterly",
        evidence=[_passage("Database backups are performed daily.", 6)],
    )
    out = adjudicate(result)
    assert out.status == EvidenceStatus.NOT_FOUND
    assert "policy" in out.reasoning.lower() or "Policy" in out.reasoning


def test_adjudicate_operational_evidence_blocks_policy_only_rule():
    result = _result(
        status="Partially Compliant",
        coverage=Coverage.PARTIAL,
        requirement="Security patches are applied to all servers within 14 days of release",
        evidence=[
            _passage("Patching is applied to all servers within 14 days of release.", 2),
            _passage("Patching completed for 14 of 20 servers within 14 days; 6 servers patched late.", 2, EvidenceType.OPERATIONAL_RECORD),
        ],
        uncovered_scope=["6 servers patched late"],
    )
    out = adjudicate(result)
    assert out.status == EvidenceStatus.PARTIALLY_COMPLIANT


def test_adjudicate_stale_violation_is_non_compliant():
    result = _result(
        status="Partially Compliant",
        coverage=Coverage.PARTIAL,
        requirement="High findings are remediated within 30 days of identification",
        evidence=[
            _passage("Remediation of high findings is required within 30 days of identification.", 4),
            _passage("Finding F-22, identified 2026-01-15, remains open as of 2026-11-01 with no approved exception.", 4, EvidenceType.OPERATIONAL_RECORD),
        ],
    )
    out = adjudicate(result, stale_is_violation=True)
    assert out.status == EvidenceStatus.NON_COMPLIANT
    assert out.review_required is True


def test_adjudicate_stale_without_violation_flag_is_not_non_compliant():
    # An overdue review date alone is not a violation.
    result = _result(
        status="Partially Compliant",
        coverage=Coverage.PARTIAL,
        requirement="Incident response plan is reviewed annually",
        evidence=[
            _passage("Incident response plan is reviewed annually.", 3),
            _passage("Last review of the incident response plan was 2024-03-01.", 3, EvidenceType.OPERATIONAL_RECORD),
        ],
    )
    out = adjudicate(result, stale_is_violation=False)
    assert out.status == EvidenceStatus.PARTIALLY_COMPLIANT


def test_adjudicate_unknown_coverage_preserves_uncertainty():
    result = _result(
        status="Needs Review",
        coverage=Coverage.UNKNOWN,
        requirement="An access review policy defines scope and frequency for privileged accounts",
        evidence=[_passage("Access reviews are performed periodically for all privileged accounts.", 1)],
        missing_elements=["Review frequency is not stated."],
    )
    out = adjudicate(result)
    assert out.status == EvidenceStatus.NEEDS_REVIEW
    assert out.review_required is True


def test_adjudicate_full_coverage_with_verified_evidence_is_compliant():
    result = _result(
        status="Compliant",
        coverage=Coverage.FULL,
        requirement="An access review policy is documented",
        evidence=[_passage("Access reviews are performed periodically for all privileged accounts.", 1)],
    )
    out = adjudicate(result)
    assert out.status == EvidenceStatus.COMPLIANT


def test_adjudicate_analysis_error_is_terminal():
    result = error_result("policy.pdf", "NS-01", error="Model response failed validation")
    out = adjudicate(result)
    assert out.status == EvidenceStatus.ANALYSIS_ERROR
    assert out.review_required is True


def test_adjudicate_exception_does_not_auto_approve():
    # An exception described without approval details must not flip a
    # partial result to Compliant.
    result = _result(
        status="Partially Compliant",
        coverage=Coverage.PARTIAL,
        requirement="Multi-factor authentication is required for all users",
        evidence=[_passage("MFA is required for administrators.", 1)],
        uncovered_scope=["Non-admin users"],
        exceptions=["Exception process exists for MFA."],
    )
    out = adjudicate(result)
    assert out.status == EvidenceStatus.PARTIALLY_COMPLIANT


def test_infer_requirement_kind_operational_vs_documentary():
    assert infer_requirement_kind("Database backups must be restore-tested quarterly") == "operational"
    assert infer_requirement_kind("An access review policy defines scope and frequency") == "documentary"
    assert infer_requirement_kind("High findings are remediated within 30 days") == "operational"


def test_extract_dates_finds_iso_dates():
    dates = extract_dates("Finding F-22, identified 2026-01-15, remains open as of 2026-11-01.")
    assert date(2026, 1, 15) in dates
    assert date(2026, 11, 1) in dates


def test_extract_review_interval_never_invented():
    assert extract_review_interval_days("Reviews are performed periodically.") is None
    assert extract_review_interval_days("The plan is reviewed annually.") == 365
    assert extract_review_interval_days("Access is reviewed every 90 days.") == 90


def test_check_recency_overdue_and_missing_interval():
    finding = check_recency(
        ["Last review of the incident response plan was 2024-03-01."],
        requirement_text="Incident response plan is reviewed annually",
        reference_date=date(2026, 11, 16),
    )
    assert finding.is_overdue is True
    assert finding.interval_days == 365

    finding2 = check_recency(
        ["Reviews are performed periodically."],
        requirement_text="Reviews are performed periodically.",
        reference_date=date(2026, 11, 16),
    )
    assert finding2.interval_days is None
    assert finding2.is_overdue is False
    detail_lower = finding2.detail.lower()
    assert "no review interval" in detail_lower or "no evidence date" in detail_lower


def test_detect_conflict_signals_different_timeframes():
    signals = detect_conflict_signals([
        "Audit logs are retained for 90 days.",
        "Audit logs are retained for 30 days.",
    ])
    assert any("Different numeric timeframes" in s for s in signals)
    signals2 = detect_conflict_signals([
        "Access is revoked within 24 hours.",
    ])
    assert signals2 == []


def test_detect_conflict_signals_mandatory_vs_optional():
    signals = detect_conflict_signals([
        "Encryption is mandatory for all external services.",
        "Encryption is optional at the discretion of the team.",
    ])
    assert any("Mandatory-vs-optional" in s for s in signals)
