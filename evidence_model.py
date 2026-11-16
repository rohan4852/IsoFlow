"""IsoFlow structured evidence model (evidence-classification-v2).

This module is the single source of truth for the unified, seven-status
classification architecture.  It replaces the previous minimal ``AuditRow``
(filename / control_id / finding / evidence) used by ``app.py`` and the
binary Compliant / Gap Detected model used by ``gap_analyzer.py``.

Design rules enforced here (see the Full Engineering Remediation Mandate):

* Every control result is a validated :class:`EvidenceResult`.  Required
  fields are checked before a model response is accepted; invalid payloads
  are rejected with :class:`ValidationError`, never repaired by permissive
  parsing.
* Quotations are verified deterministically against the original extracted
  page text (:func:`verify_quote`).  A paraphrase is never silently accepted
  as an exact quotation.
* ``confidence`` is optional and is never presented as a statistically
  validated probability.  The model is not asked to emit calibrated
  confidence, and the UI must not display it as one.
* AI-generated findings are kept separate from human reviewer decisions
  (``reviewer_decision`` / ``reviewer_comments`` are only ever set by a
  human through the UI).
* Every result serialises to JSON and to the flat 21-column export schema.

Statuses
--------
Compliant
    Sufficient relevant evidence supports the requirement for the evaluated
    scope.  Documented requirements are distinguished from verified
    operational evidence.
Partially Compliant
    Some requirements, systems, populations or conditions are covered while
    others are missing or incomplete.
Non-Compliant
    Available evidence demonstrates that a requirement is not met, provided
    the applicable requirement and scope are established.
Not Found
    No relevant supporting evidence was identified in the supplied
    documents.  Absence of evidence is NOT treated as proof of
    non-compliance.
Conflicting Evidence
    Two or more relevant passages or records contain contradictory
    requirements, dates, values, conditions or implementation claims.
Needs Review
    Relevant evidence exists, but a reliable final conclusion requires human
    judgement or additional evidence.
Analysis Error
    The analysis could not be completed or validated reliably (API error,
    malformed model output, invalid source data or another processing
    failure).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "EvidenceStatus",
    "EvidenceType",
    "Coverage",
    "EvidencePassage",
    "EvidenceResult",
    "PageText",
    "ExtractedDocument",
    "ValidationError",
    "normalize_text",
    "verify_quote",
    "validate_model_result",
    "result_to_export_rows",
    "results_to_export_rows",
    "EXPORT_COLUMNS",
    "STATUS_LABELS",
]


class ValidationError(ValueError):
    """Raised when a model response or result payload fails strict validation."""


class EvidenceStatus(str, Enum):
    COMPLIANT = "Compliant"
    PARTIALLY_COMPLIANT = "Partially Compliant"
    NON_COMPLIANT = "Non-Compliant"
    NOT_FOUND = "Not Found"
    CONFLICTING_EVIDENCE = "Conflicting Evidence"
    NEEDS_REVIEW = "Needs Review"
    ANALYSIS_ERROR = "Analysis Error"

    @classmethod
    def values(cls) -> List[str]:
        return [s.value for s in cls]

    @classmethod
    def coerce(cls, value: Any) -> "EvidenceStatus":
        """Strictly coerce a raw value to a status; unknown values are rejected."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            text = value.strip()
            for member in cls:
                if member.value == text:
                    return member
        raise ValidationError(f"Unknown status value: {value!r}")


class EvidenceType(str, Enum):
    POLICY = "Policy"
    PROCEDURE = "Procedure"
    OPERATIONAL_RECORD = "Operational Record"
    CONFIGURATION_EVIDENCE = "Configuration Evidence"
    EXCEPTION_RECORD = "Exception Record"
    THIRD_PARTY_ASSURANCE = "Third-Party Assurance"
    UNKNOWN = "Unknown"

    @classmethod
    def values(cls) -> List[str]:
        return [t.value for t in cls]

    @classmethod
    def coerce(cls, value: Any) -> "EvidenceType":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            text = value.strip()
            for member in cls:
                if member.value == text:
                    return member
        raise ValidationError(f"Unknown evidence type: {value!r}")


