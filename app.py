import io, json, os, re, gc, concurrent.futures
from dataclasses import asdict, dataclass
from typing import List, Tuple, Optional
import pandas as pd
import streamlit as st
from pdf2image import convert_from_bytes # Kept your imports safe
import pytesseract # Kept your imports safe
import google.generativeai as genai
from pypdf import PdfReader

@dataclass
class AuditRow:
    filename: str
    audit_finding: str
    evidence: str

def _safe_str(exc: Exception) -> str:
    return str(exc)[:4000]

def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[\t\r ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_pdf_text(pdf_bytes, **kwargs) -> Tuple[str, bool]:
    extracted = ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        # SPEED FIX 1: Removed the [:2] limit. Gemini Flash is fast enough to read ALL pages.
        # We read the whole file now so you don't miss evidence.
        pages = [p.extract_text() or "" for p in reader.pages] 
        extracted = "\n\n".join(pages).strip()
    except:
        pass
    return _clean_text(extracted), False

# SPEED FIX 2: We pass the 'model' object IN, instead of creating it 100 times.
def ask_single_control(model, document_text, cid, cdesc) -> AuditRow:
    # prompt optimized for speed
    prompt = f"Find verbatim evidence for ISO 27001 Control {cid} ({cdesc}). Return JSON: {{'finding': '...', 'evidence': '...'}}\n\nText:\n{document_text}"
    
    try:
        resp = model.generate_content(prompt)
        text_resp = resp.text.replace("```json", "").replace("```", "")
        data = json.loads(text_resp)
        return AuditRow(filename=cid, audit_finding=data.get("finding", ""), evidence=data.get("evidence", ""))
    except:
        return AuditRow(filename=cid, audit_finding="Error", evidence="Not Found")

def main():
    st.set_page_config(page_title="IsoFlow AI", layout="wide")
    
    # Hide Header/Footer
    st.markdown("<style>header {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)

    # Auth logic
    if "auth" not in st.session_state: st.session_state.auth = False
    if not st.session_state.auth:
        key = st.text_input("License Key", type="password")
        if st.button("Unlock"):
            if key == st.secrets.get("ACCESS_KEY"):
                st.session_state.auth = True
                st.rerun()
        return

    st.title("IsoFlow AI — Automated Auditor")
    
    with st.sidebar:
        st.success("✅ Logged In")

    api_key = st.secrets.get("GEMINI_API_KEY")
    files = st.file_uploader("Upload Evidence (PDF)", type=["pdf"], accept_multiple_files=True)
    run = st.button("Run Automated Mapping", type="primary", disabled=not files)

    if run:
        all_rows = []
        
        # SPEED FIX 3: Initialize the engine ONCE here.
        # "gemini-1.5-flash" is 10x faster than "preview" models.
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash", 
            generation_config={"response_mime_type": "application/json", "temperature": 0}
        )

        demo_controls = [("A.5.17", "Auth"), ("A.8.10", "Deletion"), ("A.5.1", "Policy")]
        
        progress = st.progress(0)
        status_text = st.empty() # Added visual feedback
        
        for i, f in enumerate(files):
            progress.progress(i / len(files))
            status_text.text(f"Reading file: {f.name}...")
            
            doc_text, _ = extract_pdf_text(f.getvalue())
            
            if not doc_text:
                all_rows.append(AuditRow(f.name, "ERROR", "No text found"))
                continue

            status_text.text(f"Auditing {f.name}...")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # We pass 'model' to the function now
                futures = [executor.submit(ask_single_control, model, doc_text, cid, desc) for cid, desc in demo_controls]
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    res.filename = f"{res.filename} | {f.name}"
                    all_rows.append(res)
            
            gc.collect()

        progress.progress(1.0)
        status_text.text("Done!")
        
        if all_rows:
            df = pd.DataFrame([asdict(r) for r in all_rows])
            st.dataframe(df, use_container_width=True)
            st.download_button("Download CSV", df.to_csv(index=False), "report.csv")
            
    st.markdown("---")
    st.caption("🛡️ Stateless Architecture. No data is stored.")

if __name__ == "__main__":
    main()
