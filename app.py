import io, json, os, re, gc, concurrent.futures
from dataclasses import asdict, dataclass
from typing import List, Tuple, Optional
import pandas as pd
import streamlit as st
from pdf2image import convert_from_bytes
import pytesseract
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
        # DEMO SPEED FIX: Only read the first 2 pages
        pages = [p.extract_text() or "" for p in reader.pages[:2]] 
        extracted = "\n\n".join(pages).strip()
    except:
        pass
    return _clean_text(extracted), False

def ask_single_control(api_key, model_name, document_text, cid, cdesc) -> AuditRow:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=f"Find verbatim evidence for ISO 27001 Control {cid} ({cdesc}). Return JSON: {{'finding': '...', 'evidence': '...'}}",
        generation_config={"response_mime_type": "application/json", "temperature": 0}
    )
    try:
        resp = model.generate_content(f"Text:\n{document_text}")
        data = json.loads(resp.text)
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
        chosen_model = "gemini-3-flash-preview"
        demo_controls = [("A.5.17", "Auth"), ("A.8.10", "Deletion"), ("A.5.1", "Policy")]
        
        progress = st.progress(0)
        for i, f in enumerate(files):
            progress.progress(i / len(files))
            doc_text, _ = extract_pdf_text(f.getvalue())
            
            if not doc_text:
                all_rows.append(AuditRow(f.name, "ERROR", "No text found"))
                continue

            st.info(f"🚀 Mapping {f.name}...")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(ask_single_control, api_key, chosen_model, doc_text, cid, desc) for cid, desc in demo_controls]
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    res.filename = f"{res.filename} | {f.name}"
                    all_rows.append(res)
            
            gc.collect()

        progress.progress(1.0)
        if all_rows:
            df = pd.DataFrame([asdict(r) for r in all_rows])
            st.dataframe(df, use_container_width=True)
            st.download_button("Download CSV", df.to_csv(index=False), "report.csv")
            
    st.markdown("---")
    st.caption("🛡️ Stateless Architecture. No data is stored.")

if __name__ == "__main__":
    main()
