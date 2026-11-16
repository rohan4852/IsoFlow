"""Unit tests: two-stage audit engine (strict parsing, error handling)."""

import json

import pytest

from audit_engine import (
    analyse_control,
    analyse_controls,
    ask_with_backoff,
    build_audit_prompt,
    parse_model_response_strict,
)
from conftest import FakeModel, FakeModelText
from evidence_model import EvidenceStatus, ValidationError
from fixtures.northstar_fixture import (
    CONTROLS,
    DOC_NAME,
    MOCK_PAYLOADS,
    POLICY_PAGES,
)

CONTROL_MAP = {cid: (name, req) for cid, name, req in CONTROLS}


def test_parse_strict_accepts_plain_json():
    payload = {"control_id": "NS-01", "status": "Needs Review"}
    assert parse_model_response_strict(json.dumps(payload)) == payload


def test_parse_strict_strips_code_fences():
    payload = {"control_id": "NS-01", "status": "Needs Review"}
    text = "```json\n" + json.dumps(payload) + "\n```"
    assert parse_model_response_strict(text) == payload


def test_parse_strict_rejects_malformed_json():
    with pytest.raises(ValidationError):
        parse_model_response_strict('{"control_id": "NS-01", "status": ')


def test_parse_strict_rejects_non_object_json():
    with pytest.raises(ValidationError):
        parse_model_response_strict('["NS-01", "Compliant"]')


def test_parse_strict_rejects_text_with_no_json():
    # No permissive regex fallback: prose around a JSON-like fragment
    # without a complete object must fail, not be repaired.
    with pytest.raises(ValidationError):
        parse_model_response_strict("The control is Compliant because the policy says so.")


def test_parse_strict_rejects_empty_text():
    with pytest.raises(ValidationError):
        parse_model_response_strict("")


def test_build_audit_prompt_contains_rules():
    prompt = build_audit_prompt(
        "NS-07", "Audit log retention", "Retention is defined",
        "[Page 3]\nAudit logs are retained for 90 days.",
    )
    assert "NS-07" in prompt
    assert "Conflicting" in prompt
    assert "favourable" in prompt.lower() or "favorable" in prompt.lower()
    assert "Do not paraphrase" in prompt


def test_analyse_control_partial():
    model = FakeModel(MOCK_PAYLOADS)
    name, req = CONTROL_MAP["NS-02"]
    result = analyse_control(model, POLICY_PAGES, "NS-02", name, req, DOC_NAME)
    assert result.control_id == "NS-02"
    assert result.status == EvidenceStatus.PARTIALLY_COMPLIANT
    assert result.evidence
    from evidence_model import verify_quote

    assert all(verify_quote(p.quote, POLICY_PAGES) is not None for p in result.evidence)
    assert result.reasoning


def test_analyse_control_conflict_retained():
    model = FakeModel(MOCK_PAYLOADS)
    name, req = CONTROL_MAP["NS-07"]
    result = analyse_control(model, POLICY_PAGES, "NS-07", name, req, DOC_NAME)
    assert result.status == EvidenceStatus.CONFLICTING_EVIDENCE
    assert result.conflicts
    assert len(result.evidence) == 2


def test_analyse_control_stale_violation_is_non_compliant():
    model = FakeModel(MOCK_PAYLOADS)
    name, req = CONTROL_MAP["NS-13"]
    result = analyse_control(model, POLICY_PAGES, "NS-13", name, req, DOC_NAME)
    assert result.status == EvidenceStatus.NON_COMPLIANT


def test_analyse_control_policy_only_operational_is_not_found():
    model = FakeModel(MOCK_PAYLOADS)
    name, req = CONTROL_MAP["NS-21"]
    result = analyse_control(model, POLICY_PAGES, "NS-21", name, req, DOC_NAME)
    assert result.status == EvidenceStatus.NOT_FOUND


def test_analyse_control_malformed_response_is_analysis_error():
    model = FakeModelText('{"control_id": "NS-01", "status": ')
    name, req = CONTROL_MAP["NS-01"]
    result = analyse_control(model, POLICY_PAGES, "NS-01", name, req, DOC_NAME)
    assert result.status == EvidenceStatus.ANALYSIS_ERROR
    assert result.analysis_error


def test_analyse_control_wrong_control_id_is_analysis_error():
    model = FakeModelText(json.dumps({
        "control_id": "NS-99", "status": "Compliant",
        "requirement_coverage": "Full", "evidence": [], "reasoning": "x",
    }))
    name, req = CONTROL_MAP["NS-01"]
    result = analyse_control(model, POLICY_PAGES, "NS-01", name, req, DOC_NAME)
    assert result.status == EvidenceStatus.ANALYSIS_ERROR


def test_analyse_control_api_failure_is_analysis_error_not_finding():
    model = FakeModel(MOCK_PAYLOADS, fail_on={"NS-01"})
    name, req = CONTROL_MAP["NS-01"]
    result = analyse_control(model, POLICY_PAGES, "NS-01", name, req, DOC_NAME)
    assert result.status == EvidenceStatus.ANALYSIS_ERROR
    assert result.analysis_error


def test_ask_with_backoff_retries_rate_limit_once_then_succeeds():
    model = FakeModel(MOCK_PAYLOADS, rate_limit_on_first=True)
    response = ask_with_backoff(model, "CONTROL: NS-02 — test")
    assert json.loads(response.text)["control_id"] == "NS-02"
    assert model.calls == 2


def test_ask_with_backoff_does_not_retry_other_errors():
    model = FakeModel(MOCK_PAYLOADS, fail_on={"NS-02"})
    with pytest.raises(RuntimeError):
        ask_with_backoff(model, "CONTROL: NS-02 — test")
    assert model.calls == 1


def test_analyse_controls_stable_order_and_all_controls():
    model = FakeModel(MOCK_PAYLOADS)
    controls = [(cid, name, req) for cid, name, req in CONTROLS[:5]]
    results = analyse_controls(model, [(DOC_NAME, POLICY_PAGES)], controls, max_workers=2)
    assert [r.control_id for r in results] == [c[0] for c in controls]
    assert all(r.status in EvidenceStatus for r in results)
