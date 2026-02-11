import io
import json
import os
import re
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
    "You are a Senior IT Compliance Auditor (CISA/CISSP) specializing in SOC2 and ISO 27001 audits. "
    "Your task is to analyze the provided policy document text against an audit question.\n\n"
    "STRICT RULES:\n"
    "1. FACTUAL STRICTNESS: You must answer ONLY using facts explicitly stated in the provided text. Do not use prior knowledge or assumptions.\n"
    "2. EVIDENCE QUOTING: The 'evidence' field must be a VERBATIM copy-paste of the sentence from the text that supports your finding. Do not paraphrase.\n"
    "3. HANDLING GAPS: If the document does not explicitly address the question, the audit_finding must be 'Gaps Observed: Policy does not explicitly state...' and evidence must be 'EVIDENCE NOT FOUND'.\n"
    "4. TONE: Be direct, objective, and professional. Avoid fluff."
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

@st.cache_data(show_spinner=False)
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

def ask_gemini(*, api_key: str, model_name: str, document_text: str, question: str) -> AuditRow:
    genai.configure(api_key=api_key)

    # Clean model name if needed
    if model_name.startswith("models/"):
        model_name = model_name[len("models/") :]

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_PROMPT,
        generation_config={"response_mime_type": "application/json"}
    )

    user_prompt = (
        f"DOCUMENT CONTENT:\n{document_text}\n\n"
        f"AUDIT QUESTION:\n{question}\n\n"
        "INSTRUCTIONS:\n"
        "Analyze the document and return a JSON object with exactly two keys:\n"
        "1. \"audit_finding\": A summary of whether the control is met, partially met, or missing.\n"
        "2. \"evidence\": The exact sentence from the text proving the finding.\n"
        "If evidence is missing, set \"evidence\" to 'EVIDENCE NOT FOUND'."
    )

    try:
        resp = model.generate_content(user_prompt)
        parsed = json.loads(resp.text)
        return AuditRow(
            filename="", 
            audit_finding=parsed.get("audit_finding", "Error parsing finding"), 
            evidence=parsed.get("evidence", "EVIDENCE NOT FOUND")
        )
    except Exception as e:
        return AuditRow(
            filename="", 
            audit_finding="AI PROCESSING ERROR", 
            evidence=_safe_str(e)
        )

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

    # SIDEBAR
    with st.sidebar:
        st.success("✅ Logged In")
        st.markdown("---")
        st.header("Configuration")
        
        secret_key = st.secrets.get("GEMINI_API_KEY", "")
        placeholder_text = "✅ Key loaded from Secrets" if secret_key else "Enter GEMINI_API_KEY"
        
        user_key = st.text_input("API Key", type="password", placeholder=placeholder_text)
        api_key = user_key if user_key else secret_key

        # Restored Selection Dropdown so YOU can choose what works
        model_choice = st.selectbox(
            "Model",
            options=["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro", "Auto (list models)"],
            index=0,
        )

        st.subheader("OCR Settings")
        ocr_threshold_chars = st.number_input("OCR threshold", value=50)
        ocr_dpi = st.number_input("OCR DPI", value=200)
        ocr_lang = st.text_input("Language", value="eng")
        
        # Paths are handled by packages.txt on cloud, so we leave these blank defaults
        poppler_path = None

    # MAIN INTERFACE
    question = st.text_input("Audit Question", value="Does this document satisfy Control A.5.17 (Authentication)?")
    files = st.file_uploader("Upload Evidence (PDF)", type=["pdf"], accept_multiple_files=True)

    run = st.button("Run Analysis", type="primary", disabled=not (files and question.strip()))

    if not run:
        return

    if not api_key:
        st.error("⚠️ Please enter your Gemini API Key.")
        return

    chosen_model = choose_model(api_key, model_choice)
    rows: List[AuditRow] = []
    progress = st.progress(0)

    # ORIGINAL SEQUENTIAL LOOP (Safe & Stable)
    for i, f in enumerate(files):
        progress.progress((i) / max(len(files), 1))
        
        try:
            pdf_bytes = f.getvalue()
            doc_text, used_ocr = extract_pdf_text(
                pdf_bytes,
                filename=f.name,
                ocr_threshold_chars=int(ocr_threshold_chars),
                ocr_dpi=int(ocr_dpi),
                ocr_lang=ocr_lang,
                poppler_path=poppler_path,
            )

            if not doc_text:
                rows.append(AuditRow(filename=f.name, audit_finding="ERROR", evidence="No text found"))
                continue
            
            result = ask_gemini(
                api_key=api_key,
                model_name=chosen_model,
                document_text=doc_text,
                question=question.strip(),
            )
            result.filename = f.name
            rows.append(result)

        except Exception as e:
            rows.append(AuditRow(filename=f.name, audit_finding="ERROR", evidence=_safe_str(e)))

    progress.progress(1.0)

    if rows:
        st.success("Analysis Complete")
        df = pd.DataFrame([asdict(r) for r in rows])
        st.subheader("Audit Report")
        st.dataframe(df, use_container_width=True)
        st.download_button("Download CSV", df.to_csv(index=False), "report.csv", "text/csv")

if __name__ == "__main__":
    main()
