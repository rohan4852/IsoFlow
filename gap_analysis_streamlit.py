"""
ISO 27001:2022 Gap Analysis - Streamlit Frontend Interface (evidence-classification-v2).

Interactive dashboard for displaying and exploring gap analysis results
using the unified seven-status model (Compliant, Partially Compliant,
Non-Compliant, Not Found, Conflicting Evidence, Needs Review, Analysis
Error).

Features:
- Real-time analysis execution with progress tracking
- Summary statistics with per-status counts (compliance % is calculated
  only over successfully evaluated controls; see gap_analyzer)
- Interactive filtering by status
- Structured detail view: evidence quotations with source page and
  document, reasoning, missing elements, conflicts, exceptions, and the
  review-required indicator
- CSV export using the shared 21-column evidence schema
- Session state management for result persistence

AI-generated findings and source evidence are shown separately from any
human reviewer decision.  Nothing here claims a result is certified or
independently audited.
"""

import streamlit as st
import pandas as pd
from typing import List
from types import SimpleNamespace

from evidence_model import EvidenceStatus


_STATUS_ICONS = {
    EvidenceStatus.COMPLIANT.value: "✅",
    EvidenceStatus.PARTIALLY_COMPLIANT.value: "🟡",
    EvidenceStatus.NON_COMPLIANT.value: "❌",
    EvidenceStatus.NOT_FOUND.value: "🔍",
    EvidenceStatus.CONFLICTING_EVIDENCE.value: "⚠️",
    EvidenceStatus.NEEDS_REVIEW.value: "👀",
    EvidenceStatus.ANALYSIS_ERROR.value: "🛠️",
}


