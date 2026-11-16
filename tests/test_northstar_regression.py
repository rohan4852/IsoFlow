"""30-control Northstar regression suite.

Uses the NEW documented synthetic fixture in tests/fixtures/ — the
original Northstar test policy and control matrix were NOT in the repo,
so this suite does NOT claim to reproduce the original evaluation.

Each control is run through the real pipeline with a deterministic
mocked Stage A response: strict JSON parsing -> strict validation
(including deterministic quotation verification) -> deterministic
Stage B adjudication.  No live Gemini call is made.

For every control the suite asserts: a result exists, the ID matches,
the status is one of the seven valid statuses and equals the expected
proposed label, every quotation exists verbatim in the original source
pages with the correct source page, reasoning is present, missing
evidence is identified where the label requires it, conflicts and
exceptions are retained, and no invalid result is presented as
Compliant.
"""

import pytest

from audit_engine import analyse_control, analyse_controls
from conftest import FakeModel
from evidence_model import EvidenceStatus, verify_quote
from fixtures.northstar_fixture import (
    CONTROLS,
    DOC_NAME,
    EXPECTED,
    MOCK_PAYLOADS,
    POLICY_PAGES,
)

CONTROL_MAP = {cid: (name, req) for cid, name, req in CONTROLS}


@pytest.fixture(scope="module")
def results():
    model = FakeModel(MOCK_PAYLOADS)
    controls = [(cid, name, req) for cid, name, req in CONTROLS]
    return {
        r.control_id: r
        for r in analyse_controls(model, [(DOC_NAME, POLICY_PAGES)], controls, max_workers=4)
    }


def test_all_30_controls_produce_results(results):
    assert len(results) == 30
    assert set(results) == set(EXPECTED)


@pytest.mark.parametrize("control_id", [cid for cid, _, _ in CONTROLS])
def test_expected_status(control_id, results):
    result = results[control_id]
    assert result.control_id == control_id
    assert result.status.value in {s.value for s in EvidenceStatus}
    assert result.status.value == EXPECTED[control_id], (
        f"{control_id}: expected {EXPECTED[control_id]}, got {result.status.value} "
        f"(reasoning: {result.reasoning})"
    )


@pytest.mark.parametrize("control_id", [cid for cid, _, _ in CONTROLS])
def test_result_invariants(control_id, results):
    result = results[control_id]
    # Reasoning is always present.
    assert result.reasoning.strip(), f"{control_id}: reasoning missing"
    # Every quotation exists verbatim in the original source, with the
    # correct source page.
    for passage in result.evidence:
        found = verify_quote(passage.quote, POLICY_PAGES)
        assert found is not None, f"{control_id}: unverified quote {passage.quote!r}"
        assert found == (passage.source_document, passage.page), (
            f"{control_id}: quote source mismatch — expected {found}, "
            f"got {(passage.source_document, passage.page)}"
        )
    # No invalid result is presented as Compliant.
    if result.status == EvidenceStatus.COMPLIANT:
        assert result.evidence, f"{control_id}: Compliant with no evidence"
        assert result.requirement_coverage.value == "Full"


@pytest.mark.parametrize("control_id", ["NS-14", "NS-21", "NS-25", "NS-30"])
def test_not_found_controls_identify_missing_evidence(control_id, results):
    result = results[control_id]
    assert result.status == EvidenceStatus.NOT_FOUND
    assert result.missing_elements, f"{control_id}: missing evidence not identified"


@pytest.mark.parametrize("control_id", ["NS-07", "NS-15", "NS-26"])
def test_conflicting_controls_retain_conflicts(control_id, results):
    result = results[control_id]
    assert result.status == EvidenceStatus.CONFLICTING_EVIDENCE
    assert result.conflicts, f"{control_id}: conflicts not retained"
    assert len(result.evidence) >= 2, f"{control_id}: conflicting passages not retained"
    assert result.review_required is True


def test_ns13_non_compliant_requires_overdue_violation(results):
    result = results["NS-13"]
    assert result.status == EvidenceStatus.NON_COMPLIANT
    assert result.stale_is_violation is True
    assert not result.exceptions, "NS-13 must have no valid approved exception"
    assert "F-22" in result.reasoning


def test_ns21_policy_text_alone_is_not_operational_proof(results):
    result = results["NS-21"]
    assert result.status == EvidenceStatus.NOT_FOUND
    assert result.evidence, "NS-21 should retain the policy passage as retrieved evidence"
    assert all(p.evidence_type.value == "Policy" for p in result.evidence)
    assert "policy" in result.reasoning.lower()


def test_ns30_policy_text_alone_is_not_operational_proof(results):
    result = results["NS-30"]
    assert result.status == EvidenceStatus.NOT_FOUND
    assert all(p.evidence_type.value == "Policy" for p in result.evidence)


@pytest.mark.parametrize(
    "control_id",
    ["NS-02", "NS-03", "NS-06", "NS-08", "NS-09", "NS-10", "NS-11", "NS-12",
     "NS-16", "NS-17", "NS-18", "NS-19", "NS-22", "NS-23", "NS-27"],
)
def test_partial_controls_have_uncovered_scope(control_id, results):
    result = results[control_id]
    assert result.status == EvidenceStatus.PARTIALLY_COMPLIANT
    assert result.uncovered_scope or result.missing_elements, (
        f"{control_id}: partial result must name what is uncovered or missing"
    )


@pytest.mark.parametrize(
    "control_id", ["NS-01", "NS-04", "NS-05", "NS-20", "NS-24", "NS-28", "NS-29"]
)
def test_needs_review_controls_require_human_review(control_id, results):
    result = results[control_id]
    assert result.status == EvidenceStatus.NEEDS_REVIEW
    assert result.review_required is True


def test_single_control_path_matches_batch_path():
    """analyse_control (single) and analyse_controls (batch) agree."""
    model = FakeModel(MOCK_PAYLOADS)
    name, req = CONTROL_MAP["NS-13"]
    single = analyse_control(model, POLICY_PAGES, "NS-13", name, req, DOC_NAME)
    assert single.status == EvidenceStatus.NON_COMPLIANT
    assert single.status.value == EXPECTED["NS-13"]
