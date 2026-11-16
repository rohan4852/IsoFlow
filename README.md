# IsoFlow — AI-assisted compliance evidence mapping

IsoFlow is a Streamlit application that maps policy and evidence documents
to compliance controls (ISO 27001 by default, or a custom CSV control
matrix such as SOC 2) and produces a structured, human-reviewable audit
trail. It is an **AI-assisted evidence-mapping tool for human-reviewed
workflows**. It is **not** a certified compliance determination, an audit
opinion, or a guarantee of audit outcomes.

## What it does

1. **Upload** one or more PDF policy/evidence documents and (optionally)
   a custom control matrix as CSV (first column: control ID, second
   column: requirement/description).
2. **Analyse** every control against every document with a two-stage
   engine:
   - **Stage A — evidence retrieval (Gemini):** retrieves favourable
     *and* unfavourable passages, exceptions, dates and scope, with
     verbatim quotations and source locations.
   - **Stage B — evaluation (deterministic Python):** adjudicates the
     final status from validated evidence only. The model never verifies
     its own quotations and never decides the final status alone.
3. **Review** the results in the app: status, coverage, verified
   quotations with source page and filename, reasoning, missing
   elements, conflicts, exceptions and a review-required indicator.
   A human reviewer can record a decision and comments per control;
   reviewer decisions are shown separately from AI results.
4. **Export** the full evidence chain as CSV or styled Excel
   (21-column schema, one row per evidence passage, plus a per-status
   summary sheet). Exports are generated in memory; no report files are
   written to the server filesystem.

A second workflow, the **gap analysis** tab, evaluates the same
documents against the full ISO 27001:2022 framework (115 controls) in
batches of 10, with the same seven-status model and quotation
verification.

## Classification model (seven statuses)

| Status | Meaning |
|---|---|
| Compliant | Sufficient verified evidence supports the requirement for the evaluated scope. |
| Partially Compliant | Some systems, populations or conditions are covered; others are missing. |
| Non-Compliant | The evidence shows the requirement is not met (only when the requirement and scope are established, e.g. an overdue finding with no valid approved exception). |
| Not Found | No relevant supporting evidence was identified, or only policy text was found for an operational requirement (policy text alone is not proof of operation). Absence of evidence is not proof of non-compliance. |
| Conflicting Evidence | Two or more passages contradict each other on requirements, dates, values or claims in a way that materially affects the conclusion. |
| Needs Review | Relevant evidence exists but a reliable conclusion needs human judgement or more evidence. This is the default when the source does not support a definitive label. |
| Analysis Error | The analysis could not be completed reliably (API failure, malformed model output, validation failure). Never presented as a compliance finding. |

Evidence types: Policy, Procedure, Operational Record, Configuration
Evidence, Exception Record, Third-Party Assurance, Unknown.

### Traceability guarantees

- PDF extraction is **page-aware**: every passage carries its filename,
  document id and 1-based page number. Page boundaries are preserved
  across multiple PDFs.
- Every quotation is **verified deterministically** against the extracted
  source pages (whitespace-normalised substring search). Quotations that
  cannot be verified are dropped, never repaired or paraphrased; a
  Compliant claim that loses its only quotation is downgraded to
  Needs Review.
- Model responses are **strictly validated**: invalid JSON, missing or
  duplicate control IDs, unknown statuses, malformed evidence, invalid
  page references and invalid confidence values are rejected. There is
  **no permissive regex fallback** that turns malformed model output
  into a valid result.
- A coverage percentage is never invented without a known denominator.
  The compliance % shown in gap analysis is the share of successfully
  evaluated controls marked Compliant; Analysis Errors are excluded
  from its denominator.
- Review intervals and dates are only ever taken from the document
  text; an interval is never invented. An overdue date alone is not a
  violation — Non-Compliant requires an overdue finding that
  demonstrably violates the remediation requirement with no valid
  approved exception.
- Confidence, if present, is uncalibrated model output and is never
  presented as a validated probability. The engine does not ask the
  model for confidence.

