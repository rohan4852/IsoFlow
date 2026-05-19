import io, json, re, gc, time, random, concurrent.futures
from dataclasses import asdict, dataclass
import pandas as pd
import streamlit as st
from pypdf import PdfReader
import google.generativeai as genai
from google.api_core import exceptions
from excel_formatter import generate_excel_bytes
from gap_analysis_streamlit import render_gap_analysis_tab
import os

@dataclass
class AuditRow:
    filename: str
    control_id: str
    audit_finding: str
    evidence: str

def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[\t\r ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_pdf_text(pdf_bytes) -> str:
    extracted = ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [p.extract_text() or "" for p in reader.pages]
        extracted = "\n\n".join(pages).strip()
    except Exception as e:
        return ""
    return _clean_text(extracted)

def get_working_model_name(api_key):
    genai.configure(api_key=api_key)
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name
                if 'flash' in name.lower(): return name
                if 'gemini-1.5-pro' in name.lower(): return name
                if 'gemini-pro' in name.lower(): return name
        return "models/gemini-pro"
    except:
        return "models/gemini-pro"

# --- SMART RETRY LOGIC ---
def ask_with_backoff(model, prompt, retries=3):
    """
    If the API blocks us, we wait and try again.
    """
    for i in range(retries):
        try:
            return model.generate_content(prompt)
        except Exception as e:
            if "429" in str(e) or "ResourceExhausted" in str(e):
                # RATE LIMIT HIT: Wait 5, 10, then 15 seconds
                wait_time = (i + 1) * 5
                time.sleep(wait_time)
                continue
            else:
                # If it's a real error (not speed), fail
                raise e
    raise Exception("Timed out")

def ask_single_control(model, document_text, cid, cdesc, file_name) -> AuditRow:
    truncated_text = document_text[:35000] 
    
    prompt = f"""
    You are an ISO 27001 Auditor.
    Task: Find verbatim evidence for Control {cid} ({cdesc}).
    
    Rules:
    1. If found, return JSON: {{ "finding": "Compliant", "evidence": "Exact quote..." }}
    2. If NOT found, return JSON: {{ "finding": "Not Found", "evidence": "No evidence found" }}
    
    Text:
    {truncated_text}
    """
    
    try:
        # Use the Smart Retry function
        resp = ask_with_backoff(model, prompt)
        
        text_resp = resp.text.replace("```json", "").replace("```", "")
        if "{" not in text_resp: raise Exception("Invalid JSON")
        
        data = json.loads(text_resp)
        return AuditRow(
            filename=file_name,
            control_id=cid,
            audit_finding=data.get("finding", "Manual Review"),
            evidence=data.get("evidence", "No evidence found")
        )
    except Exception as e:
        return AuditRow(filename=file_name, control_id=cid, audit_finding="Error", evidence="Processing Failed")


def process_audit(files_data, active_controls, model):
    """
    Helper function to run the multi-threaded extraction logic.
    files_data is a list of tuples: (filename, document_text)
    """
    all_rows = []
    total_steps = len(files_data) * len(active_controls)
    current_step = 0
    
    status = st.status("🚀 Initializing Full Audit...", expanded=True)
    progress_bar = st.progress(0)
    
    for filename, doc_text in files_data:
        status.write(f"Reading **{filename}**...")
        
        if not doc_text:
            status.error(f"Could not read text from {filename}")
            continue
            
        # The Engine Upgrade: Asynchronous Parallel Processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # 1. Submit all controls to be mapped at the exact same time
            future_to_control = {
                executor.submit(ask_single_control, model, doc_text, cid, desc, filename): cid 
                for cid, desc in active_controls
            }
            
            # 2. Catch them as they finish and update the UI instantly
            for future in concurrent.futures.as_completed(future_to_control):
                cid = future_to_control[future]
                res = future.result()
                all_rows.append(res)
                
                status.write(f"⚡ Extracted evidence for **{cid}**")
                
                current_step += 1
                safe_progress = min(current_step / total_steps, 1.0)
                progress_bar.progress(safe_progress)

    status.update(label="✅ Audit Complete!", state="complete", expanded=False)
    progress_bar.empty()
    return all_rows

def render_gap_analysis_tab(combined_text: str):
    """
    Renders the Gap Analysis tab using the combined document text.
    This function will be called when audit_completed is True.
    """
    st.subheader("🔍 Internal Audit Readiness & Gap Assessment Matrix")
    
    if not combined_text or combined_text.strip() == "":
        st.warning("No document text available for gap analysis.")
        return
    
    st.info(f"Analyzing {len(combined_text)} characters of document text against ISO 27001:2022 framework...")
    
    # Placeholder for future gap analysis rendering
    # This would integrate with GapAnalysisMatrix.tsx or Python-based rendering
    with st.expander("📊 Gap Analysis Results (Coming Soon)"):
        st.write("Gap analysis engine initialized. Full results will be displayed here.")
        st.text_area("Document Text Preview", combined_text[:1000] + "...", height=200, disabled=True)

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
    
    try:
        stored_key = st.secrets.get("ACCESS_KEY", "")
        api_key = st.secrets.get("GEMINI_API_KEY", "")
    except:
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
    
    current_model = st.session_state.model_name

    st.title("IsoFlow — Automated Auditor")
    st.caption("🟢 System Status: Online | Environment: Isolated RAM Compute (Zero-Retention)")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=current_model,
        generation_config={"response_mime_type": "application/json"}
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
                    # 1. Read the local dummy PDF
                    with open(dummy_pdf_path, "rb") as f:
                        dummy_pdf_bytes = f.read()
                    doc_text = extract_pdf_text(dummy_pdf_bytes)
                    
                    # 2. Read the local dummy CSV
                    df_dummy = pd.read_csv(dummy_csv_path)
                    dummy_controls = list(zip(df_dummy.iloc[:, 0], df_dummy.iloc[:, 1]))
                    
                    # 3. Process using the shared helper function
                    files_data = [("dummy_policy.pdf", doc_text)]
                    all_rows = process_audit(files_data, dummy_controls, model)
                    
                    if all_rows:
                        df = pd.DataFrame([asdict(r) for r in all_rows])
                        st.subheader("📋 Audit Findings (Demo Data)")
                        st.dataframe(
                            df, 
                            column_config={
                                "control_id": st.column_config.TextColumn("ID", width="small"),
                                "audit_finding": st.column_config.TextColumn("Status", width="small"),
                                "evidence": st.column_config.TextColumn("Verbatim Evidence", width="large"),
                                "filename": st.column_config.TextColumn("File", width="medium"),
                            },
                            use_container_width=True,
                            hide_index=True
                        )
                        
                        df.to_csv('demo_report.csv', index=False)
                        
                        try:
                            excel_data = generate_excel_bytes('demo_report.csv')
                            st.download_button(
                                label="📊 Download Enterprise Excel Report (Demo)",
                                data=excel_data,
                                file_name="Sample_SOC2_Mapping.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        except Exception as excel_err:
                            st.warning(f"Could not format Excel (check formatting script): {excel_err}")
                            
                except Exception as e:
                    st.error(f"Engine error: {e}")

    st.divider()

    # --- UI: UPLOAD MATRIX ---
    st.subheader("1. Or Upload Your Own Custom Matrix (SOC 1 / Custom)")
    matrix_file = st.file_uploader("Upload Matrix (CSV)", type=["csv"])

    active_controls = []
    if matrix_file is not None:
        df_matrix = pd.read_csv(matrix_file)
        active_controls = list(zip(df_matrix.iloc[:, 0], df_matrix.iloc[:, 1]))
        st.success(f"Successfully loaded {len(active_controls)} custom controls!")
    else:
        active_controls = [
            ("A.5.1", "Policies for information security"),
            ("A.8.2", "Privileged access rights"),
            ("A.9.1", "Access control policy"),
            ("A.10.1", "Cryptography policy"), 
            ("A.12.1", "Documented operating procedures"),
            ("A.13.1", "Network security management"),
        ]

    # --- UI: UPLOAD PDF ---
    st.subheader("2. Upload Policy Document")
    files = st.file_uploader("Upload Evidence (PDF)", type=["pdf"], accept_multiple_files=True)
    
    # --- BUTTON CLICK: EXECUTE AUDIT AND SAVE TO SESSION STATE ---
    if st.button("Run Full Audit", type="primary", disabled=not files):
        
        # Prepare data for processing
        files_data = []
        for f in files:
            doc_text = extract_pdf_text(f.getvalue())
            files_data.append((f.name, doc_text))
        
        # Process using the shared helper function
        all_rows = process_audit(files_data, active_controls, model)
        
        # Save results to session state
        if all_rows:
            st.session_state.all_rows = all_rows
            
            # Combine all document text for gap analysis
            combined_text = "\n\n".join([doc_text for _, doc_text in files_data])
            st.session_state.combined_text = combined_text
            
            # Mark audit as completed
            st.session_state.audit_completed = True
            
            # Trigger rerun to display persistent UI
            st.rerun()
    
    # --- PERSISTENT TAB RENDERING (SEPARATE TOP-LEVEL CHECK) ---
    if st.session_state.audit_completed:
        
        # Convert all_rows to DataFrame for display
        df = pd.DataFrame([asdict(r) for r in st.session_state.all_rows])
        
        # Create tabs
        tab1, tab2 = st.tabs(["📋 Audit Findings", "🔍 Gap Analysis"])
        
        with tab1:
            st.subheader("📋 Audit Findings")
            st.dataframe(
                df, 
                column_config={
                    "control_id": st.column_config.TextColumn("ID", width="small"),
                    "audit_finding": st.column_config.TextColumn("Status", width="small"),
                    "evidence": st.column_config.TextColumn("Verbatim Evidence", width="large"),
                    "filename": st.column_config.TextColumn("File", width="medium"),
                },
                use_container_width=True,
                hide_index=True
            )
            
            # Save the raw CSV for the formatter to use
            df.to_csv('report.csv', index=False)
            csv = df.to_csv(index=False).encode('utf-8')
            
            st.success("✅ Analysis Complete!")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button("📥 Download Raw Data (CSV)", csv, "report.csv", "text/csv")
            
            with col2:
                try:
                    # Generate the beautiful Excel file in memory
                    excel_data = generate_excel_bytes('report.csv')
                    st.download_button(
                        label="📊 Download Enterprise Excel Report",
                        data=excel_data,
                        file_name="IsoFlow_Audit_Report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as excel_err:
                    st.error(f"Excel formatting failed. Check excel_formatter.py. Error: {excel_err}")
            
            # Upsell to the paid version
            st.warning("🔒 Want to upload your own custom PDFs and run them on secure AWS servers? Purchase the Pro license.")
        
        with tab2:
    st.info("📌 Gap Analysis runs a systematic ISO 27001:2022 compliance assessment")
    render_gap_analysis_tab(
        extracted_text=st.session_state.combined_text,
        model=model
    )
        
        # Add a "Reset Audit" button to clear session state
        st.divider()
        if st.button("🔄 Reset & Start New Audit"):
            st.session_state.audit_completed = False
            st.session_state.all_rows = []
            st.session_state.combined_text = ""
            st.rerun()

if __name__ == "__main__":
    main()
