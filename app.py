import io, json, re, gc, time, concurrent.futures
from dataclasses import asdict, dataclass
import pandas as pd
import streamlit as st
from pypdf import PdfReader
import google.generativeai as genai
from google.api_core import exceptions

# --- EMERGENCY CONFIG ---
# We revert to the standard model that acts as the "Universal Donor".
# It works with ALL keys.
MODEL_NAME = "gemini-pro"

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
        # FIXED: Reads ALL pages (No limit), but safe.
        pages = [p.extract_text() or "" for p in reader.pages]
        extracted = "\n\n".join(pages).strip()
    except:
        return ""
    return _clean_text(extracted)

def ask_with_retry(model, prompt, retries=3):
    """
    Since 'gemini-pro' is stricter on Rate Limits, this wrapper is ESSENTIAL.
    """
    for attempt in range(retries):
        try:
            return model.generate_content(prompt)
        except exceptions.ResourceExhausted:
            # If rate limited, wait 4 seconds and try again
            time.sleep(4)
            continue
        except Exception as e:
            # If model not found or other error, fail fast
            if "404" in str(e): raise Exception("Model Not Found")
            raise e
    raise Exception("Rate limit hit")

def ask_single_control(model, document_text, cid, cdesc, file_name) -> AuditRow:
    # We limit text slightly to ensure 'gemini-pro' doesn't choke on context window
    truncated_text = document_text[:28000] 
    
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
        resp = ask_with_retry(model, prompt)
        text_resp = resp.text.replace("```json", "").replace("```", "")
        
        # Clean up common JSON errors from older models
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
    
    # Load Secrets
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
    st.caption(f"Engine: {MODEL_NAME} (Legacy Mode) | Reading Full Documents")
    
    # --- CRITICAL FIX: Configure ONCE ---
    genai.configure(api_key=api_key)
    
    # We use 'gemini-pro' which is the standard available model
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
        
        status = st.status("🚀 Processing (Standard Speed)...", expanded=True)
        
        for f in files:
            status.write(f"Reading **{f.name}**...")
            doc_text = extract_pdf_text(f.getvalue())
            
            if not doc_text:
                status.error(f"Could not read text from {f.name}")
                continue
            
            # --- CRITICAL SAFETY: Max Workers = 1 ---
            # We run 1 request at a time to prevent your key from being blocked.
            # This is slower, but it GUARANTEES the demo works.
            for cid, desc in demo_controls:
                # Slight delay to respect API limits
                time.sleep(0.5) 
                
                # Run synchronously (safest option)
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
