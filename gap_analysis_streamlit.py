"""
ISO 27001:2022 Gap Analysis - Streamlit Frontend Interface

Interactive dashboard for displaying and exploring gap analysis results.

Features:
- Real-time analysis execution with progress tracking
- Summary statistics (compliance %, total controls, gaps)
- Interactive filtering (All / Compliant / Gaps Only)
- Dynamic CSV export for audit reports
- Responsive table rendering with formatted icons and evidence citations
- Session state management for result persistence

This module bridges the gap analysis engine with Streamlit UI components.
"""

import streamlit as st
import pandas as pd
from typing import List, Optional
from types import SimpleNamespace
from dataclasses import asdict


def render_gap_analysis_tab(extracted_text: str, model, active_controls=None):
    """
    Main frontend interface for ISO 27001:2022 gap analysis.
    
    Renders:
    - Summary statistics (compliance metrics)
    - Interactive data table with filtering and visual status indicators
    - Dynamic CSV export button
    - Visual status indicators with icons
    
    Args:
        extracted_text: Combined text from uploaded documents
        model: Configured Gemini model instance
    """
    
    # Import framework and analysis engine
    try:
        from iso27001_framework import ISO27001_FRAMEWORK
        from gap_analyzer import run_gap_analysis, compute_analysis_summary, AnalysisResult
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
    
    # Check if analysis has already been run
    if st.session_state.gap_analysis_results is None:
        
        # Display execution flow
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Gap Analysis Ready")
        
        with col2:
            if st.button("Start Analysis", type="primary", use_container_width=True):
                st.session_state.gap_analysis_running = True
                st.rerun()
        
        if st.session_state.gap_analysis_running:
            # Process gap analysis with status tracking
            with st.status("Analyzing document against ISO 27001:2022 framework...", expanded=True) as status:
                try:
                    st.write(f"Processing {len(extracted_text)} characters of document text...")
                    st.write(f"Evaluating {len(selected_framework)} controls from {framework_label}...")
                    
                    # Execute gap analysis
                    results = run_gap_analysis(
                        combined_text=extracted_text,
                        model=model,
                        framework=selected_framework
                    )
                    
                    if results:
                        # Compute summary statistics
                        summary = compute_analysis_summary(results)
                        
                        # Store in session state for persistence
                        st.session_state.gap_analysis_results = results
                        st.session_state.gap_analysis_summary = summary
                        
                        st.write(f"Analysis complete: {len(results)} controls evaluated")
                        status.update(
                            label="Gap Analysis Complete!",
                            state="complete",
                            expanded=False
                        )
                        
                        # Rerun to display results
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
        
        # --- SUMMARY STATISTICS ---
        st.divider()
        st.subheader("Compliance Summary")
        
        # Create metric cards
        metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
        
        with metric_col1:
            st.metric(
                label="Total Controls",
                value=summary["total_controls"],
                delta=None
            )
        
        with metric_col2:
            compliance_pct = summary["compliance_percentage"]
            st.metric(
                label="Compliance %",
                value=f"{compliance_pct:.1f}%",
                help="Calculated only from controls successfully classified as Compliant or Gap Detected."
            )
        
        with metric_col3:
            st.metric(
                label="Compliant",
                value=summary["compliant_count"],
                delta=None
            )
        
        with metric_col4:
            st.metric(
                label="Gaps Detected",
                value=summary["gap_count"],
                delta=None
            )

        with metric_col5:
            st.metric(
                label="Analysis Errors",
                value=summary.get("error_count", 0),
                help="Controls that could not be reliably evaluated. These are not counted as compliance gaps."
            )
        
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
                    "Compliance %": f"{compliance:.1f}%"
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
                    "Compliance %": f"{compliance:.1f}%"
                })
            st.dataframe(pd.DataFrame(section_data), use_container_width=True, hide_index=True)
        
        # --- INTERACTIVE FILTERING ---
        st.divider()
        st.subheader("Detailed Results")
        
        filter_cols = st.columns(5)
        
        with filter_cols[0]:
            if st.button("All Controls", use_container_width=True):
                st.session_state.gap_filter_status = "All"
                st.rerun()
        
        with filter_cols[1]:
            if st.button("Compliant Only", use_container_width=True):
                st.session_state.gap_filter_status = "Compliant"
                st.rerun()
        
        with filter_cols[2]:
            if st.button("Gaps Only", use_container_width=True):
                st.session_state.gap_filter_status = "Gap Detected"
                st.rerun()
        
        with filter_cols[3]:
            if st.button("Errors Only", use_container_width=True):
                st.session_state.gap_filter_status = "Analysis Error"
                st.rerun()

        with filter_cols[4]:
            if st.button("Reset Filter", use_container_width=True):
                st.session_state.gap_filter_status = "All"
                st.rerun()
        
        # Apply filter
        filtered_results = results
        current_filter = st.session_state.gap_filter_status
        
        if current_filter == "Compliant":
            filtered_results = [r for r in results if r.status == "Compliant"]
        elif current_filter == "Gap Detected":
            filtered_results = [r for r in results if r.status == "Gap Detected"]
        elif current_filter == "Analysis Error":
            filtered_results = [r for r in results if r.status == "Analysis Error"]
        
        # Display filter status
        if current_filter == "All":
            filter_label = f"Showing all {len(filtered_results)} controls"
        elif current_filter == "Compliant":
            filter_label = f"Showing {len(filtered_results)} compliant controls"
        elif current_filter == "Gap Detected":
            filter_label = f"Showing {len(filtered_results)} controls with gaps"
        else:
            filter_label = f"Showing {len(filtered_results)} controls with analysis errors"
        
        st.info(filter_label)
        
        # --- INTERACTIVE RESULTS TABLE WITH FORMATTED EVIDENCE/GAP ANALYSIS ---
        st.write("")
        
        # Render interactive table with dynamic columns
        for idx, result in enumerate(filtered_results):
            # Determine status icon and styling
            if result.status == "Compliant":
                status_icon = "✅"
                evidence_content = result.evidenceCitation
                evidence_label = "Evidence Found:"
                content_type = "compliant"
            elif result.status == "Gap Detected":
                status_icon = "⚠️"
                evidence_content = result.gapComment
                evidence_label = "Gap Analysis:"
                content_type = "gap"
            else:
                status_icon = "🛠️"
                evidence_content = result.gapComment
                evidence_label = "Analysis Error — Manual Review Required:"
                content_type = "error"
            
            # Create table row with columns: Control ID, Name, Status, Evidence/Gap
            col_id, col_name, col_status, col_evidence = st.columns([1, 2, 1.5, 3])
            
            with col_id:
                st.write(f"**{result.id}**")
            
            with col_name:
                st.write(result.name)
            
            with col_status:
                st.write(f"{status_icon} {result.status}")
            
            with col_evidence:
                # Render evidence/gap content in blockquote wrapper
                if content_type == "compliant":
                    st.markdown(f"> **{evidence_label}**\n\n> {evidence_content}")
                else:
                    st.markdown(f"> **{evidence_label}**\n\n> {evidence_content}")
            
            st.divider()
        
        # --- CSV EXPORT ---
        st.divider()
        st.subheader("Export Results")
        
        # Prepare CSV data
        csv_data = []
        for result in filtered_results:
            csv_data.append({
                "Control ID": result.id,
                "Control Name": result.name,
                "Category": result.category,
                "Section": result.section,
                "Requirement": result.requirement,
                "Status": result.status,
                "Evidence Citation": result.evidenceCitation,
                "Gap Analysis / Remediation": result.gapComment if result.status == "Gap Detected" else "",
                "Analysis Error / Manual Review": result.gapComment if result.status == "Analysis Error" else "",
            })
        
        df_export = pd.DataFrame(csv_data)
        csv_buffer = df_export.to_csv(index=False)
        
        # Create download button
        st.download_button(
            label=f"Download {current_filter} Results (CSV)",
            data=csv_buffer,
            file_name=f"ISO27001_Gap_Analysis_{current_filter.replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True
        )
        
        # --- RESET ANALYSIS ---
        st.divider()
        
        if st.button("Run New Analysis", use_container_width=True):
            st.session_state.gap_analysis_results = None
            st.session_state.gap_analysis_summary = None
            st.session_state.gap_analysis_running = False
            st.session_state.gap_filter_status = "All"
            st.rerun()


