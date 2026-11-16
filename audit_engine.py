"""Two-stage evidence-mapping engine for the main audit pipeline.

Stage A — Evidence retrieval (language model)
    For each control the model is asked to return *all* relevant passages:
    favourable and unfavourable, exceptions and exclusions, dates, metrics
    and scope information, each with its source document and page.  The
    model is instructed never to stop after the first favourable passage
    and never to treat a policy statement as proof of operation.

Stage B — Evidence evaluation (deterministic Python)
    The model response is strictly validated
    (:func:`evidence_model.validate_model_result`) and then adjudicated by
    :func:`classification.adjudicate`.  Quotations are verified against the
    original page text; unverified quotations are dropped, never repaired.

This module replaces the old ``ask_single_control`` / ``_parse_audit_response``
path in ``app.py``, which used a binary Compliant / Not Found model and a
permissive regular-expression fallback that fabricated results from
malformed model output.  There is no regex fallback here: malformed JSON
is an Analysis Error for that control.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, List, Optional, Sequence, Tuple

from classification import adjudicate, error_result, infer_requirement_kind
from evidence_model import (
    EvidenceResult,
    PageText,
    ValidationError,
    validate_model_result,
)

__all__ = [
    "build_audit_prompt",
    "parse_model_response_strict",
    "ask_with_backoff",
    "analyse_control",
    "analyse_controls",
    "AUDIT_RESPONSE_SCHEMA",
]

AUDIT_RESPONSE_SCHEMA = {
    "control_id": "string (must match the requested control id exactly)",
    "status": "one of: Compliant, Partially Compliant, Non-Compliant, "
    "Not Found, Conflicting Evidence, Needs Review, Analysis Error",
    "requirement_coverage": "one of: Full, Partial, None, Unknown",
    "evidence": [
        {
            "quote": "exact verbatim quotation from the documents",
            "source_document": "filename the quotation came from",
            "page": "1-based page number, or null if genuinely unknown",
            "evidence_type": "Policy | Procedure | Operational Record | "
            "Configuration Evidence | Exception Record | "
            "Third-Party Assurance | Unknown",
        }
    ],
    "covered_scope": ["systems, populations or conditions with evidence"],
    "uncovered_scope": ["systems, populations or conditions without evidence"],
    "missing_elements": ["specific requirements with no supporting evidence"],
    "conflicts": ["contradictory requirements, dates, values or claims"],
    "exceptions": ["exception scope, owner, approval and expiry, if any"],
    "reasoning": "short explanation of how the conclusion was reached",
    "review_required": "true when human judgement is needed",
    # Only true when the evidence shows an overdue finding that
    # demonstrably violates the remediation requirement and no valid
    # approved exception exists.  Never set true on a guess.
    "stale_is_violation": "boolean, default false",
}


def build_audit_prompt(
    control_id: str,
    control_name: str,
    requirement: str,
    document_text: str,
    requirement_kind: str = "operational",
) -> str:
    """Build the Stage A prompt for one control.

    The prompt states the seven statuses and the classification rules
    explicitly, and requires the structured JSON schema above.  It asks
    for favourable *and* unfavourable evidence, exceptions, dates and
    scope — never only the first favourable passage.
    """
    return f"""You are a strict compliance evidence reviewer. Your job is to
find and report evidence, not to give a favourable verdict.

CONTROL: {control_id} — {control_name}
REQUIREMENT: {requirement}
REQUIREMENT KIND: {requirement_kind} (operational requirements need
operational evidence — records, configurations or third-party assurance —
not policy text alone; documentary requirements can be met by policy or
procedure text.)

DOCUMENT TEXT (page markers are [Page N]):
{document_text}

INSTRUCTIONS:
1. Search the WHOLE document set for this control. Retrieve favourable
   AND unfavourable passages. Do not stop after the first favourable
   passage.
2. Retrieve passages about exceptions, exclusions and conditional
   requirements, and any dates, metrics, deadlines and scope information.
3. A policy statement that something "should" happen is NOT proof that it
   happens. Do not infer implementation from a policy statement.
4. If two passages contradict each other (different timeframes, retention
   periods, mandatory vs optional, conflicting versions or dates), report
   both under "conflicts".
5. If only some systems, populations or conditions are covered, list the
   covered ones under "covered_scope" and the rest under
   "uncovered_scope", and set requirement_coverage to "Partial".
6. If a date and a review interval are both present, report them; flag
   overdue evidence in "missing_elements" or "reasoning".
7. Never invent a coverage percentage without a known denominator.
8. When the evidence does not support a definitive conclusion, use
   status "Needs Review" and set review_required to true.
8a. Set "stale_is_violation" to true ONLY when the evidence shows an
    overdue finding that demonstrably violates the remediation
    requirement and no valid approved exception exists.  An overdue
    review date alone is not a violation — say so in "reasoning".
9. Quote EXACTLY, word for word, from the document text, with the correct
   source document and 1-based page number. Do not paraphrase. Do not
   invent quotations.
10. If no relevant evidence exists, return status "Not Found" with an
    empty "evidence" list. Absence of evidence is not proof of
    non-compliance.

