"""Stage B — deterministic evidence evaluation (evidence-classification-v2).

Stage A (evidence retrieval) is performed by the language model, which
returns candidate passages, coverage, scope, conflicts, exceptions and
dates as structured JSON.  This module is Stage B: pure, deterministic
Python that adjudicates the final status from *validated* evidence.

Nothing here calls the model.  The rules below are the executable form of
the classification rules in the mandate:

1.  A favourable statement never automatically means "Compliant".
2.  Adverse evidence is considered even when favourable evidence exists.
3.  Policy statements are documentary evidence, never proof of operational
    effectiveness.
4.  Contradictions that materially affect the conclusion mean
    "Conflicting Evidence".
5.  Partial coverage of systems, populations or conditions means
    "Partially Compliant".
6.  Stale or overdue evidence is flagged when dates and review intervals
    are present; a review interval is never invented.
7.  A coverage percentage is never invented without a known denominator.
8.  Uncertainty is preserved: where the source does not support a
    definitive label, the result is "Needs Review", not a confident guess.

The adjudicator takes a validated :class:`~evidence_model.EvidenceResult`
plus the control's requirement kind and returns the final result (status
may be adjusted, with the adjustment recorded in ``reasoning``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Sequence

from evidence_model import (
    Coverage,
    EvidenceResult,
    EvidenceStatus,
)

__all__ = [
    "RequirementKind",
    "RecencyFinding",
    "infer_requirement_kind",
    "extract_dates",
    "check_recency",
    "detect_conflict_signals",
    "adjudicate",
    "error_result",
]

# Words in a requirement that imply the control must be *operating*, not
# merely documented.  Used only as a heuristic default; control matrices
# may override it explicitly.
_OPERATIONAL_KEYWORDS = (
    "implement",
    "operat",
    "enforc",
    "monitor",
    "test",
    "perform",
    "conduct",
    "complet",
    "execut",
    "verif",
    "reviewed",
    "remediat",
    "respond",
    "report",
    "maintain",
    "appl",
)


class RequirementKind(str):
    """Whether a requirement is satisfied by documentation or by operation."""

    DOCUMENTARY = "documentary"
    OPERATIONAL = "operational"


def infer_requirement_kind(requirement: str) -> str:
    """Heuristic: does the requirement ask for something operating?

    Defaults to operational when the requirement text contains an
    operational verb, otherwise documentary.  This is a heuristic, not a
    judgement — the adjudicator only uses it to cap policy-only evidence,
    never to invent a finding.
    """
    lowered = (requirement or "").lower()
    if any(word in lowered for word in _OPERATIONAL_KEYWORDS):
        return RequirementKind.OPERATIONAL
    return RequirementKind.DOCUMENTARY


_DATE_PATTERNS = [
    # 2026-01-15, 15/01/2026, 15-01-2026
    re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b"),
    # 15 January 2026 / January 15, 2026 / December 2024
    re.compile(
        r"\b(\d{1,2})?\s*(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(20\d{2})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(20\d{2})\b",
        re.IGNORECASE,
    ),
]

_MONTHS = {
    name.lower(): index
    for index, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}

_INTERVAL_RE = re.compile(
    r"\b(?:every|each|at least once (?:a|every)|reviewed? (?:at least )?once (?:a|every))\s+"
    r"(?:(\d+)\s+)?(day|week|month|year)s?\b"
    r"|\b(annual|annually|yearly|biannual|biennial|two-?yearly|quarterly|monthly|weekly)\b",
    re.IGNORECASE,
)

_INTERVAL_DAYS = {
    "day": 1,
    "week": 7,
    "month": 30,
    "year": 365,
    "annual": 365,
    "annually": 365,
    "yearly": 365,
    "biannual": 182,
    "biennial": 730,
    "two-yearly": 730,
    "quarterly": 91,
    "monthly": 30,
    "weekly": 7,
}


def _parse_date_match(match: re.Match) -> Optional[date]:
    groups = match.groups()
    try:
        if match.re is _DATE_PATTERNS[0]:
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            return date(year, month, day)
        if match.re is _DATE_PATTERNS[1]:
            day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
            return date(year, month, day)
        if match.re is _DATE_PATTERNS[2]:
            day = int(groups[0]) if groups[0] else 1
            month = _MONTHS[groups[1].lower()]
            year = int(groups[2])
            return date(year, month, day)
        if match.re is _DATE_PATTERNS[3]:
            month = _MONTHS[groups[0].lower()]
            day = int(groups[1])
            year = int(groups[2])
            return date(year, month, day)
    except ValueError:
        return None
    return None


def extract_dates(text: str) -> List[date]:
    """Extract calendar dates mentioned in a text (deduplicated, sorted)."""
    found: List[date] = []
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text or ""):
            parsed = _parse_date_match(match)
            if parsed is not None and parsed not in found:
                found.append(parsed)
    return sorted(found)


def extract_review_interval_days(text: str) -> Optional[int]:
    """Extract a stated review interval in days, or None if none is stated.

    The interval is only ever taken from the document text.  When no
    interval is stated, ``None`` is returned and no interval is invented.
    """
    match = _INTERVAL_RE.search(text or "")
    if not match:
        return None
    groups = match.groups()
    # groups: (count, unit) from the first alternative, or (word,) from the second
    if groups[2]:
        return _INTERVAL_DAYS.get(groups[2].lower())
    unit = (groups[1] or "year").lower()
    count = int(groups[0]) if groups[0] else 1
    return _INTERVAL_DAYS.get(unit, 365) * count


@dataclass
class RecencyFinding:
    """Outcome of the deterministic recency check for one result."""

    last_evidence_date: Optional[date] = None
    interval_days: Optional[int] = None
    reference_date: Optional[date] = None
    is_overdue: bool = False
    is_stale: bool = False
    detail: str = ""
    missing: List[str] = field(default_factory=list)


def check_recency(
    evidence_texts: Sequence[str],
    requirement_text: str = "",
    reference_date: Optional[date] = None,
) -> RecencyFinding:
    """Compare the latest evidence date against the stated review interval.

    ``reference_date`` defaults to today.  When either the last evidence
    date or the review interval is missing from the text, the finding
    records that gap instead of inventing an interval or a date.
    """
    reference = reference_date or date.today()
    combined = "\n".join(evidence_texts or [])
    interval = extract_review_interval_days(combined) or extract_review_interval_days(
        requirement_text or ""
    )
    dates = extract_dates(combined)
    finding = RecencyFinding(
        interval_days=interval,
        reference_date=reference,
        last_evidence_date=dates[-1] if dates else None,
    )
    if interval is None:
        finding.missing.append("No review interval stated in the evidence.")
    if not dates:
        finding.missing.append("No evidence date found in the evidence.")
        finding.detail = (
            "Recency cannot be assessed: no evidence date or no stated "
            "review interval."
        )
        return finding
    if interval is None:
        finding.detail = (
            "Recency cannot be assessed: no review interval stated."
        )
        return finding
    last = dates[-1]
    age_days = (reference - last).days
    if age_days > interval:
        finding.is_overdue = True
        finding.is_stale = True
        finding.detail = (
            f"Last evidence is dated {last.isoformat()}, {age_days} days "
            f"before {reference.isoformat()}, exceeding the stated review "
            f"interval of {interval} days."
        )
    else:
        finding.detail = (
            f"Last evidence is dated {last.isoformat()}, within the stated "
            f"review interval of {interval} days."
        )
    return finding


_CONTRADICTION_PATTERNS = [
    # Two different timeframes for the same action (e.g. "24 hours" vs "two business days").
    (re.compile(r"\b(\d+)\s*(hour|day|week|month)s?\b", re.IGNORECASE), "timeframe"),
    (
        re.compile(
            r"\b(mandatory|required|must)\b.{0,80}\b(optional|not required|at (?:the )?discretion)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "mandatory-vs-optional",
    ),
]


def detect_conflict_signals(texts: Sequence[str]) -> List[str]:
    """Deterministic contradiction signals across the supplied passages.

    This is a conservative detector: it only flags patterns that are
    genuinely contradictory on their face (different numeric timeframes for
    the same action, mandatory-vs-optional wording).  The language model
    remains responsible for semantic contradictions; this layer catches
    the cases that can be decided without interpretation.
    """
    signals: List[str] = []
    joined = "\n".join(texts or [])
    timeframes = {
        (int(m.group(1)), m.group(2).lower())
        for m in _CONTRADICTION_PATTERNS[0][0].finditer(joined)
    }
    # Distinct numeric timeframes in the same evidence set are a signal,
    # not a verdict — the caller decides materiality.
    if len({value for value, _ in timeframes}) > 1:
        signals.append(
            "Different numeric timeframes appear in the evidence "
            f"({sorted(timeframes)})."
        )
    for pattern, label in _CONTRADICTION_PATTERNS[1:]:
        if pattern.search(joined):
            signals.append(
                f"Mandatory-vs-optional wording appears in the evidence ({label})."
            )
    return signals


def error_result(
    filename: str,
    control_id: str,
    control_name: str = "",
    requirement: str = "",
    error: str = "Analysis failed",
) -> EvidenceResult:
    """Build an explicit Analysis Error result (never a compliance finding)."""
    return EvidenceResult(
        filename=filename,
        control_id=control_id,
        control_name=control_name,
        requirement=requirement,
        status=EvidenceStatus.ANALYSIS_ERROR,
        requirement_coverage=Coverage.UNKNOWN,
        evidence=[],
        reasoning="Analysis could not be completed reliably.",
        review_required=True,
        analysis_error=error,
    )


def adjudicate(
    result: EvidenceResult,
    requirement_kind: Optional[str] = None,
    reference_date: Optional[date] = None,
    stale_is_violation: bool = False,
) -> EvidenceResult:
    """Apply the deterministic classification rules to a validated result.

    ``requirement_kind`` is "operational" or "documentary" (inferred from
    the requirement text when omitted).  ``stale_is_violation`` should be
    set only when the caller has established that an overdue finding
    demonstrably violates the applicable remediation requirement and no
    valid approved exception exists (the NS-13 case); it is never assumed.

    The function mutates and returns ``result``.  Every adjustment is
    recorded in ``reasoning`` so the final label stays explainable.
    """
    kind = requirement_kind or infer_requirement_kind(result.requirement)
    notes: List[str] = []

    # 0. Analysis Error is terminal: nothing else is inferred from it.
    if result.status == EvidenceStatus.ANALYSIS_ERROR:
        result.review_required = True
        return result

    # 1. No verified evidence at all -> Not Found (never Non-Compliant).
    if not result.evidence:
        if result.status != EvidenceStatus.NOT_FOUND:
            notes.append(
                "No verified evidence passage supports this control; "
                "status set to Not Found (absence of evidence is not "
                "proof of non-compliance)."
            )
        result.status = EvidenceStatus.NOT_FOUND
        result.requirement_coverage = Coverage.NONE
        if not result.missing_elements:
            result.missing_elements.append(
                "No relevant supporting evidence was identified in the "
                "supplied documents."
            )
        result.review_required = False
        _append_notes(result, notes)
        return result

    # 2. Material, validated conflicts -> Conflicting Evidence.
    if result.conflicts:
        if result.status != EvidenceStatus.CONFLICTING_EVIDENCE:
            notes.append(
                "Conflicting evidence was identified and materially "
                "affects the conclusion."
            )
        result.status = EvidenceStatus.CONFLICTING_EVIDENCE
        result.review_required = True
        _append_notes(result, notes)
        return result

    # 3. Overdue evidence that demonstrably violates the requirement and
    #    has no valid approved exception -> Non-Compliant.
    if stale_is_violation:
        result.status = EvidenceStatus.NON_COMPLIANT
        result.review_required = True
        notes.append(
            "Overdue evidence demonstrably violates the applicable "
            "remediation requirement and no valid approved exception exists."
        )
        _append_notes(result, notes)
        return result

    # 4. Operational requirement supported only by policy/procedure text.
    if kind == RequirementKind.OPERATIONAL and not result.has_operational_evidence():
        # Distinguish "no operational evidence at all" from "some
        # operational evidence, but incomplete": the first is Not Found
        # for operational evidence, the second is Needs Review.
        if result.has_documentary_evidence_only():
            result.status = EvidenceStatus.NOT_FOUND
            result.requirement_coverage = Coverage.NONE
            notes.append(
                "Only policy or procedure text was found; no operational "
                "record, configuration evidence or third-party assurance "
                "was identified, so operational evidence is Not Found. "
                "Policy text alone is not proof of operation."
            )
        else:
            result.status = EvidenceStatus.NEEDS_REVIEW
            notes.append(
                "Operational evidence is incomplete; human judgement is "
                "required."
            )
        result.review_required = True
        _append_notes(result, notes)
        return result

    # 5. Partial coverage -> Partially Compliant.
    if result.requirement_coverage == Coverage.PARTIAL or result.uncovered_scope:
        result.status = EvidenceStatus.PARTIALLY_COMPLIANT
        _append_notes(result, notes)
        return result

    # 6. Explicit ambiguity / missing elements that block a conclusion.
    if result.status == EvidenceStatus.NEEDS_REVIEW:
        result.review_required = True
        _append_notes(result, notes)
        return result

    # 7. Full coverage with verified evidence -> Compliant, but only when
    #    the evidence actually supports the requirement kind.
    if result.requirement_coverage == Coverage.FULL and result.evidence:
        if result.status != EvidenceStatus.COMPLIANT:
            notes.append(
                "Evidence supports the requirement for the evaluated scope."
            )
        result.status = EvidenceStatus.COMPLIANT
        _append_notes(result, notes)
        return result

    # 8. Anything else is uncertain: preserve uncertainty.
    if result.status not in (
        EvidenceStatus.COMPLIANT,
        EvidenceStatus.PARTIALLY_COMPLIANT,
    ):
        result.status = EvidenceStatus.NEEDS_REVIEW
        result.review_required = True
        notes.append(
            "The available evidence does not support a definitive label; "
            "human review is required."
        )
    _append_notes(result, notes)
    return result


def _append_notes(result: EvidenceResult, notes: List[str]) -> None:
    for note in notes:
        if note not in result.reasoning:
            result.reasoning = (
                f"{result.reasoning} {note}".strip()
                if result.reasoning
                else note
            )
