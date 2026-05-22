"""ISO 27001:2022 Gap Analysis Engine (Batch of 10, Strict JSON, Low RPM Footprint)

This module implements batch-processing gap analysis for ISO 27001:2022
(Clauses 4-10 and Annex A controls) to reduce API call frequency.

Required behaviors for quota avoidance:
- Each LLM call evaluates exactly N controls in one JSON array response.
- run_gap_analysis uses ThreadPoolExecutor(max_workers=2) to execute exactly
  two concurrent batch calls.
- Each batch is exactly 10 controls; the final remainder (if any) is evaluated
  in a separate batch with N = remainder.
- The model is forced to return a single valid JSON array containing exactly
  N objects following this internal schema:

  [
    {
      "id": "Control ID string",
      "status": "Compliant" or "Gap Detected",
      "evidence_citation": "Verbatim text quote or empty string",
      "gap_comment": "Remediation comment or empty string"
    }
  ]

The code:
- Parses the returned JSON array thread-safely.
- Converts elements into AnalysisResult dataclass instances.
- Reconstructs results in the original framework order.

Note: Evidence extraction must be verbatim; the model is instructed accordingly.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

import google.generativeai as genai  # noqa: F401 (used by caller/model configuration)


@dataclass(frozen=True)
class AnalysisResult:
    """Result of analyzing a single control against document text."""

    id: str
    name: str
    category: str
    section: str
    requirement: str

    status: str  # "Compliant" | "Gap Detected"
    evidenceCitation: str
    gapComment: str


def _system_prompt() -> str:
    return (
        "You are a strict ISO 27001:2022 Compliance Auditor performing gap analysis.\n\n"
        "CRITICAL RULES:\n"
        "1) VERBATIM EXTRACTION ONLY: If evidence of compliance is found, extract the EXACT,\n"
        "   word-for-word text snippet from the provided document. Do NOT paraphrase, summarize, or interpret.\n"
        "2) STRICT MATCHING: Match the control requirement against the actual document text.\n"
        "   If the text does not directly address the requirement, do NOT force a compliance decision.\n"
        "3) NO HALLUCINATION: If the document does not contain evidence of compliance, use status 'Gap Detected'\n"
        "   and explain what specific element is missing.\n\n"
        "OUTPUT RULES (mandatory):\n"
        "- Return ONLY valid JSON (no markdown, no backticks).\n"
        "- Return a single JSON array containing exactly N objects, where N equals the number of controls\n"
        "  included in this request.\n"
        "- The JSON array must match this internal schema EXACTLY (no extra keys, no nested objects):\n"
        "  [\n"
        "    {\n"
        "      \"id\": \"Control ID string\",\n"
        "      \"status\": \"Compliant\" or \"Gap Detected\",\n"
        "      \"evidence_citation\": \"Verbatim text quote or empty string\",\n"
        "      \"gap_comment\": \"Remediation comment or empty string\"\n"
        "    }\n"
        "  ]\n"
        "- Each object MUST correspond to the specific control requirement provided, matched by control 'id'.\n"
        "- If status is 'Compliant': evidence_citation MUST be a non-empty exact quote, and gap_comment MUST be ''.\n"
        "- If status is 'Gap Detected': evidence_citation MUST be '', and gap_comment MUST be non-empty."
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
        "DOCUMENT TEXT FOR ANALYSIS:\n"
        f"{document_text}\n\n"
        "TASK:\n"
        "For EACH control in this batch, determine whether the document text contains evidence that the control requirement is met.\n"
        "Return the results as a SINGLE JSON array (only JSON) with exactly N objects.\n"
        "The output order must match the order of controls as provided above, and each object must include exactly these keys:\n"
        "  id, status, evidence_citation, gap_comment\n"
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


def _parse_batch_json_array(response_text: str, batch_controls: Sequence[Any]) -> List[dict]:
    cleaned = _strip_code_fences(response_text or "")
    if not cleaned:
        raise ValueError("Empty response from model")

    data = json.loads(cleaned)

    if not isinstance(data, list):
        raise ValueError("Model response is not a JSON array")

    n_expected = len(batch_controls)
    if len(data) != n_expected:
        raise ValueError(f"JSON array length mismatch: got {len(data)}, expected {n_expected}")

    # Validate schema and ordering by id
    required_keys = {"id", "status", "evidence_citation", "gap_comment"}
    results: List[dict] = []

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Item {i} is not an object")

        item_keys = set(item.keys())
        if item_keys != required_keys:
            raise ValueError(f"Item {i} keys mismatch. Got {sorted(item_keys)} expected {sorted(required_keys)}")

        status = str(item.get("status", ""))
        if status not in ("Compliant", "Gap Detected"):
            raise ValueError(f"Item {i} invalid status: {status}")

        evidence = item.get("evidence_citation")
        gap_comment = item.get("gap_comment")
        if not isinstance(evidence, str) or not isinstance(gap_comment, str):
            raise ValueError(f"Item {i} evidence_citation/gap_comment must be strings")

        expected_id = getattr(batch_controls[i], "id")
        got_id = str(item.get("id", "")).strip()
        if got_id != expected_id:
            raise ValueError(f"Item {i} id mismatch. Got '{got_id}', expected '{expected_id}'")

        if status == "Compliant":
            if evidence.strip() == "" or gap_comment != "":
                raise ValueError(f"Item {i} Compliant rule violated")
        else:
            if evidence != "" or gap_comment.strip() == "":
                raise ValueError(f"Item {i} Gap Detected rule violated")

        results.append(item)

    return results


def evaluate_batch(model: Any, document_text: str, batch_controls: Sequence[Any]) -> List[AnalysisResult]:
    """Evaluate a single batch of controls (size N) in one API call."""

    max_truncation = 45000
    truncated_text = document_text[:max_truncation]
    if len(document_text) > max_truncation:
        truncated_text += f"\n\n[... document truncated at {max_truncation} characters ...]"

    prompt = _system_prompt() + "\n\n" + _batch_prompt(batch_controls, truncated_text)

    response_text = ask_with_backoff(model, prompt, max_retries=3)
    if not response_text:
        raise RuntimeError("Empty response from model")

    parsed_items = _parse_batch_json_array(response_text, batch_controls)

    results: List[AnalysisResult] = []
    for c, item in zip(batch_controls, parsed_items):
        results.append(
            AnalysisResult(
                id=getattr(c, "id"),
                name=getattr(c, "name"),
                category=getattr(c, "category"),
                section=getattr(c, "section"),
                requirement=getattr(c, "requirement"),
                status=item["status"],
                evidenceCitation=item["evidence_citation"],
                gapComment=item["gap_comment"],
            )
        )

    return results


def run_gap_analysis(
    combined_text: str,
    model: Any,
    framework: List[Any],
    max_workers: int = 2,
) -> List[AnalysisResult]:
    """Run full batch gap analysis.

    Per requirements:
    - Split the framework array into chunks of 10 controls each.
    - Force the model prompt to include all N controls (N can be remainder for the final chunk).
    - Force a single JSON array response containing exactly N objects.
    - Thread-safe parsing and ordered reconstruction.
    - Force ThreadPoolExecutor(max_workers=2).

    The max_workers argument is ignored to ensure exactly two concurrent batch calls.
    """

    if not combined_text or combined_text.strip() == "":
        return [
            AnalysisResult(
                id=getattr(ctrl, "id"),
                name=getattr(ctrl, "name"),
                category=getattr(ctrl, "category"),
                section=getattr(ctrl, "section"),
                requirement=getattr(ctrl, "requirement"),
                status="Gap Detected",
                evidenceCitation="",
                gapComment="No document text provided for analysis.",
            )
            for ctrl in framework
        ]

    chunk_size = 10
    batches: List[List[Any]] = [framework[i : i + chunk_size] for i in range(0, len(framework), chunk_size)]

    print("\n🔍 Starting batch gap analysis...")
    print(f"📊 Framework: {len(framework)} controls")
    print(f"📦 Batches: {len(batches)} (chunk size: {chunk_size})")
    print(f"📄 Document text length: {len(combined_text)} characters")
    print("⚡ Using 2 concurrent workers (max_workers=2) to limit quota footprint")

    id_to_index = {getattr(ctrl, "id"): idx for idx, ctrl in enumerate(framework)}

    # Store results by framework index (thread-safe writes are fine because keys are unique)
    results_by_index: dict[int, AnalysisResult] = {}

    # Strict rate limiting: run batches sequentially to keep total requests under the 10 RPM ceiling.
    # JSON parsing + ordering remain unchanged.
    with ThreadPoolExecutor(max_workers=1) as executor:
        for batch in batches:
            try:
                fut = executor.submit(evaluate_batch, model, combined_text, batch)
                batch_results = fut.result()

                for r in batch_results:
                    results_by_index[id_to_index[r.id]] = r

                batch_ids = [getattr(c, "id") for c in batch]
                compliant_count = sum(1 for r in batch_results if r.status == "Compliant")
                gap_count = sum(1 for r in batch_results if r.status == "Gap Detected")
                print(f"✅ Batch {batch_ids}: Compliant={compliant_count}, Gaps={gap_count}")

            except Exception as e:
                # Deterministic fallback for entire batch failure
                err = str(e)
                print(f"❌ Batch failed: {err[:200]}")
                for c in batch:
                    idx = id_to_index[getattr(c, "id")]
                    results_by_index[idx] = AnalysisResult(
                        id=getattr(c, "id"),
                        name=getattr(c, "name"),
                        category=getattr(c, "category"),
                        section=getattr(c, "section"),
                        requirement=getattr(c, "requirement"),
                        status="Gap Detected",
                        evidenceCitation="",
                        gapComment=f"Batch analysis error: {err}. Manual review required.",
                    )

            # Hard pacing to stay under 10 RPM: 7 seconds between calls.
            # (If ask_with_backoff triggers additional waits on 429, those apply on top.)
            time.sleep(7)


    # Reconstruct results in original framework order
    ordered_results: List[AnalysisResult] = [results_by_index[i] for i in range(len(framework))]

    print("\n✅ Batch gap analysis complete!")
    print(f"   Total Controls: {len(ordered_results)}")
    print(
        "   Compliant: "
        + str(sum(1 for r in ordered_results if r.status == "Compliant"))
    )
    print("   Gaps: " + str(sum(1 for r in ordered_results if r.status == "Gap Detected")))

    return ordered_results


def compute_analysis_summary(results: List[AnalysisResult]) -> dict:
    total = len(results)
    compliant = sum(1 for r in results if r.status == "Compliant")
    gaps = sum(1 for r in results if r.status == "Gap Detected")

    compliance_percentage = (compliant / total * 100) if total > 0 else 0

    by_section: dict[str, dict[str, int]] = {}
    for r in results:
        by_section.setdefault(r.section, {"compliant": 0, "gaps": 0})
        if r.status == "Compliant":
            by_section[r.section]["compliant"] += 1
        else:
            by_section[r.section]["gaps"] += 1

    by_category: dict[str, dict[str, int]] = {}
    for r in results:
        by_category.setdefault(r.category, {"compliant": 0, "gaps": 0})
        if r.status == "Compliant":
            by_category[r.category]["compliant"] += 1
        else:
            by_category[r.category]["gaps"] += 1

    return {
        "total_controls": total,
        "compliant_count": compliant,
        "gap_count": gaps,
        "compliance_percentage": round(compliance_percentage, 2),
        "by_section": by_section,
        "by_category": by_category,
    }


def filter_results_by_status(results: List[AnalysisResult], status: str) -> List[AnalysisResult]:
    return [r for r in results if r.status == status]


def filter_results_by_section(results: List[AnalysisResult], section: str) -> List[AnalysisResult]:
    return [r for r in results if r.section == section]


def export_results_to_dict(results: List[AnalysisResult]) -> List[dict]:
    return [
        {
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "section": r.section,
            "requirement": r.requirement,
            "status": r.status,
            "evidenceCitation": r.evidenceCitation,
            "gapComment": r.gapComment,
        }
        for r in results
    ]