def render_gap_analysis_tab(extracted_text: str, model, active_controls=None, pages=None):
    """
    Main frontend interface for ISO 27001:2022 gap analysis.

    Args:
        extracted_text: Combined text from uploaded documents.
        model: Configured Gemini model instance.
        active_controls: Optional custom control matrix (id, description).
        pages: Optional page-aware extraction (list of PageText) used to
            verify quotations against source pages.
    """

    try:
        from iso27001_framework import ISO27001_FRAMEWORK
        from gap_analyzer import run_gap_analysis, compute_analysis_summary, GAP_STATUSES
    except ImportError as e:
        st.error(f"Failed to import analysis modules: {e}")
        return

    def normalize_custom_controls(controls):
        """Convert app.py CSV control pairs into the object schema expected by gap_analyzer."""
        normalized = []
        seen_ids = set()
        for index, item in enumerate(controls or [], start=1):
            if not isinstance(item, (tuple, list)) or len(item) < 2:
                raise ValueError(f"Custom control row {index} must contain an ID and a description.")
            control_id = str(item[0]).strip()
            description = str(item[1]).strip()
            if not control_id or not description or control_id.lower() == "nan" or description.lower() == "nan":
                raise ValueError(f"Custom control row {index} has a blank ID or description.")
            if control_id in seen_ids:
                raise ValueError(f"Duplicate custom control ID: {control_id}")
            seen_ids.add(control_id)
            normalized.append(SimpleNamespace(
                id=control_id,
                name=description,
                category="Custom Matrix",
                section="Custom Matrix",
                requirement=description,
            ))
        if not normalized:
            raise ValueError("The custom control matrix is empty. Upload a valid CSV matrix or reset to the default framework.")
        return normalized

    try:
        if active_controls is None:
            selected_framework = list(ISO27001_FRAMEWORK)
            framework_label = "ISO 27001:2022 framework"
            framework_signature = tuple(
                (str(getattr(c, "id", "")), str(getattr(c, "requirement", "")))
                for c in selected_framework
            )
        else:
            selected_framework = normalize_custom_controls(active_controls)
            framework_label = "custom control matrix"
            framework_signature = tuple((c.id, c.requirement) for c in selected_framework)
    except ValueError as e:
        st.error(f"Invalid control matrix: {e}")
        return

    # ========================================================================
    # SESSION STATE MANAGEMENT
    # ========================================================================

    if "gap_analysis_results" not in st.session_state:
        st.session_state.gap_analysis_results = None
    if "gap_analysis_summary" not in st.session_state:
        st.session_state.gap_analysis_summary = None
    if "gap_analysis_running" not in st.session_state:
        st.session_state.gap_analysis_running = False
    if "gap_filter_status" not in st.session_state:
        st.session_state.gap_filter_status = "All"

    if st.session_state.get("gap_analysis_framework_signature") != framework_signature:
        st.session_state.gap_analysis_results = None
        st.session_state.gap_analysis_summary = None
        st.session_state.gap_analysis_running = False
        st.session_state.gap_analysis_framework_signature = framework_signature
        st.session_state.gap_filter_status = "All"

    # ========================================================================
    # ANALYSIS EXECUTION
    # ========================================================================

    if not extracted_text or extracted_text.strip() == "":
        st.warning("No document text available for gap analysis. Please upload documents on the main audit tab.")
        return

    if st.session_state.gap_analysis_results is None:

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Gap Analysis Ready")

        with col2:
            if st.button("Start Analysis", type="primary", use_container_width=True):
                st.session_state.gap_analysis_running = True
                st.rerun()

        if st.session_state.gap_analysis_running:
            with st.status("Analyzing document against ISO 27001:2022 framework...", expanded=True) as status:
                try:
                    st.write(f"Processing {len(extracted_text)} characters of document text...")
                    st.write(f"Evaluating {len(selected_framework)} controls from {framework_label}...")

                    results = run_gap_analysis(
                        combined_text=extracted_text,
                        model=model,
                        framework=selected_framework,
                        pages=pages,
                    )

                    if results:
                        summary = compute_analysis_summary(results)
                        st.session_state.gap_analysis_results = results
                        st.session_state.gap_analysis_summary = summary
                        st.write(f"Analysis complete: {len(results)} controls evaluated")
                        status.update(
                            label="Gap Analysis Complete!",
                            state="complete",
                            expanded=False,
                        )
                        st.session_state.gap_analysis_running = False
                        st.rerun()
                    else:
                        st.error("No results returned from gap analysis engine.")
                        st.session_state.gap_analysis_running = False

                except Exception as e:
                    st.error(f"Analysis failed: {str(e)}")
                    st.session_state.gap_analysis_running = False

    # ========================================================================
    # RESULTS DISPLAY
    # ========================================================================

    if st.session_state.gap_analysis_results is not None:
        results = st.session_state.gap_analysis_results
        summary = st.session_state.gap_analysis_summary

        st.divider()
        st.subheader("Compliance Summary")
        st.caption(
            "AI-assisted findings for human review. Compliance % is the share "
            "of successfully evaluated controls marked Compliant; Analysis "
            "Errors are excluded from its denominator."
        )

        by_status = summary.get("by_status", {})
        metric_cols = st.columns(4)
        with metric_cols[0]:
            st.metric(label="Total Controls", value=summary["total_controls"])
        with metric_cols[1]:
            st.metric(
                label="Compliance %",
                value=f"{summary['compliance_percentage']:.1f}%",
                help="Calculated only from controls successfully classified.",
            )
        with metric_cols[2]:
            st.metric(label="Compliant", value=summary["compliant_count"])
        with metric_cols[3]:
            st.metric(label="Analysis Errors", value=summary.get("error_count", 0))

        status_cols = st.columns(len(EvidenceStatus))
        for col, status in zip(status_cols, EvidenceStatus):
            col.metric(status.value, by_status.get(status.value, 0))

        # --- BREAKDOWN BY CATEGORY ---
        st.divider()
        st.subheader("Breakdown by Category")

        category_cols = st.columns(2)

        with category_cols[0]:
            st.write("**By Type:**")
            by_category = summary["by_category"]
            category_data = []
            for category, stats in by_category.items():
                total = stats["compliant"] + stats["gaps"]
                compliance = (stats["compliant"] / total * 100) if total > 0 else 0
                category_data.append({
                    "Type": category,
                    "Compliant": stats["compliant"],
                    "Gaps": stats["gaps"],
                    "Analysis Errors": stats.get("errors", 0),
                    "Compliance %": f"{compliance:.1f}%",
                })
            st.dataframe(pd.DataFrame(category_data), use_container_width=True, hide_index=True)

        with category_cols[1]:
            st.write("**By Section:**")
            by_section = summary["by_section"]
            section_data = []
            for section, stats in by_section.items():
                total = stats["compliant"] + stats["gaps"]
                compliance = (stats["compliant"] / total * 100) if total > 0 else 0
                section_data.append({
                    "Section": section[:25],
                    "Compliant": stats["compliant"],
                    "Gaps": stats["gaps"],
                    "Analysis Errors": stats.get("errors", 0),
                    "Compliance %": f"{compliance:.1f}%",
                })
            st.dataframe(pd.DataFrame(section_data), use_container_width=True, hide_index=True)

        # --- INTERACTIVE FILTERING ---
        st.divider()
        st.subheader("Detailed Results")

        filter_options = ["All", *[s.value for s in EvidenceStatus], "Gaps Only"]
        current_filter = st.selectbox(
            "Filter by status",
            options=filter_options,
            index=filter_options.index(st.session_state.gap_filter_status)
            if st.session_state.gap_filter_status in filter_options else 0,
            key="gap_filter_select",
        )
        st.session_state.gap_filter_status = current_filter

        gap_values = {s.value for s in GAP_STATUSES}
        if current_filter == "All":
            filtered_results = results
        elif current_filter == "Gaps Only":
            filtered_results = [r for r in results if r.status in gap_values]
        else:
            filtered_results = [r for r in results if r.status == current_filter]

        st.info(f"Showing {len(filtered_results)} of {len(results)} controls")

        # --- STRUCTURED DETAIL VIEW ---
        for result in filtered_results:
            icon = _STATUS_ICONS.get(result.status, "•")
            header = f"{icon} {result.id} — {result.name} · {result.status}"
            with st.expander(header, expanded=False):
                st.markdown(f"**Status (AI):** {result.status}")
                st.markdown(f"**Requirement coverage:** {result.requirement_coverage}")
                st.markdown(f"**Requirement:** {result.requirement}")
                st.markdown("**AI reasoning:**")
                st.write(result.reasoning or result.gapComment or "—")

                st.markdown("**Source evidence (verified quotations):**")
                if result.evidence:
                    for passage in result.evidence:
                        st.markdown(
                            f"> “{passage.quote}”\n\n"
                            f"> — {passage.source_document}, page {passage.page} "
                            f"({passage.evidence_type.value})"
                        )
                elif result.evidenceCitation:
                    st.markdown(f"> {result.evidenceCitation}")
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

        # --- CSV EXPORT (shared 21-column schema) ---
        st.divider()
        st.subheader("Export Results")

        from gap_analyzer import export_results_to_dict

        export_rows = export_results_to_dict(filtered_results)
        df_export = pd.DataFrame(export_rows)
        csv_buffer = df_export.to_csv(index=False)

        st.download_button(
            label=f"Download {current_filter} Results (CSV)",
            data=csv_buffer,
            file_name=f"ISO27001_Gap_Analysis_{current_filter.replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        # --- RESET ANALYSIS ---
        st.divider()

        if st.button("Run New Analysis", use_container_width=True):
            st.session_state.gap_analysis_results = None
            st.session_state.gap_analysis_summary = None
            st.session_state.gap_analysis_running = False
            st.session_state.gap_filter_status = "All"
            st.rerun()


def create_gap_analysis_integration(extracted_text: str, model, active_controls=None, pages=None):
    """Wrapper for integrating the gap analysis tab into the main app."""
    render_gap_analysis_tab(extracted_text, model, active_controls=active_controls, pages=pages)


def export_results_to_csv(results: List, current_filter: str = "All") -> str:
    """Convert gap analysis results to the shared 21-column CSV string."""
    try:
        from gap_analyzer import export_results_to_dict

        rows = export_results_to_dict(results)
        df = pd.DataFrame(rows)
        return df.to_csv(index=False)
    except Exception as e:
        raise ValueError(f"Failed to export results to CSV: {e}")
