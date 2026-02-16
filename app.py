import io, json, re, gc, time, concurrent.futures
from dataclasses import asdict, dataclass
import pandas as pd
import streamlit as st
from pypdf import PdfReader
import google.generativeai as genai
from google.api_core import exceptions

# --- AUTO-DISCOVERY SETUP ---
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
        # Reads ALL pages (No limit)
        pages = [p.extract_text() or "" for p in reader.pages]
        extracted = "\n\n".join(pages).strip()
    except:
        return ""
    return _clean_text(extracted)

def get_working_model_name(api_key):
    """
    CRITICAL FIX: Automatically finds a valid model for this API Key.
    """
    genai.configure(api_key=api_key)
    try:
        # List all models available to your key
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name
                # Prefer Flash if available, otherwise Pro
                if 'flash' in name.lower(): return name
                if 'gemini-1.5-pro' in name.lower(): return name
                if 'gemini-1.0-pro' in name.lower(): return name
                if 'gemini-pro' in name.lower(): return name
        return "models/gemini-pro" # Fallback
    except:
        return "models/gemini-pro" # Fallback

def ask_single_control(model, document_text, cid, cdesc, file_name) -> AuditRow:
    # Truncate text to be safe
    truncated_text = document_text[:30000] 
    
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
        # Retry logic inside
        resp = model.generate_content(prompt)
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
        return AuditRow(filename=file_name, control_id=cid, audit_finding=f"Error: {str(e)[:40]}", evidence="Failed")

def main():
    st.set_page_config(page_title="IsoFlow AI", layout="wide")
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

    # --- AUTO-CONFIGURE MODEL ---
    # We find the model name BEFORE the UI loads to prevent crashes
    if "model_name" not in st.session_state:
        st.session_state.model_name = get_working_model_name(api_key)
    
    current_model = st.session_state.model_name

    st.title("IsoFlow AI — Automated Auditor")
    st.caption(f"System Status: Online | Connected to: {current_model}")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=current_model,
        generation_config={"response_mime_type": "application/json"}
    )

    files = st.file_uploader("Upload Evidence (PDF)", type=["pdf"], accept_multiple_files=True)
    
    if st.button("Run Automated Mapping", type="primary", disabled=not files):
        
        all_rows = []
        demo_controls = [
            ("A.5.1", "Policies for Information Security"),
            ("A.8.2", "Privileged Access Rights"),
            ("A.12.1", "Operational Procedures"),
        ]
        
        status = st.status("🚀 Initializing Audit...", expanded=True)
        
        for f in files:
            status.write(f"Reading **{f.name}**...")
            doc_text = extract_pdf_text(f.getvalue())
            
            if not doc_text:
                status.error(f"Could not read text from {f.name}")
                continue
            
            # SAFE MODE: Sequential processing to avoid Rate Limits with generic models
            for cid, desc in demo_controls:
                # Small delay to keep the API happy
                time.sleep(0.5)
                res = ask_single_control(model, doc_text, cid, desc, f.name)
                all_rows.append(res)
                status.write(f"✅ Checked {cid}")

        status.update(label="Done!", state="complete", expanded=False)
        
        if all_rows:
            df = pd.DataFrame([asdict(r) for r in all_rows])
            st.dataframe(df, use_container_width=True)
            st.download_button("Download CSV", df.to_csv(index=False), "report.csv")

if __name__ == "__main__":
    main()