def create_gap_analysis_integration(extracted_text: str, model, active_controls=None):
    """
    Wrapper function for integrating gap analysis tab into main Streamlit app.
    
    This function is called from app.py to render the gap analysis interface
    within a tab alongside the main audit findings.
    
    Args:
        extracted_text: Combined document text from session state
        model: Configured Gemini model instance
    
    Example usage in app.py:
        with tab2:
            create_gap_analysis_integration(
                st.session_state.combined_text,
                model
            )
    """
    render_gap_analysis_tab(extracted_text, model, active_controls=active_controls)


def export_results_to_csv(results: List, current_filter: str = "All") -> str:
    """
    Convert gap analysis results to CSV format.
    
    Args:
        results: List of AnalysisResult objects
        current_filter: Filter description for filename
    
    Returns:
        CSV string ready for download
    """
    try:
        from gap_analyzer import AnalysisResult
        
        csv_data = []
        for result in results:
            csv_data.append({
                "Control ID": result.id,
                "Control Name": result.name,
                "Category": result.category,
                "Section": result.section,
                "Requirement": result.requirement,
                "Status": result.status,
                "Evidence Citation": result.evidenceCitation,
                "Gap Analysis / Remediation": result.gapComment if result.status == "Gap Detected" else "",
                "Analysis Error / Manual Review": result.gapComment if result.status == "Analysis Error" else "",
            })
        
        df = pd.DataFrame(csv_data)
        return df.to_csv(index=False)
    
    except Exception as e:
        raise ValueError(f"Failed to export results to CSV: {e}")