Return ONLY valid JSON matching this schema (no markdown, no backticks):
{json.dumps(AUDIT_RESPONSE_SCHEMA, indent=2)}
"""


def parse_model_response_strict(text: str) -> dict:
    """Parse a model response as strict JSON.

    Code fences are stripped; anything else that is not valid JSON is
    rejected.  There is deliberately NO regular-expression fallback:
    malformed model output must become an Analysis Error, never a
    fabricated audit result.
    """
    if not isinstance(text, str):
        raise ValidationError("Model response is not text")
    s = text.strip()
    if s.startswith("```json"):
        s = s[len("```json"):].strip()
    elif s.startswith("```"):
        s = s[len("```"):].strip()
    if s.endswith("```"):
        s = s[: -len("```")].strip()
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValidationError("Model response contains no JSON object")
    s = s[start : end + 1]
    try:
        data = json.loads(s)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Model response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("Model response JSON is not an object")
    return data


def ask_with_backoff(model: Any, prompt: str, retries: int = 3):
    """Gemini call with backoff for rate limits (429 / ResourceExhausted).

    Only rate-limit errors are retried.  Any other API error is raised so
    the caller can record an Analysis Error instead of silently converting
    an API failure into a compliance finding.
    """
    for attempt in range(retries):
        try:
            return model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                },
            )
        except Exception as exc:
            text = str(exc)
            is_rate_limit = (
                "429" in text
                or "ResourceExhausted" in text
                or "RESOURCE_EXHAUSTED" in text
                or "Too Many Requests" in text
            )
            if not is_rate_limit:
                raise
            if attempt < retries - 1:
                time.sleep((attempt + 1) * 5)
                continue
            raise


def analyse_control(
    model: Any,
    pages: Sequence[PageText],
    control_id: str,
    control_name: str,
    requirement: str,
    filename: str,
    max_chars: int = 120_000,
    requirement_kind: Optional[str] = None,
) -> EvidenceResult:
    """Run the two-stage analysis for one control.

    Returns a validated, adjudicated :class:`EvidenceResult`.  API errors,
    malformed responses and validation failures all produce an
    "Analysis Error" result for that control — never a compliance finding.
    """
    kind = requirement_kind or infer_requirement_kind(requirement)
    document_text = "\n\n".join(
        f"[Page {p.page} — {p.filename}]\n{p.text}" for p in pages
    )
    truncated = document_text[:max_chars]
    if len(document_text) > max_chars:
        truncated += f"\n\n[... document truncated at {max_chars} characters ...]"
    prompt = build_audit_prompt(
        control_id, control_name, requirement, truncated, kind
    )
    try:
        response = ask_with_backoff(model, prompt)
        text = getattr(response, "text", "") or ""
        payload = parse_model_response_strict(text)
        result = validate_model_result(
            payload,
            expected_control_id=control_id,
            pages=pages,
            filename=filename,
            control_name=control_name,
            requirement=requirement,
        )
    except ValidationError as exc:
        return error_result(
            filename, control_id, control_name, requirement,
            error=f"Model response failed validation: {exc}",
        )
    except Exception as exc:  # API failure or any other processing failure
        return error_result(
            filename, control_id, control_name, requirement,
            error=f"Analysis failed: {exc}",
        )
    return adjudicate(
        result,
        requirement_kind=kind,
        stale_is_violation=result.stale_is_violation,
    )


def analyse_controls(
    model: Any,
    pages_by_document: Sequence[Tuple[str, Sequence[PageText]]],
    controls: Sequence[Tuple[str, str, str]],
    max_workers: int = 5,
    progress: Optional[Callable[[str, int, int], None]] = None,
) -> List[EvidenceResult]:
    """Analyse every control against every document (parallel, threaded).

    ``pages_by_document`` is a list of ``(filename, pages)`` pairs.
    ``controls`` is a list of ``(control_id, control_name, requirement)``
    tuples.  All documents are searched for each control (Stage A never
    stops at the first document).  Results are returned in a stable order
    (document, then control).
    """
    all_pages: List[PageText] = [
        page for _, pages in pages_by_document for page in pages
    ]
    jobs: List[Tuple[str, str, str, str]] = []
    for filename, _ in pages_by_document:
        for control_id, control_name, requirement in controls:
            jobs.append((filename, control_id, control_name, requirement))

    results: List[EvidenceResult] = []
    total = len(jobs)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {
            executor.submit(
                analyse_control,
                model,
                all_pages,
                control_id,
                control_name,
                requirement,
                filename,
            ): (filename, control_id)
            for filename, control_id, control_name, requirement in jobs
        }
        for future in as_completed(future_to_job):
            filename, control_id = future_to_job[future]
            try:
                results.append(future.result())
            except Exception as exc:  # pragma: no cover - defensive
                results.append(
                    error_result(
                        filename, control_id, "", "",
                        error=f"Worker failed: {exc}",
                    )
                )
            done += 1
            if progress is not None:
                progress(control_id, done, total)

    # Stable order: document order, then control order.
    doc_order = {name: i for i, (name, _) in enumerate(pages_by_document)}
    ctrl_order = {cid: i for i, (cid, _, _) in enumerate(controls)}
    results.sort(key=lambda r: (doc_order.get(r.filename, 0), ctrl_order.get(r.control_id, 0)))
    return results
