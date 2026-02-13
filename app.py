import io
import json
import os
import re
import gc
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pdf2image import convert_from_bytes
import pytesseract
import google.generativeai as genai

# Try importing pypdf, show error if missing
try:
    from pypdf import PdfReader
except ImportError as exc:
    st.error("Missing dependency 'pypdf'. Please install it.")
    st.stop()

# --- GLOBAL CONSTANTS & CLASSES ---

SYSTEM_PROMPT = (
    "You are a Lead ISO 27001:2022 Auditor. Your task is to perform 'Requirement Discovery' and 'Annex A Mapping'.\n\n"
    "STRICT RULES:\n"
    "1. DISCOVERY: Scan the text for every security requirement, rule, or internal control mentioned.\n"
    "2. MAPPING: Map each finding to the most relevant ISO 27001:2022 Annex A Control ID (e.g., A.5.1, A.8.10).\n"
    "3. EVIDENCE: Quote the EXACT VERBATIM sentence from the document for each finding.\n"
    "4. FORMAT: You MUST return a JSON LIST of objects exactly like this: "
    "[{\"control_id\": \"A.X.X\", \"finding\": \"Summary of policy rule\", \"evidence\": \"Verbatim quote\"}]"
)

@dataclass
class AuditRow:
    filename: str
    audit_finding: str
    evidence: str

def _safe_str(exc: BaseException) -> str:
    msg = f"{type(exc).__name__}: {exc}"
    return msg[:4000]

def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[\t\r ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_pdf_text(
    pdf_bytes: bytes,
    *,
    filename: str,
    ocr_threshold_chars: int,
    ocr_dpi: int,
    ocr_lang: str,
    poppler_path: Optional[str],
) -> Tuple[str, bool]:
    extracted = ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages: List[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            t = t.strip()
            if t:
                pages.append(t)
        extracted = "\n\n".join(pages).strip()
    except Exception:
        extracted = ""

    if len(extracted) >= ocr_threshold_chars:
        return _clean_text(extracted), False

    # OCR Fallback
    try:
        images = convert_from_bytes(
            pdf_bytes,
            dpi=ocr_dpi,
            fmt="png",
            poppler_path=poppler_path or None,
        )
        parts: List[str] = []
        for img in images:
            parts.append(pytesseract.image_to_string(img, lang=ocr_lang) or "")
        ocr_text = "\n".join(parts).strip()
        if ocr_text:
            return _clean_text(ocr_text), True
    except Exception:
        pass

    return _clean_text(extracted), True

def ask_gemini_mapper(*, api_key: str, model_name: str, document_text: str) -> List[AuditRow]:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_PROMPT,
        generation_config={"response_mime_type": "application/json"}
    )

    user_prompt = f"Analyze this document and map all internal controls found to ISO 27001:2022 Annex A:\n\n{document_text}"

    try:
        resp = model.generate_content(user_prompt)
        parsed_list = json.loads(resp.text)
        
        results = []
        for item in parsed_list:
            results.append(AuditRow(
                filename=item.get("control_id", "Unknown"), 
                audit_finding=item.get("finding", "No finding"), 
                evidence=item.get("evidence", "EVIDENCE NOT FOUND")
            ))
        return results
    except Exception as e:
        return [AuditRow(filename="Error", audit_finding="AI Processing Failed", evidence=_safe_str(e))]

def choose_model(api_key: str, preferred: str) -> str:
    if preferred != "Auto (list models)":
        return preferred
    genai.configure(api_key=api_key)
    try:
        for m in genai.list_models():
            methods = getattr(m, "supported_generation_methods", None) or []
            if "generateContent" in methods:
                return str(getattr(m, "name", "gemini-1.5-flash"))
    except Exception:
        pass
    return "gemini-1.5-flash"

# --- MAIN APPLICATION ---

def main() -> None:
    st.set_page_config(page_title="IsoFlow AI", layout="wide")

    # Branding Hider
    st.markdown("""
        <style>
            header {visibility: hidden !important;}
            [data-testid="stHeader"] {display: none !important;}
            footer {visibility: hidden !important;}
            .stFooter {display: none !important;}
            .block-container {padding-top: 1rem !important;}
        </style>
        """, unsafe_allow_html=True)

    # AUTH Check
    if "auth_status" not in st.session_state:
        st.session_state.auth_status = False

    if not st.session_state.auth_status:
        st.title("🔐 IsoFlow AI - Pilot Access")
        password = st.text_input("License Key", type="password")
        if st.button("Unlock Access"):
            if password == st.secrets.get("ACCESS_KEY", ""):
                st.session_state.auth_status = True
                st.rerun()
            else:
                st.error("❌ Incorrect License Key")
        st.stop()

    load_dotenv()

    st.title("IsoFlow AI — Automated Auditor")

    # --- SIDEBAR (Minimalist) ---
    with st.sidebar:
        st.success("✅ Logged In")

    # --- CONFIGURATION (Internal) ---
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    model_choice = "gemini-1.5-flash"
    ocr_threshold_chars = 50
    ocr_dpi = 200
    ocr_lang = "eng"
    poppler_path = None

    # --- MAIN INTERFACE ---
    st.info("💡 Upload your policy PDFs below. IsoFlow will automatically discover and map internal controls to ISO 27001:2022 Annex A.")
    files = st.file_uploader("Upload Evidence (PDF)", type=["pdf"], accept_multiple_files=True)

    run = st.button("Run Automated Mapping", type="primary", disabled=not files)

    if not run:
        return

    if not api_key:
        st.error("⚠️ Gemini API Key not found in secrets.")
        return

    chosen_model = choose_model(api_key, model_choice)
    all_rows: List[AuditRow] = []
    progress = st.progress(0)

    for i, f in enumerate(files):
        progress.progress((i) / max(len(files), 1))
        try:
            pdf_bytes = f.getvalue()
            doc_text, _ = extract_pdf_text(
                pdf_bytes,
                filename=f.name,
                ocr_threshold_chars=int(ocr_threshold_chars),
                ocr_dpi=int(ocr_dpi),
                ocr_lang=ocr_lang,
                poppler_path=poppler_path,
            )

            if not doc_text:
                all_rows.append(AuditRow(filename=f.name, audit_finding="ERROR", evidence="No text found"))
                continue
            
            st.info(f"🔍 Analyzing {f.name} for ISO controls...")
            mappings = ask_gemini_mapper(
                api_key=api_key,
                model_name=chosen_model,
                document_text=doc_text
            )
            
            for m in mappings:
                m.filename = f"{m.filename} | {f.name}"
            
            all_rows.extend(mappings)
            del pdf_bytes
            del doc_text

        except Exception as e:
            all_rows.append(AuditRow(filename=f.name, audit_finding="ERROR", evidence=_safe_str(e)))

    progress.progress(1.0)
    gc.collect()

    if all_rows:
        st.success("✅ Mapping Complete")
        df = pd.DataFrame([asdict(r) for r in all_rows])
        df.columns = ["Control ID | Source File", "Audit Finding / Discovery", "Evidence (Verbatim Quote)"]
        
        st.subheader("ISO 27001:2022 Annex A Mapping Report")
        st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Mapping CSV", csv, "iso_annex_a_report.csv", "text/csv")
        
        all_rows.clear()
        gc.collect()

        st.markdown("---")
        st.caption("🛡️ **Security Note:** IsoFlow uses a stateless architecture. Documents are processed in volatile memory and purged immediately after analysis. No data is stored on our servers.")

if __name__ == "__main__":
    main()