class Coverage(str, Enum):
    FULL = "Full"
    PARTIAL = "Partial"
    NONE = "None"
    UNKNOWN = "Unknown"

    @classmethod
    def coerce(cls, value: Any) -> "Coverage":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            text = value.strip()
            for member in cls:
                if member.value == text:
                    return member
        raise ValidationError(f"Unknown coverage value: {value!r}")


# Human-readable status labels used by the UI and exports.
STATUS_LABELS: Dict[str, str] = {
    EvidenceStatus.COMPLIANT.value: "Compliant",
    EvidenceStatus.PARTIALLY_COMPLIANT.value: "Partially Compliant",
    EvidenceStatus.NON_COMPLIANT.value: "Non-Compliant",
    EvidenceStatus.NOT_FOUND.value: "Not Found",
    EvidenceStatus.CONFLICTING_EVIDENCE.value: "Conflicting Evidence",
    EvidenceStatus.NEEDS_REVIEW.value: "Needs Review",
    EvidenceStatus.ANALYSIS_ERROR.value: "Analysis Error",
}

# The flat 21-column export schema (Excel and CSV are kept identical).
EXPORT_COLUMNS: List[str] = [
    "Filename",
    "Control ID",
    "Control Name",
    "Requirement",
    "Status",
    "Requirement Coverage",
    "Evidence Type",
    "Evidence Quotation",
    "Source Page",
    "Source Document",
    "Covered Scope",
    "Uncovered Scope",
    "Missing Elements",
    "Conflicts",
    "Exceptions",
    "Reasoning",
    "Confidence",
    "Review Required",
    "Reviewer Decision",
    "Reviewer Comments",
    "Analysis Error",
]

# Evidence types that count as operational proof.  Policy and procedure text
# alone is documentary evidence, never proof that a control operates.
OPERATIONAL_EVIDENCE_TYPES = frozenset(
    {
        EvidenceType.OPERATIONAL_RECORD,
        EvidenceType.CONFIGURATION_EVIDENCE,
        EvidenceType.THIRD_PARTY_ASSURANCE,
    }
)

DOCUMENTARY_EVIDENCE_TYPES = frozenset(
    {EvidenceType.POLICY, EvidenceType.PROCEDURE}
)


@dataclass
class EvidencePassage:
    """One verbatim evidence passage, traceable to a source page."""

    quote: str
    source_document: str
    page: Optional[int]  # 1-based page number; None only when unresolvable
    evidence_type: EvidenceType = EvidenceType.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quote": self.quote,
            "source_document": self.source_document,
            "page": self.page,
            "evidence_type": self.evidence_type.value,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "EvidencePassage":
        if not isinstance(data, dict):
            raise ValidationError("Evidence passage must be an object")
        quote = data.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            raise ValidationError("Evidence passage requires a non-empty 'quote'")
        source_document = data.get("source_document")
        if not isinstance(source_document, str) or not source_document.strip():
            raise ValidationError("Evidence passage requires a non-empty 'source_document'")
        page = data.get("page")
        if page is not None:
            if isinstance(page, bool) or not isinstance(page, int) or page < 1:
                raise ValidationError(f"Invalid evidence page: {page!r}")
        evidence_type = EvidenceType.coerce(data.get("evidence_type", "Unknown"))
        return cls(
            quote=quote.strip(),
            source_document=source_document.strip(),
            page=page,
            evidence_type=evidence_type,
        )


