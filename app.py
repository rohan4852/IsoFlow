import io, json, re, gc, time, random, concurrent.futures
from dataclasses import asdict, dataclass
import pandas as pd
import streamlit as st
from pypdf import PdfReader
import google.generativeai as genai
from google.api_core import exceptions
from excel_formatter import generate_excel_bytes

# --- CONFIGURATION ---
ISO_CONTROLS = [
    ("A.5.1", "Policies for information security"),
    ("A.8.2", "Privileged access rights"),
    ("A.9.1", "Access control policy"),
    ("A.10.1", "Cryptography policy"), 
    ("A.12.1", "Documented operating procedures"),
    ("A.13.1", "Network security management"),
]

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
    except:
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

# --- THE FIX: SMART RETRY LOGIC ---
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
        # Use the new Smart Retry function
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

def main():
    st.set_page_config(page_title="IsoFlowAI", layout="wide")
    st.markdown("<style>header {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)

    if "auth" not in st.session_state: st.session_state.auth = False
    
    try:
        stored_key = st.secrets.get("ACCESS_KEY", "")
        api_key = st.secrets.get("GEMINI_API_KEY", "")
    except:
        st.error("Missing Secrets")
        return

    if not st.session_state.auth:
        key = st.text_input("License Key", type="password")
        if st.button("Unlock"):
            if key == stored_key:
                st.session_state.auth = True
                st.rerun()
        return

    if "model_name" not in st.session_state:
        st.session_state.model_name = get_working_model_name(api_key)
    
    current_model = st.session_state.model_name

    st.title("IsoFlowAI — Automated Auditor")
    st.caption(f"System Status: Online | Connected to: {current_model}")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=current_model,
        generation_config={"response_mime_type": "application/json"}
    )

    files = st.file_uploader("Upload Evidence (PDF)", type=["pdf"], accept_multiple_files=True)
    
    if st.button("Run Full Audit", type="primary", disabled=not files):
        
        all_rows = []
        total_steps = len(files) * len(ISO_CONTROLS)
        current_step = 0
        
        status = st.status("🚀 Initializing Full Audit...", expanded=True)
        progress_bar = st.progress(0)
        
        for f in files:
            status.write(f"Reading **{f.name}**...")
            doc_text = extract_pdf_text(f.getvalue())
            
            if not doc_text:
                status.error(f"Could not read text from {f.name}")
                continue
            
            for cid, desc in ISO_CONTROLS:
                status.write(f"🔍 Checking **{cid}**...")
                
                # Check control with auto-retry
                res = ask_single_control(model, doc_text, cid, desc, f.name)
                all_rows.append(res)
                
                current_step += 1
                progress_bar.progress(current_step / total_steps)
                
                # BASE DELAY: Wait 1 second between requests to be safe
                time.sleep(1.0) 

        status.update(label="✅ Audit Complete!", state="complete", expanded=False)
        progress_bar.empty()
        
        if all_rows:
            df = pd.DataFrame([asdict(r) for r in all_rows])
            
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
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download Report (CSV)", csv, "report.csv", "text/csv")
            # Once the AI is done and report.csv exists, show the download button:
            st.success("Analysis Complete!")
            # Generate the beautiful Excel file in memory
            excel_data = generate_excel_bytes('report.csv')

           # Show the Streamlit Download Button
           st.download_button(
           label="📊 Download Enterprise Excel Report",
           data=excel_data,
           file_name="IsoFlow_Audit_Report.xlsx",
           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

if __name__ == "__main__":
    main()
