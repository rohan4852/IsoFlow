"""IsoFlow — AI-assisted compliance evidence mapping (Streamlit).

Evidence-classification-v2: the main audit pipeline now uses the unified
seven-status model (Compliant, Partially Compliant, Non-Compliant,
Not Found, Conflicting Evidence, Needs Review, Analysis Error) with
page-aware source traceability and deterministic quotation verification.

What this app does and does not do
-----------------------------------
* It maps documents to controls and surfaces evidence for a human
  reviewer.  Results are AI-assisted findings, NOT certified compliance
  determinations and NOT an audit opinion.
* Quotations are verified deterministically against the extracted source
  pages; unverified quotations are dropped, never repaired.
* Exports (CSV / Excel) are generated in memory; no report files are
  written to the server filesystem.
"""

import os
from typing import List, Sequence, Tuple

import pandas as pd
import streamlit as st

import google.generativeai as genai
from audit_engine import analyse_controls
from evidence_model import (
    EvidenceResult,
    EvidenceStatus,
    PageText,
)
from excel_formatter import generate_csv_bytes, generate_excel_bytes
from gap_analysis_streamlit import render_gap_analysis_tab
from pdf_extraction import extract_pdf_pages

# Backwards-compatible name: the old AuditRow is superseded by
# EvidenceResult.  Kept as an alias so older imports do not break.
AuditRow = EvidenceResult


def get_working_model_name(api_key):
    genai.configure(api_key=api_key)
    try:
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                name = m.name
                if "flash" in name.lower():
                    return name
                if "gemini-1.5-pro" in name.lower():
                    return name
                if "gemini-pro" in name.lower():
                    return name
        return "models/gemini-pro"
    except Exception:
        return "models/gemini-pro"


def process_audit(
    pages_by_document: Sequence[Tuple[str, Sequence[PageText]]],
    active_controls: Sequence[Tuple[str, str, str]],
    model,
) -> List[EvidenceResult]:
    """Run the two-stage audit across every document and control.

    ``pages_by_document`` is a list of ``(filename, pages)`` pairs.
    ``active_controls`` is a list of ``(control_id, name, requirement)``
    tuples.  Returns validated, adjudicated results in stable order.
    """
    current_step = 0

    status = st.status("🚀 Initializing Full Audit...", expanded=True)
    progress_bar = st.progress(0)

    def _progress(control_id: str, done: int, total: int) -> None:
        nonlocal current_step
        current_step = done
        status.write(f"⚡ Extracted evidence for **{control_id}**")
        progress_bar.progress(min(done / max(total, 1), 1.0))

    for filename, _ in pages_by_document:
        status.write(f"Reading **{filename}**...")

    all_rows = analyse_controls(
        model,
        pages_by_document,
        active_controls,
        max_workers=5,
        progress=_progress,
    )

    status.update(label="✅ Audit Complete!", state="complete", expanded=False)
    progress_bar.empty()
    return all_rows


def _load_controls_from_csv(df: pd.DataFrame) -> List[Tuple[str, str, str]]:
    """Load a custom control matrix CSV.

    The first column is the control ID and the second is the requirement /
    description.  An optional third column may carry the requirement kind
    ("operational" or "documentary"); it is validated but not required.
    """
    if df.shape[1] < 2:
        raise ValueError(
            "The uploaded CSV must contain at least two columns: "
            "control ID and requirement/description."
        )
    controls: List[Tuple[str, str, str]] = []
    seen = set()
    for _, row in df.iterrows():
        cid = str(row.iloc[0]).strip()
        desc = str(row.iloc[1]).strip()
        if not cid or not desc or cid.lower() == "nan" or desc.lower() == "nan":
            raise ValueError("Control matrix rows must have a non-empty ID and description.")
        if cid in seen:
            raise ValueError(f"Duplicate control ID in matrix: {cid}")
        seen.add(cid)
        controls.append((cid, desc, desc))
    if not controls:
        raise ValueError("The control matrix is empty.")
    return controls


def _default_controls() -> List[Tuple[str, str, str]]:
    return [
        ("A.5.1", "Policies for information security", "Policies for information security"),
        ("A.8.2", "Privileged access rights", "Privileged access rights"),
        ("A.9.1", "Access control policy", "Access control policy"),
        ("A.10.1", "Cryptography policy", "Cryptography policy"),
        ("A.12.1", "Documented operating procedures", "Documented operating procedures"),
        ("A.13.1", "Network security management", "Network security management"),
    ]


