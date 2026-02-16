import io, json, re, gc, time, random, concurrent.futures
from dataclasses import asdict, dataclass
from typing import List, Tuple
import pandas as pd
import streamlit as st
from pypdf import PdfReader
import google.generativeai as genai
from google.api_core import exceptions

# --- CONFIGURATION ---
# We use the stable 1.5 Flash model
MODEL_NAME = "gemini-1.5-flash"

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
        # READ ALL PAGES (Essential for accuracy)
        pages = [p.extract_text() or "" for p in reader.pages]
        extracted = "\n\n".join(pages).strip()
    except Exception as e:
        return ""
    return _clean_text(extracted)

def ask_with_retry(model, prompt, retries=3):
    """
    Tries to call the API. If it fails (Rate Limit), waits and retries.
    """
    for attempt in range(retries):
        try:
            return model.generate_content(prompt)
        except exceptions.ResourceExhausted:
            # Hit Rate Limit -> Wait 2-5 seconds and try again
            time.sleep(2 + random.random() * 3)
            continue
        except Exception as e:
            # If it's another error, raise it immediately
            raise e
    raise Exception("Rate limit exceeded after retries")

def ask_single_control(model, document_text, cid, cdesc, file_name) -> AuditRow:
    prompt = f"""
    You are an ISO 27001 Auditor.
    Task: Find verbatim evidence for Control {cid} ({cdesc}).
    
    Rules:
    1. If found, return JSON: {{ "finding": "Compliant", "evidence": "Exact quote..." }}
    2. If NOT found, return JSON: {{ "finding": "Not Found", "evidence": "No evidence found" }}
    
    Text:
    {document_text[:30000]} 
    """
    # Limit text to 30k chars per chunk to prevent timeouts on huge files
    
    try:
        # Call with Smart Retry Logic
        resp = ask_with_retry(model, prompt)
        
        # Parse JSON safely
        text_resp = resp.text.replace("```json", "").replace("```", "")
        if "{" not in text_resp: raise Exception("Invalid JSON")
        
        data = json.loads(text_resp)
        return AuditRow(
            filename=file_name,
            control_id=cid,
            audit_finding=data.get("finding", "Check Manually"),
            evidence=data.get("evidence", "No evidence found")
        )
    except Exception as e:
        # RETURN THE ACTUAL ERROR so we can see what's wrong
        return AuditRow(filename=file_name, control_id=cid, audit_finding=f"Error: {str(e)[:50]}", evidence="Failed")

def main():
    st.set_page_config(page_title="IsoFlow AI", layout="wide")
    st.markdown("<style>header {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)

    if "auth" not in st.session_state: st.session_state.auth = False
    
    # Securely load keys
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

    st.title("IsoFlow AI — Automated Auditor")
    
    # Configure API ONCE
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
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
        
        status = st.status("🚀 Processing...", expanded=True)
        
        for f in files:
            status.write(f"Reading **{f.name}**...")
            doc_text = extract_pdf_text(f.getvalue())
            
            if not doc_text:
                status.error(f"Could not read text from {f.name}")
                continue
            
            # REDUCED WORKERS TO 2 to prevent Rate Limits
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(ask_single_control, model, doc_text, cid, desc, f.name) 
                    for cid, desc in demo_controls
                ]
                
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    all_rows.append(res)
                    status.write(f"✅ Checked {res.control_id}")

        status.update(label="Done!", state="complete", expanded=False)
        
        if all_rows:
            df = pd.DataFrame([asdict(r) for r in all_rows])
            st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    main()