## Repository layout

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI: upload, demo, main audit, results view, exports. |
| `audit_engine.py` | Two-stage main-audit engine (Stage A prompt, strict parsing, rate-limit backoff, per-control analysis). |
| `classification.py` | Stage B deterministic adjudication, recency/conflict helpers. |
| `evidence_model.py` | Seven-status data model, quotation verification, strict model-response validation, 21-column export schema. |
| `pdf_extraction.py` | Page-aware PDF text extraction (blank-page / scanned / failure flags). |
| `gap_analyzer.py` | Batch gap-analysis engine (10 controls per call, strict batch validation, summary). |
| `gap_analysis_streamlit.py` | Gap-analysis tab UI. |
| `iso27001_framework.py` | ISO 27001:2022 framework — 115 controls (22 clauses + 93 Annex A). |
| `excel_formatter.py` | Excel/CSV export (21-column schema, per-status formatting, summary sheet, in-memory). |
| `dummy_policy.pdf`, `dummy_controls.csv` | Demo files for the 1-click sample run. |
| `tests/` | Unit + regression tests (see below). |

## Running locally

```bash
git clone https://github.com/rohan4852/IsoFlow.git
cd IsoFlow
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### Secrets

The app reads Streamlit secrets (`st.secrets`):

| Secret | Purpose |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key used by the analysis engine. |
| `ACCESS_KEY` | PassKey gate shown on first load. |

For local development, create `.streamlit/secrets.toml` with those two
keys. **Never commit secrets.** `.env` is git-ignored; a `.env` file
containing only a placeholder was previously tracked in error and has
been removed. `.env.example` documents the expected variables.

The model used for analysis is `models/gemini-3.5-flash-lite`
(hardcoded in `app.py`). The `google-generativeai` SDK used here is
deprecated upstream (Google recommends the `google-genai` SDK); the
integration is kept unchanged in this release and migration is a
documented follow-up — see Limitations.

## Running the tests

```bash
pip install -r requirements.txt   # includes pytest and openpyxl
python -m pytest tests/ -q
```

The suite (171 tests) uses deterministic mocked model responses; **no
live Gemini call is made** in the standard suite. It covers quotation
verification, page preservation, multi-document retrieval,
contradiction / partial-scope / stale-evidence / missing-evidence /
exception handling, invalid model responses, Excel and CSV exports,
error handling, and a 30-control regression suite
(`tests/test_northstar_regression.py`) built on a synthetic fixture
(`tests/fixtures/northstar_fixture.py`).

**Fixture provenance:** the original 30-control test policy and control
matrix were not present in this repository, so the regression fixture is
a new, separately documented synthetic fixture. It does not reproduce
the original evaluation and must not be described as doing so. Expected
statuses in the fixture are proposed labels, not certified audit
judgements.

## Current limitations

- **PDF only.** Uploads accept PDF documents and CSV control matrices.
  `.docx` / `.txt` uploads and large-file handling are not implemented.
- **No OCR.** `pdf2image` and `pytesseract` are listed in
  `requirements.txt` but are not used by any code path. Scanned or
  image-only PDFs are flagged (blank pages / no extractable text) rather
  than OCR-processed.
- **Model availability is not verified here.** The configured model name
  (`models/gemini-3.5-flash-lite`) is used as-is; live availability
  depends on the API key and Google's model catalogue at run time.
  `google-generativeai` is deprecated upstream; migrating to
  `google-genai` is a follow-up, not part of this change.
- **AI results are not determinations.** Every result is an AI-assisted
  finding for human review. The app never claims certification,
  independent audit, guaranteed audit outcomes, zero data retention,
  isolated/RAM-only execution, or production-grade security — none of
  those properties are established by this codebase.
- **Demo files are illustrative.** `dummy_policy.pdf` /
  `dummy_controls.csv` exist only to demonstrate the flow.
- **Session state only.** Results live in the Streamlit session; there
  is no database, user management, or persistent audit store.