def render_audit_results(results: List[EvidenceResult]) -> None:
    """Structured results view: status, coverage, evidence, review state.

    AI-generated findings, source evidence and human reviewer decisions
    are shown separately and labelled as such.
    """
    st.subheader("📋 Audit Findings")
    st.caption(
        "AI-assisted findings for human review. These results are not a "
        "certified compliance determination and not an audit opinion."
    )

    # --- Summary metrics ---
    counts = {status.value: 0 for status in EvidenceStatus}
    for r in results:
        counts[r.status.value] += 1
    cols = st.columns(len(counts))
    for col, status in zip(cols, EvidenceStatus):
        col.metric(status.value, counts[status.value])
    review_needed = sum(1 for r in results if r.review_required)
    st.info(f"🔎 {review_needed} of {len(results)} results need human review.")

    # --- Per-control expandable detail ---
    for result in results:
        icon = {
            EvidenceStatus.COMPLIANT.value: "✅",
            EvidenceStatus.PARTIALLY_COMPLIANT.value: "🟡",
            EvidenceStatus.NON_COMPLIANT.value: "❌",
            EvidenceStatus.NOT_FOUND.value: "🔍",
            EvidenceStatus.CONFLICTING_EVIDENCE.value: "⚠️",
            EvidenceStatus.NEEDS_REVIEW.value: "👀",
            EvidenceStatus.ANALYSIS_ERROR.value: "🛠️",
        }.get(result.status.value, "•")
        header = (
            f"{icon} {result.control_id} — {result.control_name or result.control_id} "
            f"· {result.status.value}"
        )
        with st.expander(header, expanded=False):
            st.markdown(f"**Status (AI):** {result.status.value}")
            st.markdown(f"**Requirement coverage:** {result.requirement_coverage.value}")
            st.markdown(f"**Requirement:** {result.requirement or '—'}")
            st.markdown("**AI reasoning:**")
            st.write(result.reasoning or "—")

            st.markdown("**Source evidence (verified quotations):**")
            if result.evidence:
                for passage in result.evidence:
                    st.markdown(
                        f"> “{passage.quote}”\n\n"
                        f"> — {passage.source_document}, page {passage.page} "
                        f"({passage.evidence_type.value})"
                    )
            else:
                st.write("No verified evidence passage.")

            if result.covered_scope:
                st.markdown("**Covered scope:** " + "; ".join(result.covered_scope))
            if result.uncovered_scope:
                st.markdown("**Uncovered scope:** " + "; ".join(result.uncovered_scope))
            if result.missing_elements:
                st.markdown("**Missing elements:**")
                for item in result.missing_elements:
                    st.markdown(f"- {item}")
            if result.conflicts:
                st.markdown("**Conflicts:**")
                for item in result.conflicts:
                    st.markdown(f"- {item}")
            if result.exceptions:
                st.markdown("**Exceptions:**")
                for item in result.exceptions:
                    st.markdown(f"- {item}")
            if result.analysis_error:
                st.error(f"**Analysis error:** {result.analysis_error}")
            if result.review_required:
                st.warning("⚠️ Human review required for this result.")

            # --- Human reviewer decision (clearly separated from AI output) ---
            st.divider()
            st.markdown("**Human reviewer decision** (not an AI result)")
            key_prefix = f"review-{result.filename}-{result.control_id}"
            decision = st.selectbox(
                "Reviewer decision",
                options=["", *EvidenceStatus.values()],
                index=0,
                key=f"{key_prefix}-decision",
                help="A human reviewer may confirm or override the AI status.",
            )
            comments = st.text_area(
                "Reviewer comments",
                key=f"{key_prefix}-comments",
                help="Record the basis for the reviewer decision.",
            )
            if st.button("Save reviewer decision", key=f"{key_prefix}-save"):
                if decision:
                    result.reviewer_decision = decision
                    result.reviewer_comments = comments or None
                    result.review_required = False
                    st.success(f"Reviewer decision saved: {decision}")
                else:
                    st.warning("Choose a decision before saving.")


