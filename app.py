import io
import json
import os
import re
import concurrent.futures
from dataclasses import asdict, dataclass
from typing import List

import pandas as pd
import streamlit as st
import google.generativeai as genai
from pdf2image import convert_from_bytes
from pypdf import PdfReader
import pytesseract

# --- CORE SETTINGS ---
SYSTEM_PROMPT = (
    "You are a strict ISO 27001 Lead Auditor. Analyze the provided text. "
    "Respond ONLY in valid JSON format with keys: 'audit_finding' and 'evidence'. "
    "Do not include any markdown formatting or extra text."
)

@dataclass
class AuditRow:
    filename: str
    audit_finding: str
    evidence: str

def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    return re.sub(r"\s+", " ", text).strip()

def extract_text_fast(file_bytes: bytes) -> str:
    """Hybrid: Fast Metadata Extract -> Fallback to Slow OCR."""
    text = ""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            text += page.extract_text() or ""
    except: pass
    
    if len(text.strip()) > 100:
        return _clean_text(text)

    # Fallback to OCR if PDF is a scanned image
    try:
        images = convert_from_bytes(file_bytes, dpi=200, fmt='jpeg') # JPEG + 200DPI = Speed
        ocr_parts = [pytesseract.image_to_string(img) for img in images]
        return _clean_text(" ".join(ocr_parts))
    except Exception as e:
        return f"Extraction Error: {str(e)}"

def run_worker(api_key: str, file_obj, question: str) -> AuditRow:
    """Thread worker: Forced Stable API Version."""
    try:
        content = extract_text_fast(file_obj.getvalue())
        if not content:
            return AuditRow(file_obj.name, "ERROR", "Could not read file.")

        # 1. FORCE THE STABLE API VERSION
        # We explicitly tell the SDK to use 'v1' to avoid the 'v1beta' 404 error.
        genai.configure(api_key=api_key, transport='rest')
        
        # 2. SIMPLIFIED MODEL SELECTION
        # We use the base names which are most compatible across versions.
        success = False
        response = None
        last_err = ""

        # Try Flash first for speed, then Pro for reliability.
        for m_name in ["gemini-1.5-flash", "gemini-1.5-pro"]:
            try:
                # We bypass the 'models/' prefix which is causing issues in your environment
                model = genai.GenerativeModel(model_name=m_name)
                
                # We combine the system prompt and user prompt to ensure JSON output
                full_prompt = (
                    f"System: {SYSTEM_PROMPT}\n\n"
                    f"Document Content: {content[:100000]}\n\n"
                    f"Audit Question: {question}"
                )
                
                response = model.generate_content(full_prompt)
                if response and response.text:
                    success = True
                    break
            except Exception as e:
                last_err = str(e)
                continue

        if not success:
            return AuditRow(file_obj.name, "API ERROR", f"Stable models not found. Check API Key permissions.")

        # 3. ROBUST JSON PARSING
        raw_text = response.text.strip()
        # Remove any markdown backticks the AI might add
        clean_json = re.sub(r"```json|```", "", raw_text).strip()
        
        try:
            parsed = json.loads(clean_json)
            return AuditRow(
                filename=file_obj.name,
                audit_finding=parsed.get("audit_finding", "N/A"),
                evidence=parsed.get("evidence", "NOT FOUND")
            )
        except:
            # If JSON parsing fails, return the first 500 chars of the response
            return AuditRow(file_obj.name, "Manual Review", clean_json[:500])

    except Exception as e:
        return AuditRow(file_obj.name, "ENGINE CRASH", str(e)[:150])
        

# --- UI LAYER ---
def main():
    st.set_page_config(page_title="IsoFlow AI", layout="wide")
    
    # Force Hacker Dark Theme
    st.markdown("""
        <style>
            .stApp { background-color: #050505; color: #d4d4d4; }
            .stTextInput input { background-color: #111 !important; color: #fff !important; border: 1px solid #333 !important; }
            .stButton>button { background-color: #2563eb !important; width: 100%; border: none !important; }
            [data-testid="stHeader"], [data-testid="stFooter"] { display: none; }
        </style>
    """, unsafe_allow_html=True)

    if "auth" not in st.session_state: st.session_state.auth = False
    if not st.session_state.auth:
        st.title("🔐 IsoFlow Pilot Access")
        key = st.text_input("License Key", type="password")
        if st.button("Unlock"):
            if key == st.secrets.get("ACCESS_KEY", "admin"):
                st.session_state.auth = True
                st.rerun()
        st.stop()

    st.title("IsoFlow // Turbo Auditor")
    
    with st.sidebar:
        st.header("⚡ Core")
        api_key = st.text_input("Gemini Key", type="password", value=st.secrets.get("GEMINI_API_KEY", ""))
        st.info("Mode: Parallel Multi-Threaded")

    question = st.text_input("Audit Question", value="Verify MFA requirements in this policy.")
    files = st.file_uploader("Upload Evidence", accept_multiple_files=True, type=['pdf'])

    if st.button("Run Instant Analysis", type="primary") and files:
        if not api_key: 
            st.error("API Key missing.")
            return

        results = []
        progress = st.progress(0)
        status = st.empty()

        # THE TURBO PART: Process 5 files at a time instead of 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(run_worker, api_key, f, question): f for f in files}
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                res = future.result()
                results.append(res)
                progress.progress((i + 1) / len(files))
                status.text(f"Processed: {res.filename}")

        df = pd.DataFrame([asdict(r) for r in results])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("Download Report", df.to_csv(index=False), "report.csv", "text/csv")

if __name__ == "__main__":
    main()