@dataclass
class EvidenceResult:
    """Structured, validated result for one control against the documents.

    ``reviewer_decision`` and ``reviewer_comments`` are human-only fields.
    They are never populated by the model and must never be presented as an
    AI result.
    """

    filename: str
    control_id: str
    control_name: str = ""
    requirement: str = ""
    status: EvidenceStatus = EvidenceStatus.NEEDS_REVIEW
    requirement_coverage: Coverage = Coverage.UNKNOWN
    evidence_type: List[EvidenceType] = field(default_factory=list)
    evidence: List[EvidencePassage] = field(default_factory=list)
    covered_scope: List[str] = field(default_factory=list)
    uncovered_scope: List[str] = field(default_factory=list)
    missing_elements: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    reasoning: str = ""
    # Optional, uncalibrated.  The engine does not ask the model for
    # confidence and never presents this as a validated probability.
    confidence: Optional[float] = None
    review_required: bool = False
    reviewer_decision: Optional[str] = None
    reviewer_comments: Optional[str] = None
    analysis_error: Optional[str] = None
    # Internal Stage A -> Stage B signal: True only when the retrieved
    # evidence shows an overdue finding that demonstrably violates the
    # remediation requirement AND no valid approved exception exists.
    # This is a semantic judgement made in Stage A; Stage B applies the
    # deterministic Non-Compliant rule.  It is not exported.
    stale_is_violation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.filename, str) or not self.filename.strip():
            raise ValidationError("EvidenceResult requires a non-empty 'filename'")
        if not isinstance(self.control_id, str) or not self.control_id.strip():
            raise ValidationError("EvidenceResult requires a non-empty 'control_id'")
        self.status = EvidenceStatus.coerce(self.status)
        self.requirement_coverage = Coverage.coerce(self.requirement_coverage)
        self.evidence_type = [EvidenceType.coerce(t) for t in self.evidence_type]
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(
                self.confidence, (int, float)
            ):
                raise ValidationError(f"Invalid confidence value: {self.confidence!r}")
            if not 0.0 <= float(self.confidence) <= 1.0:
                raise ValidationError(f"Confidence out of range [0, 1]: {self.confidence!r}")
            self.confidence = float(self.confidence)
        if self.status == EvidenceStatus.ANALYSIS_ERROR and not self.analysis_error:
            raise ValidationError("Analysis Error results require 'analysis_error'")
        if self.reviewer_decision is not None:
            # A reviewer decision is a status value chosen by a human.
            EvidenceStatus.coerce(self.reviewer_decision)

    # -- serialisation ---------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Internal adjudication signal; not part of the exported result.
        data.pop("stale_is_violation", None)
        data["status"] = self.status.value
        data["requirement_coverage"] = self.requirement_coverage.value
        data["evidence_type"] = [t.value for t in self.evidence_type]
        data["evidence"] = [p.to_dict() for p in self.evidence]
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Any) -> "EvidenceResult":
        if not isinstance(data, dict):
            raise ValidationError("EvidenceResult payload must be an object")
        evidence = [
            EvidencePassage.from_dict(item) for item in data.get("evidence", [])
        ]
        return cls(
            filename=data.get("filename", ""),
            control_id=data.get("control_id", ""),
            control_name=data.get("control_name", "") or "",
            requirement=data.get("requirement", "") or "",
            status=EvidenceStatus.coerce(data.get("status")),
            requirement_coverage=Coverage.coerce(
                data.get("requirement_coverage", "Unknown")
            ),
            evidence_type=[
                EvidenceType.coerce(t) for t in data.get("evidence_type", [])
            ],
            evidence=evidence,
            covered_scope=_str_list(data.get("covered_scope", []), "covered_scope"),
            uncovered_scope=_str_list(data.get("uncovered_scope", []), "uncovered_scope"),
            missing_elements=_str_list(data.get("missing_elements", []), "missing_elements"),
            conflicts=_str_list(data.get("conflicts", []), "conflicts"),
            exceptions=_str_list(data.get("exceptions", []), "exceptions"),
            reasoning=data.get("reasoning", "") or "",
            confidence=data.get("confidence"),
            review_required=bool(data.get("review_required", False)),
            reviewer_decision=data.get("reviewer_decision"),
            reviewer_comments=data.get("reviewer_comments"),
            analysis_error=data.get("analysis_error"),
        )

    # -- helpers ---------------------------------------------------------
    def has_operational_evidence(self) -> bool:
        return any(
            p.evidence_type in OPERATIONAL_EVIDENCE_TYPES for p in self.evidence
        )

    def has_documentary_evidence_only(self) -> bool:
        return bool(self.evidence) and all(
            p.evidence_type in DOCUMENTARY_EVIDENCE_TYPES for p in self.evidence
        )

    def is_gap(self) -> bool:
        """True when the result represents an unmet or unproven requirement."""
        return self.status in (
            EvidenceStatus.PARTIALLY_COMPLIANT,
            EvidenceStatus.NON_COMPLIANT,
            EvidenceStatus.NOT_FOUND,
            EvidenceStatus.CONFLICTING_EVIDENCE,
            EvidenceStatus.NEEDS_REVIEW,
        )