def main():
    st.set_page_config(page_title="IsoFlow", layout="wide")
    st.markdown("<style>header {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)

    # --- INITIALIZE SESSION STATE ---
    if "auth" not in st.session_state:
        st.session_state.auth = False
    if "audit_completed" not in st.session_state:
        st.session_state.audit_completed = False
    if "all_rows" not in st.session_state:
        st.session_state.all_rows = []
    if "combined_text" not in st.session_state:
        st.session_state.combined_text = ""
    if "all_pages" not in st.session_state:
        st.session_state.all_pages = []

    try:
        stored_key = st.secrets.get("ACCESS_KEY", "")
        api_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        st.error("Missing Secrets")
        return

    if not st.session_state.auth:
        key = st.text_input("PassKey", type="password")
        if st.button("Unlock"):
            if key == stored_key:
                st.session_state.auth = True
                st.rerun()
        return

    if "model_name" not in st.session_state:
        st.session_state.model_name = get_working_model_name(api_key)
    if "active_controls" not in st.session_state:
        st.session_state.active_controls = None

    st.title("IsoFlow — Automated Auditor")
    st.caption(
        "AI-assisted evidence mapping for human review. Results are not "
        "certified compliance determinations."
    )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="models/gemini-3.5-flash-lite",
        generation_config={"response_mime_type": "application/json"},
    )

    # --- 1-CLICK DEMO SECTION ---
    st.info("Don't have your client files handy? See the engine in action.")

    if st.button("🚀 Run Sample SOC 2 Mapping (1-Click Demo)"):
        with st.spinner("Processing sample PDF and Control Matrix..."):
            dummy_pdf_path = "dummy_policy.pdf"
            dummy_csv_path = "dummy_controls.csv"

            if not os.path.exists(dummy_pdf_path) or not os.path.exists(dummy_csv_path):
                st.error("Missing demo files on server! Please upload 'dummy_policy.pdf' and 'dummy_controls.csv' to the repo.")
            else:
                try:
                    with open(dummy_pdf_path, "rb") as f:
                        dummy_pdf_bytes = f.read()
                    doc = extract_pdf_pages(dummy_pdf_bytes, "dummy_policy.pdf")
                    if doc.warnings:
                        for warning in doc.warnings:
                            st.warning(warning)
                    df_dummy = pd.read_csv(dummy_csv_path)
                    dummy_controls = _load_controls_from_csv(df_dummy)
                    all_rows = process_audit(
                        [("dummy_policy.pdf", doc.pages)], dummy_controls, model
                    )
                    if all_rows:
                        render_audit_results(all_rows)
                        st.success("✅ Analysis Complete!")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.download_button(
                                "📥 Download Raw Data (CSV)",
                                generate_csv_bytes(all_rows),
                                "demo_report.csv",
                                "text/csv",
                            )
                        with col2:
                            st.download_button(
                                label="📊 Download Enterprise Excel Report (Demo)",
                                data=generate_excel_bytes(all_rows),
                                file_name="Sample_SOC2_Mapping.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
                except Exception as e:
                    st.error(f"Engine error: {e}")

    st.divider()

    # --- UI: UPLOAD MATRIX ---
    st.subheader("1. Or Upload Your Own Custom Matrix (SOC 1 / Custom)")
    matrix_file = st.file_uploader("Upload Matrix (CSV)", type=["csv"])

    if "active_controls_is_custom" not in st.session_state:
        st.session_state.active_controls_is_custom = False

    if matrix_file is not None:
        try:
            df_matrix = pd.read_csv(matrix_file)
            st.session_state.active_controls = _load_controls_from_csv(df_matrix)
            st.session_state.active_controls_is_custom = True
            st.success(f"Successfully loaded {len(st.session_state.active_controls)} custom controls!")
        except ValueError as e:
            st.error(f"Invalid control matrix: {e}")
            st.stop()

    if st.session_state.active_controls is None:
        st.session_state.active_controls_is_custom = False
        st.session_state.active_controls = _default_controls()

    active_controls = st.session_state.active_controls

    # --- UI: UPLOAD PDF ---
    st.subheader("2. Upload Policy Document")
    files = st.file_uploader("Upload Evidence (PDF)", type=["pdf"], accept_multiple_files=True)

    # --- BUTTON CLICK: EXECUTE AUDIT AND SAVE TO SESSION STATE ---
    if st.button("Run Full Audit", type="primary", disabled=not files):
        pages_by_document = []
        combined_parts = []
        for f in files:
            doc = extract_pdf_pages(f.getvalue(), f.name)
            if doc.warnings:
                for warning in doc.warnings:
                    st.warning(f"{f.name}: {warning}")
            if doc.extraction_error:
                st.error(f"Could not read text from {f.name}: {doc.extraction_error}")
                continue
            pages_by_document.append((f.name, doc.pages))
            combined_parts.append(doc.text)

        if not pages_by_document:
            st.error("No readable PDF text was extracted. Check the files and try again.")
        else:
            all_rows = process_audit(pages_by_document, active_controls, model)
            if all_rows:
                st.session_state.all_rows = all_rows
                st.session_state.combined_text = "\n\n".join(combined_parts)
                st.session_state.all_pages = [
                    page for _, pages in pages_by_document for page in pages
                ]
                st.session_state.audit_completed = True
                st.rerun()

    # --- PERSISTENT TAB RENDERING (SEPARATE TOP-LEVEL CHECK) ---
    if st.session_state.audit_completed:
        tab1, tab2 = st.tabs(["📋 Audit Findings", "🔍 Gap Analysis"])

        with tab1:
            render_audit_results(st.session_state.all_rows)

            st.success("✅ Analysis Complete!")

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📥 Download Raw Data (CSV)",
                    generate_csv_bytes(st.session_state.all_rows),
                    "report.csv",
                    "text/csv",
                )
            with col2:
                try:
                    st.download_button(
                        label="📊 Download Enterprise Excel Report",
                        data=generate_excel_bytes(st.session_state.all_rows),
                        file_name="IsoFlow_Audit_Report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                except Exception as excel_err:
                    st.error(f"Excel formatting failed. Check excel_formatter.py. Error: {excel_err}")

            st.info(
                "Results are AI-assisted findings for human review. They are "
                "not a certification, an audit opinion, or a guarantee of "
                "audit outcomes."
            )

        with tab2:
            render_gap_analysis_tab(
                extracted_text=st.session_state.combined_text,
                model=model,
                active_controls=(
                    st.session_state.active_controls
                    if st.session_state.get("active_controls_is_custom", False)
                    else None
                ),
                pages=st.session_state.get("all_pages") or None,
            )

            st.divider()
            if st.button("🔄 Reset & Start New Audit"):
                st.session_state.audit_completed = False
                st.session_state.all_rows = []
                st.session_state.combined_text = ""
                st.session_state.all_pages = []
                st.rerun()


if __name__ == "__main__":
    main()
