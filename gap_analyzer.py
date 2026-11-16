"""ISO 27001:2022 Gap Analysis Engine (evidence-classification-v2).

Batch-processing gap analysis for ISO 27001:2022 (Clauses 4-10 and Annex A
controls), migrated from the previous binary Compliant / Gap Detected model
to the unified seven-status model defined in ``evidence_model``:

    Compliant, Partially Compliant, Non-Compliant, Not Found,
    Conflicting Evidence, Needs Review, Analysis Error

Batch behaviour preserved from the previous implementation (quota control):

* Each LLM call evaluates exactly N controls in one JSON array response.
* Batches contain up to 10 controls; the final remainder is evaluated in
  a separate batch with N = remainder.
* Batches are processed sequentially with a 7-second pace to stay under
  the 10 RPM ceiling.
* Each batch response is strictly validated (exact keys, id order, array
  length) with one corrective retry.

What changed in this version:

* The model must return structured evidence (verbatim quotations with
  source document and page, coverage, scope, conflicts, exceptions,
  reasoning) for every control — not a single citation string.
* Every quotation is verified deterministically against the extracted
  source pages; unverified quotations are dropped, never repaired.
* Each result is adjudicated by the deterministic Stage B rules in
  ``classification`` (policy text alone is never proof of operation;
  partial coverage is Partially Compliant; material conflicts are
  Conflicting Evidence; uncertainty stays Needs Review).
* "Gap" in summaries now means any of Partially Compliant, Non-Compliant,
  Not Found, Conflicting Evidence or Needs Review.  The compliance
  percentage denominator still excludes Analysis Errors and is documented
  wherever it is shown — a percentage is never invented from an unknown
  denominator.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from classification import adjudicate, error_result, infer_requirement_kind
from evidence_model import (
    EvidencePassage,
    EvidenceResult,
    EvidenceStatus,
    PageText,
    ValidationError,
    validate_model_result,
)

__all__ = [
    "AnalysisResult",
    "GAP_STATUSES",
    "ask_with_backoff",
    "evaluate_batch",
    "run_gap_analysis",
    "compute_analysis_summary",
    "filter_results_by_status",
    "filter_results_by_section",
    "export_results_to_dict",
    "analysis_result_to_evidence_result",
]

# Statuses that count as a "gap" for summary purposes.
GAP_STATUSES = (
    EvidenceStatus.PARTIALLY_COMPLIANT,
    EvidenceStatus.NON_COMPLIANT,
    EvidenceStatus.NOT_FOUND,
    EvidenceStatus.CONFLICTING_EVIDENCE,
    EvidenceStatus.NEEDS_REVIEW,
)

_BATCH_ITEM_KEYS = {
    "id",
    "status",
    "requirement_coverage",
    "evidence",
    "covered_scope",
    "uncovered_scope",
    "missing_elements",
    "conflicts",
    "exceptions",
    "reasoning",
    "review_required",
    "stale_is_violation",
}


@dataclass
class AnalysisResult:
    """Result of analysing a single control against document text.

    ``evidenceCitation`` and ``gapComment`` are kept for backwards
    compatibility with the previous UI and exports; the structured fields
    below are the authoritative record.  ``gapComment`` now holds the
    reasoning / missing-elements text for gap statuses, and the
    ``analysis_error`` text for Analysis Error results.
    """

    id: str
    name: str
    category: str
    section: str
    requirement: str
    status: str  # one of the seven EvidenceStatus values
    evidenceCitation: str = ""
    gapComment: str = ""
    # Structured record (new in evidence-classification-v2).
    requirement_coverage: str = "Unknown"
    evidence: List[EvidencePassage] = field(default_factory=list)
    covered_scope: List[str] = field(default_factory=list)
    uncovered_scope: List[str] = field(default_factory=list)
    missing_elements: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    reasoning: str = ""
    review_required: bool = False
    analysis_error: str = ""
    filename: str = ""

    def to_evidence_result(self) -> EvidenceResult:
        """Convert to the shared structured result model."""
        return EvidenceResult(
            filename=self.filename or "document",
            control_id=self.id,
            control_name=self.name,
            requirement=self.requirement,
            status=EvidenceStatus.coerce(self.status),
            requirement_coverage=self.requirement_coverage,  # type: ignore[arg-type]
            evidence_type=sorted(
                {p.evidence_type for p in self.evidence},
                key=lambda t: t.value,
            ),
            evidence=list(self.evidence),
            covered_scope=list(self.covered_scope),
            uncovered_scope=list(self.uncovered_scope),
            missing_elements=list(self.missing_elements),
            conflicts=list(self.conflicts),
            exceptions=list(self.exceptions),
            reasoning=self.reasoning or self.gapComment,
            review_required=self.review_required,
            analysis_error=self.analysis_error or None,
        )


def analysis_result_to_evidence_result(result: AnalysisResult) -> EvidenceResult:
    return result.to_evidence_result()


def _system_prompt() -> str:
    return (
        "You are a strict ISO 27001:2022 Compliance Auditor performing gap analysis.\n\n"
        "CLASSIFICATION RULES (the seven statuses):\n"
        "- Compliant: sufficient relevant evidence supports the requirement for the evaluated scope.\n"
        "- Partially Compliant: some systems, populations or conditions are covered, others are missing.\n"
        "- Non-Compliant: the evidence shows the requirement is not met (only when the requirement and scope are established).\n"
        "- Not Found: no relevant supporting evidence was identified. Absence of evidence is NOT proof of non-compliance.\n"
        "- Conflicting Evidence: two or more passages contradict each other on requirements, dates, values or claims.\n"
        "- Needs Review: relevant evidence exists but a reliable conclusion needs human judgement or more evidence.\n"
        "- Analysis Error: the analysis could not be completed reliably.\n\n"
        "CRITICAL RULES:\n"
        "1) VERBATIM EXTRACTION ONLY: extract the EXACT, word-for-word text snippet from the provided document. Do NOT paraphrase, summarize, or interpret. Give the correct source document and 1-based page number for every quotation.\n"
        "2) SEARCH THE WHOLE DOCUMENT: retrieve favourable AND unfavourable passages, exceptions and exclusions, dates and scope. Do not stop after the first favourable passage.\n"
        "3) POLICY IS NOT PROOF OF OPERATION: a policy statement that something 'should' happen does not prove it happens. Operational requirements need operational evidence (records, configurations, third-party assurance).\n"
        "4) NO HALLUCINATION: do not invent quotations, dates, percentages or coverage. Never invent a coverage percentage without a known denominator.\n"
        "5) UNCERTAINTY: when the evidence does not support a definitive conclusion, use 'Needs Review'.\n\n"
        "OUTPUT RULES (mandatory):\n"
        "- Return ONLY valid JSON (no markdown, no backticks).\n"
        "- Return a single JSON array containing exactly N objects, where N equals the number of controls in this request.\n"
        "- Each object must match this schema EXACTLY (no extra keys, no nested objects beyond 'evidence'):\n"
        "  {\n"
        "    \"id\": \"Control ID string\",\n"
        "    \"status\": \"Compliant | Partially Compliant | Non-Compliant | Not Found | Conflicting Evidence | Needs Review | Analysis Error\",\n"
        "    \"requirement_coverage\": \"Full | Partial | None | Unknown\",\n"
        "    \"evidence\": [ {\"quote\": \"...\", \"source_document\": \"...\", \"page\": 1, \"evidence_type\": \"Policy | Procedure | Operational Record | Configuration Evidence | Exception Record | Third-Party Assurance | Unknown\"} ],\n"
        "    \"covered_scope\": [\"...\"],\n"
        "    \"uncovered_scope\": [\"...\"],\n"
        "    \"missing_elements\": [\"...\"],\n"
        "    \"conflicts\": [\"...\"],\n"
        "    \"exceptions\": [\"...\"],\n"
        "    \"reasoning\": \"...\",\n"
        "    \"review_required\": true or false,\n"
        "    \"stale_is_violation\": false\n"
        "  }\n"
        "- Set \"stale_is_violation\" to true ONLY when the evidence shows an\n"
        "  overdue finding that demonstrably violates the remediation\n"
        "  requirement and no valid approved exception exists.\n"
        "- Each object MUST correspond to the specific control requirement provided, matched by control 'id', in the same order as the controls were given.\n"
        "- If status is 'Compliant': 'evidence' MUST contain at least one verified quotation and 'requirement_coverage' MUST be 'Full'.\n"
        "- If status is 'Not Found': 'evidence' MUST be empty and 'missing_elements' MUST be non-empty.\n"
        "- If status is 'Conflicting Evidence': 'conflicts' MUST be non-empty.\n"
    )


def _batch_prompt(batch_controls: Sequence[Any], document_text: str) -> str:
    """Build one prompt that includes exactly N controls and requires one JSON array of exactly N objects."""

    n = len(batch_controls)

    controls_block_lines: List[str] = []
    for idx, c in enumerate(batch_controls, 1):
        controls_block_lines.append(
            "CONTROL {i}\n"
            "id: {id}\n"
            "name: {name}\n"
            "category: {category}\n"
            "section: {section}\n"
            "requirement: {requirement}\n".format(
                i=idx,
                id=getattr(c, "id"),
                name=getattr(c, "name"),
                category=getattr(c, "category"),
                section=getattr(c, "section"),
                requirement=getattr(c, "requirement"),
            )
        )

    controls_block = "\n".join(controls_block_lines)

    return (
        "BATCH CONTROLS (N controls)\n"
        f"N = {n}\n\n"
        "Here are the controls to evaluate:\n\n"
        f"{controls_block}\n\n"
        "DOCUMENT TEXT FOR ANALYSIS (page markers are [Page N — filename]):\n"
        f"{document_text}\n\n"
        "TASK:\n"
        "For EACH control in this batch, determine the status from the seven statuses above, using the evidence in the document text.\n"
        "Return the results as a SINGLE JSON array (only JSON) with exactly N objects, in the same order as the controls above.\n"
    )


def ask_with_backoff(model: Any, prompt: str, max_retries: int = 3) -> Optional[str]:
    """Gemini call with exponential backoff for 429 / quota style errors."""

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return getattr(response, "text", None)
        except Exception as e:
            error_str = str(e)
            is_rate_limit = (
                "429" in error_str
                or "ResourceExhausted" in error_str
                or "RESOURCE_EXHAUSTED" in error_str
                or "Too Many Requests" in error_str
            )
            if not is_rate_limit:
                raise

            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                time.sleep(wait_time)
                continue

            raise

    return None


def _strip_code_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```json"):
        s = s[len("```json") :].lstrip()
    elif s.startswith("```"):
        s = s[len("```") :].lstrip()

    if s.endswith("```"):
        s = s[: -len("```")].rstrip()
    return s.strip()


def _validate_batch_item(item: Any, index: int, expected_id: str) -> dict:
    """Strict structural validation of one batch item (no repair)."""
    if not isinstance(item, dict):
        raise ValidationError(f"Item {index} is not an object")
    item_keys = set(item.keys())
    if item_keys != _BATCH_ITEM_KEYS:
        raise ValidationError(
            f"Item {index} keys mismatch. Got {sorted(item_keys)} "
            f"expected {sorted(_BATCH_ITEM_KEYS)}"
        )
    got_id = str(item.get("id", "")).strip()
    if got_id != expected_id:
        raise ValidationError(
            f"Item {index} id mismatch. Got '{got_id}', expected '{expected_id}'"
        )
    EvidenceStatus.coerce(item.get("status"))
    evidence = item.get("evidence")
    if not isinstance(evidence, list):
        raise ValidationError(f"Item {index} 'evidence' must be a list")
    for key in ("covered_scope", "uncovered_scope", "missing_elements", "conflicts", "exceptions"):
        value = item.get(key)
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValidationError(f"Item {index} '{key}' must be a list of strings")
    if not isinstance(item.get("reasoning", ""), str):
        raise ValidationError(f"Item {index} 'reasoning' must be a string")
    if not isinstance(item.get("review_required", False), bool):
        raise ValidationError(f"Item {index} 'review_required' must be a boolean")
    if not isinstance(item.get("stale_is_violation", False), bool):
        raise ValidationError(f"Item {index} 'stale_is_violation' must be a boolean")
    status = str(item.get("status"))
    if status == "Compliant" and not evidence:
        raise ValidationError(f"Item {index} Compliant requires evidence")
    # NOTE: "Not Found" may legitimately carry retrieved evidence — e.g.
    # policy text that is insufficient proof for an operational requirement
    # (NS-21 / NS-30).  Absence of evidence is one route to Not Found, not
    # the only one, so no empty-evidence rule is enforced here.
    if status == "Conflicting Evidence" and not item.get("conflicts"):
        raise ValidationError(f"Item {index} Conflicting Evidence requires conflicts")
    return item


def _parse_batch_json_array(response_text: str, batch_controls: Sequence[Any]) -> List[dict]:
    cleaned = _strip_code_fences(response_text or "")
    if not cleaned:
        raise ValidationError("Empty response from model")

    data = json.loads(cleaned)

    if not isinstance(data, list):
        raise ValidationError("Model response is not a JSON array")

    n_expected = len(batch_controls)
    if len(data) != n_expected:
        raise ValidationError(
            f"JSON array length mismatch: got {len(data)}, expected {n_expected}"
        )

    return [
        _validate_batch_item(item, i, str(getattr(batch_controls[i], "id")))
        for i, item in enumerate(data)
    ]


def _pages_to_text(pages: Sequence[PageText], max_chars: int) -> str:
    """Render in-scope pages as prompt text, whole pages only, in order."""
    chunks: List[str] = []
    total = 0
    for page in pages:
        chunk = f"[Page {page.page} — {page.filename}]\n{page.text}"
        if chunks and total + len(chunk) > max_chars:
            break
        chunks.append(chunk)
        total += len(chunk)
    text = "\n\n".join(chunks)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def _item_to_result(
    control: Any,
    item: dict,
    pages: Sequence[PageText],
    filename: str,
) -> AnalysisResult:
    """Validate, verify and adjudicate one batch item into an AnalysisResult."""
    payload = {
        "control_id": str(getattr(control, "id")),
        "control_name": str(getattr(control, "name")),
        "requirement": str(getattr(control, "requirement")),
        "status": item["status"],
        "requirement_coverage": item.get("requirement_coverage", "Unknown"),
        "evidence": item.get("evidence", []),
        "covered_scope": item.get("covered_scope", []),
        "uncovered_scope": item.get("uncovered_scope", []),
        "missing_elements": item.get("missing_elements", []),
        "conflicts": item.get("conflicts", []),
        "exceptions": item.get("exceptions", []),
        "reasoning": item.get("reasoning", ""),
        "review_required": item.get("review_required", False),
        "stale_is_violation": item.get("stale_is_violation", False),
    }
    validated = validate_model_result(
        payload,
        expected_control_id=str(getattr(control, "id")),
        pages=pages,
        filename=filename,
        control_name=str(getattr(control, "name")),
        requirement=str(getattr(control, "requirement")),
    )
    adjudicated = adjudicate(
        validated,
        requirement_kind=infer_requirement_kind(str(getattr(control, "requirement"))),
        stale_is_violation=validated.stale_is_violation,
    )
    citation = "; ".join(
        f'"{p.quote}" (p. {p.page}, {p.source_document})' for p in adjudicated.evidence
    )
    gap_comment = adjudicated.reasoning
    if adjudicated.missing_elements:
        gap_comment = (
            (gap_comment + " " if gap_comment else "")
            + "Missing: "
            + "; ".join(adjudicated.missing_elements)
        )
    return AnalysisResult(
        id=str(getattr(control, "id")),
        name=str(getattr(control, "name")),
        category=str(getattr(control, "category")),
        section=str(getattr(control, "section")),
        requirement=str(getattr(control, "requirement")),
        status=adjudicated.status.value,
        evidenceCitation=citation,
        gapComment=gap_comment,
        requirement_coverage=adjudicated.requirement_coverage.value,
        evidence=list(adjudicated.evidence),
        covered_scope=list(adjudicated.covered_scope),
        uncovered_scope=list(adjudicated.uncovered_scope),
        missing_elements=list(adjudicated.missing_elements),
        conflicts=list(adjudicated.conflicts),
        exceptions=list(adjudicated.exceptions),
        reasoning=adjudicated.reasoning,
        review_required=adjudicated.review_required,
        analysis_error=adjudicated.analysis_error or "",
        filename=filename,
    )


def _error_result(control: Any, filename: str, error: str) -> AnalysisResult:
    err = error_result(
        filename,
        str(getattr(control, "id")),
        str(getattr(control, "name")),
        str(getattr(control, "requirement")),
        error=error,
    )
    return AnalysisResult(
        id=str(getattr(control, "id")),
        name=str(getattr(control, "name")),
        category=str(getattr(control, "category")),
        section=str(getattr(control, "section")),
        requirement=str(getattr(control, "requirement")),
        status=EvidenceStatus.ANALYSIS_ERROR.value,
        evidenceCitation="",
        gapComment=(
            f"Batch analysis failed: {error}. Manual review required; "
            "this is not classified as a compliance gap."
        ),
        requirement_coverage="Unknown",
        reasoning=err.reasoning,
        review_required=True,
        analysis_error=error,
        filename=filename,
    )


def evaluate_batch(
    model: Any,
    document_text: str,
    batch_controls: Sequence[Any],
    pages: Optional[Sequence[PageText]] = None,
    filename: str = "document",
) -> List[AnalysisResult]:
    """Evaluate one batch. Retry once if the model returns invalid JSON or schema."""
    base_prompt = _system_prompt() + "\n\n" + _batch_prompt(batch_controls, document_text)
    expected_ids = [str(getattr(c, "id")) for c in batch_controls]
    last_error: Optional[Exception] = None
    scope_pages: List[PageText] = list(pages) if pages is not None else []

    for attempt in range(2):
        prompt = base_prompt
        if attempt == 1:
            prompt += (
                "\n\nYour previous response failed validation: " + str(last_error) + "\n"
                "Correct the response and return ONLY one valid JSON array. Do not omit controls. "
                "Return exactly one object per control, in this exact ID order: "
                + json.dumps(expected_ids, ensure_ascii=False)
                + ". Use exactly these keys: id, status, requirement_coverage, evidence, "
                "covered_scope, uncovered_scope, missing_elements, conflicts, exceptions, "
                "reasoning, review_required, stale_is_violation."
            )
        try:
            response_text = ask_with_backoff(model, prompt, max_retries=3)
            if not response_text:
                raise ValidationError("Empty response from model")
            parsed_items = _parse_batch_json_array(response_text, batch_controls)
            results: List[AnalysisResult] = []
            for c, item in zip(batch_controls, parsed_items):
                try:
                    results.append(_item_to_result(c, item, scope_pages, filename))
                except ValidationError as exc:
                    results.append(
                        _error_result(c, filename, f"Item failed validation: {exc}")
                    )
            return results
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                continue

    raise RuntimeError(
        f"Batch response invalid after one corrective retry: {last_error}"
    ) from last_error


def run_gap_analysis(
    combined_text: str,
    model: Any,
    framework: List[Any],
    max_workers: int = 2,
    pages: Optional[Sequence[PageText]] = None,
    filename: str = "document",
) -> List[AnalysisResult]:
    """Run full batch gap analysis.

    * The framework is split into chunks of 10 controls each.
    * Each batch is one LLM call returning exactly N objects.
    * Batches run sequentially with a 7-second pace (10 RPM ceiling).
    * Results are reconstructed in the original framework order.

    ``pages`` (page-aware extraction) should be supplied when available so
    quotations can be verified against source pages.  When only
    ``combined_text`` is available, verification falls back to searching
    that text with page numbers left unresolved.
    """

    if not combined_text or combined_text.strip() == "":
        return [
            _error_result(
                ctrl,
                filename,
                "No document text provided. Upload a readable document and rerun analysis.",
            )
            for ctrl in framework
        ]

    scope_pages: List[PageText] = list(pages) if pages is not None else []
    if not scope_pages:
        scope_pages = [
            PageText(filename=filename, page=1, text=combined_text, document_id=filename)
        ]
    max_chars = 45_000
    document_text = _pages_to_text(scope_pages, max_chars)
    if len(document_text) >= max_chars:
        document_text += f"\n\n[... document truncated at {max_chars} characters ...]"

    chunk_size = 10
    batches: List[List[Any]] = [
        framework[i : i + chunk_size] for i in range(0, len(framework), chunk_size)
    ]

    print("\n🔍 Starting batch gap analysis...")
    print(f"📊 Framework: {len(framework)} controls")
    print(f"📦 Batches: {len(batches)} (chunk size: {chunk_size})")
    print(f"📄 Document text length: {len(document_text)} characters")
    print("⚡ Sequential batches with 7s pacing to limit quota footprint")

    id_to_index = {getattr(ctrl, "id"): idx for idx, ctrl in enumerate(framework)}
    results_by_index: dict[int, AnalysisResult] = {}

    for batch in batches:
        try:
            batch_results = evaluate_batch(
                model, document_text, batch, pages=scope_pages, filename=filename
            )
            for r in batch_results:
                results_by_index[id_to_index[r.id]] = r

            batch_ids = [getattr(c, "id") for c in batch]
            compliant_count = sum(1 for r in batch_results if r.status == "Compliant")
            gap_count = sum(1 for r in batch_results if r.status in {s.value for s in GAP_STATUSES})
            print(f"✅ Batch {batch_ids}: Compliant={compliant_count}, Gaps={gap_count}")
        except Exception as e:
            err = str(e)
            print(f"❌ Batch failed: {err[:200]}")
            for c in batch:
                idx = id_to_index[getattr(c, "id")]
                results_by_index[idx] = _error_result(
                    c, filename, f"Batch analysis failed after retry: {err}"
                )

        # Hard pacing to stay under 10 RPM: 7 seconds between calls.
        time.sleep(7)

    ordered_results: List[AnalysisResult] = [
        results_by_index[i] for i in range(len(framework))
    ]

    print("\n✅ Batch gap analysis complete!")
    print(f"   Total Controls: {len(ordered_results)}")
    print("   Compliant: " + str(sum(1 for r in ordered_results if r.status == "Compliant")))
    print(
        "   Gaps: "
        + str(sum(1 for r in ordered_results if r.status in {s.value for s in GAP_STATUSES}))
    )
    print("   Analysis Errors: " + str(sum(1 for r in ordered_results if r.status == "Analysis Error")))

    return ordered_results


def compute_analysis_summary(results: List[AnalysisResult]) -> dict:
    """Summarize results with per-status counts.

    ``compliance_percentage`` is calculated only over controls that were
    successfully evaluated (Analysis Errors excluded from the denominator)
    and is rounded to two decimals.  It is a descriptive share of the
    evaluated controls, not a statistically validated measure.
    """
    total = len(results)
    by_status: Dict[str, int] = {status.value: 0 for status in EvidenceStatus}
    for r in results:
        if r.status in by_status:
            by_status[r.status] += 1
    compliant = by_status[EvidenceStatus.COMPLIANT.value]
    gaps = sum(by_status[s.value] for s in GAP_STATUSES)
    errors = by_status[EvidenceStatus.ANALYSIS_ERROR.value]
    analyzed = compliant + gaps
    compliance_percentage = (compliant / analyzed * 100) if analyzed else 0.0

    def grouped_counts(attribute: str) -> dict:
        grouped: dict[str, dict[str, int]] = {}
        for result in results:
            key = str(getattr(result, attribute) or "Uncategorized")
            entry = grouped.setdefault(
                key, {"compliant": 0, "gaps": 0, "errors": 0}
            )
            if result.status == EvidenceStatus.COMPLIANT.value:
                entry["compliant"] += 1
            elif result.status in {s.value for s in GAP_STATUSES}:
                entry["gaps"] += 1
            elif result.status == EvidenceStatus.ANALYSIS_ERROR.value:
                entry["errors"] += 1
        return grouped

    return {
        "total_controls": total,
        "compliant_count": compliant,
        "gap_count": gaps,
        "error_count": errors,
        "analyzed_count": analyzed,
        "compliance_percentage": round(compliance_percentage, 2),
        "by_status": by_status,
        "by_section": grouped_counts("section"),
        "by_category": grouped_counts("category"),
    }


def filter_results_by_status(results: List[AnalysisResult], status: str) -> List[AnalysisResult]:
    return [r for r in results if r.status == status]


def filter_results_by_section(results: List[AnalysisResult], section: str) -> List[AnalysisResult]:
    return [r for r in results if r.section == section]


def export_results_to_dict(results: List[AnalysisResult]) -> List[dict]:
    """Export to the shared 21-column schema (one row per evidence passage)."""
    from evidence_model import results_to_export_rows

    return results_to_export_rows([r.to_evidence_result() for r in results])