def _str_list(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValidationError(f"'{field_name}' must be a list of strings")
    return [v.strip() for v in value if v.strip()]


# ---------------------------------------------------------------------------
# Page-aware extraction model
# ---------------------------------------------------------------------------


@dataclass
class PageText:
    """One extracted PDF page, with its source preserved."""

    filename: str
    page: int  # 1-based
    text: str
    document_id: str = ""

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValidationError(f"Invalid page number: {self.page!r}")
        if not self.document_id:
            self.document_id = self.filename


@dataclass
class ExtractedDocument:
    """A PDF's page-aware extraction, with extraction health flags."""

    filename: str
    document_id: str
    pages: List[PageText] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    extraction_error: Optional[str] = None

    @property
    def text(self) -> str:
        """Joined text (page boundaries preserved with markers)."""
        return "\n\n".join(
            f"[Page {p.page}]\n{p.text}" for p in self.pages
        )

    @property
    def total_chars(self) -> int:
        return sum(len(p.text) for p in self.pages)

    @property
    def likely_scanned(self) -> bool:
        """True when the PDF has pages but almost no extractable text."""
        if not self.pages:
            return False
        if self.total_chars == 0:
            return True
        chars_per_page = self.total_chars / len(self.pages)
        return chars_per_page < 20


# ---------------------------------------------------------------------------
# Deterministic quotation verification
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalise whitespace for comparison (case is preserved)."""
    if not isinstance(text, str):
        return ""
    text = text.replace("\x00", " ")
    return _WHITESPACE_RE.sub(" ", text).strip()


def verify_quote(
    quote: str, pages: Sequence[PageText]
) -> Optional[Tuple[str, int]]:
    """Verify a quotation against the original extracted pages.

    Returns ``(document_id, page)`` of the first page whose normalised text
    contains the normalised quotation, or ``None`` when the quotation cannot
    be found anywhere.  This is a deterministic check: the model is never
    trusted to verify its own quotations.
    """
    needle = normalize_text(quote)
    if not needle:
        return None
    for page in pages:
        if needle in normalize_text(page.text):
            return (page.document_id, page.page)
    return None


def validate_model_result(
    payload: Any,
    expected_control_id: str,
    pages: Sequence[PageText],
    filename: str,
    control_name: str = "",
    requirement: str = "",
) -> EvidenceResult:
    """Strictly validate one model response payload for one control.

    Rejects: non-object payloads, missing/wrong control id, unknown status
    or coverage values, missing required fields, malformed evidence, quotes
    that cannot be verified against the source pages, and invalid page
    references.  Quotations that fail verification are dropped; if a result
    is left with no verified evidence while claiming evidence, it is
    downgraded to "Needs Review" with the failure recorded.
    """
    if not isinstance(payload, dict):
        raise ValidationError("Model response must be a JSON object")
    control_id = payload.get("control_id")
    if not isinstance(control_id, str) or not control_id.strip():
        raise ValidationError("Model response is missing 'control_id'")
    if control_id.strip() != expected_control_id:
        raise ValidationError(
            f"Control id mismatch: got {control_id!r}, expected {expected_control_id!r}"
        )
    status = EvidenceStatus.coerce(payload.get("status"))
    coverage = Coverage.coerce(payload.get("requirement_coverage", "Unknown"))
    stale_flag = payload.get("stale_is_violation", False)
    if not isinstance(stale_flag, bool):
        raise ValidationError("'stale_is_violation' must be a boolean")

    raw_evidence = payload.get("evidence", [])
    if raw_evidence is None:
        raw_evidence = []
    if not isinstance(raw_evidence, list):
        raise ValidationError("'evidence' must be a list")
    verified: List[EvidencePassage] = []
    dropped: List[str] = []
    for item in raw_evidence:
        passage = EvidencePassage.from_dict(item)
        found = verify_quote(passage.quote, pages)
        if found is None:
            dropped.append(passage.quote[:80])
            continue
        doc_id, page_no = found
        # Associate the passage with the page where it was actually found.
        # Keep the model's document name when it matches the located page's
        # filename; otherwise correct it to the verified source.
        page_obj = next(
            (p for p in pages if p.document_id == doc_id and p.page == page_no),
            None,
        )
        if page_obj is not None and page_obj.filename != passage.source_document:
            passage = EvidencePassage(
                quote=passage.quote,
                source_document=page_obj.filename,
                page=page_obj.page,
                evidence_type=passage.evidence_type,
            )
        elif passage.page is not None and passage.page != page_no:
            passage = EvidencePassage(
                quote=passage.quote,
                source_document=passage.source_document,
                page=page_no,
                evidence_type=passage.evidence_type,
            )
        verified.append(passage)

    if dropped:
        # Fabricated or paraphrased quotations: never silently accepted.
        if status == EvidenceStatus.COMPLIANT:
            status = EvidenceStatus.NEEDS_REVIEW
        payload_notes = (
            f"{len(dropped)} quoted passage(s) could not be verified against "
            "the source documents and were removed."
        )
    else:
        payload_notes = ""

    evidence_types = sorted(
        {p.evidence_type.value for p in verified},
        key=lambda v: EvidenceType.values().index(v),
    )

    result = EvidenceResult(
        filename=filename,
        control_id=expected_control_id,
        control_name=control_name or payload.get("control_name", "") or "",
        requirement=requirement or payload.get("requirement", "") or "",
        status=status,
        requirement_coverage=coverage,
        evidence_type=[EvidenceType.coerce(t) for t in evidence_types],
        evidence=verified,
        covered_scope=_str_list(payload.get("covered_scope", []), "covered_scope"),
        uncovered_scope=_str_list(
            payload.get("uncovered_scope", []), "uncovered_scope"
        ),
        missing_elements=_str_list(
            payload.get("missing_elements", []), "missing_elements"
        ),
        conflicts=_str_list(payload.get("conflicts", []), "conflicts"),
        exceptions=_str_list(payload.get("exceptions", []), "exceptions"),
        reasoning=payload.get("reasoning", "") or "",
        confidence=payload.get("confidence"),
        review_required=bool(payload.get("review_required", False)),
        analysis_error=None,
        stale_is_violation=bool(payload.get("stale_is_violation", False)),
    )
    if dropped:
        result.missing_elements.append(payload_notes)
        result.review_required = True
        if not result.reasoning:
            result.reasoning = payload_notes
    if status == EvidenceStatus.COMPLIANT and not verified:
        raise ValidationError(
            "Compliant result requires at least one verified evidence passage"
        )
    return result


def result_to_export_rows(result: EvidenceResult) -> List[Dict[str, Any]]:
    """Flatten one result to the 21-column export schema.

    One row is emitted per evidence passage so no evidence is discarded; a
    result with no passages still emits exactly one row.
    """
    base: Dict[str, Any] = {
        "Filename": result.filename,
        "Control ID": result.control_id,
        "Control Name": result.control_name,
        "Requirement": result.requirement,
        "Status": result.status.value,
        "Requirement Coverage": result.requirement_coverage.value,
        "Evidence Type": "; ".join(t.value for t in result.evidence_type),
        "Covered Scope": "; ".join(result.covered_scope),
        "Uncovered Scope": "; ".join(result.uncovered_scope),
        "Missing Elements": "; ".join(result.missing_elements),
        "Conflicts": "; ".join(result.conflicts),
        "Exceptions": "; ".join(result.exceptions),
        "Reasoning": result.reasoning,
        "Confidence": (
            "" if result.confidence is None else round(float(result.confidence), 3)
        ),
        "Review Required": "Yes" if result.review_required else "No",
        "Reviewer Decision": result.reviewer_decision or "",
        "Reviewer Comments": result.reviewer_comments or "",
        "Analysis Error": result.analysis_error or "",
    }
    rows: List[Dict[str, Any]] = []
    if result.evidence:
        for passage in result.evidence:
            row = dict(base)
            row["Evidence Quotation"] = passage.quote
            row["Source Page"] = passage.page if passage.page is not None else ""
            row["Source Document"] = passage.source_document
            # Per-passage evidence type overrides the joined list for clarity.
            row["Evidence Type"] = passage.evidence_type.value
            rows.append(row)
    else:
        row = dict(base)
        row["Evidence Quotation"] = ""
        row["Source Page"] = ""
        row["Source Document"] = ""
        rows.append(row)
    return rows


def results_to_export_rows(results: Sequence[EvidenceResult]) -> List[Dict[str, Any]]:
    """Flatten all results to export rows (one row per evidence passage)."""
    rows: List[Dict[str, Any]] = []
    for result in results:
        rows.extend(result_to_export_rows(result))
    return rows
