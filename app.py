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
try:
    from pypdf import PdfReader
except ImportError as exc:
    raise RuntimeError(
        "Missing dependency 'pypdf'. Install it with: pip install -r requirements.txt"
    ) from exc
import pytesseract
import google.generativeai as genai

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

    ocr_text = ocr_pdf_text(
        pdf_bytes,
        dpi=ocr_dpi,
        lang=ocr_lang,
        poppler_path=poppler_path,
    )
    ocr_text = (ocr_text or "").strip()
    if ocr_text:
        return _clean_text(ocr_text), True

    return _clean_text(extracted), True

@st.cache_data(show_spinner=False)
def ocr_pdf_text(
    pdf_bytes: bytes,
    *,
    dpi: int,
    lang: str,
    poppler_path: Optional[str],
) -> str:
    images = convert_from_bytes(
        pdf_bytes,
        dpi=dpi,
        fmt="png",
        poppler_path=poppler_path or None,
    )
    parts: List[str] = []
    for img in images:
        parts.append(pytesseract.image_to_string(img, lang=lang) or "")
    return "\n".join(parts)

def ask_gemini(*, api_key: str, model_name: str, document_text: str, question: str) -> AuditRow:
    genai.configure(api_key=api_key)

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
    # 1. PAGE CONFIG
    st.set_page_config(page_title="AuditBot", layout="wide")
    
    s# --- CSS: Hide Header & Footer, Keep Sidebar ---
    st.markdown("""
        <style>
            /* 1. Hide the top header (Hamburger menu & Red/Orange bar) */
            [data-testid="stHeader"] {
                display: none;
            }
            
            /* 2. Hide the "Made with Streamlit" footer */
            footer {
                visibility: hidden;
            }
            
            /* 3. OPTIONAL: Remove whitespace at top of page where header was */
            .block-container {
                padding-top: 1rem;
            }
        </style>
        """, unsafe_allow_html=True)
    # --- PASSWORD GATE (CENTER SCREEN) ---
    # This puts the login box right in the middle of the page
    if "auth_status" not in st.session_state:
        st.session_state.auth_status = False

    if not st.session_state.auth_status:
        st.title("🔐 AuditBot Login")
        st.write("This is a restricted pilot tool for ISO 27001 auditing.")
        
        password = st.text_input("Enter License Key", type="password")
        
        if st.button("Unlock Access"):
            if password == "TRIAL-2026":
                st.session_state.auth_status = True
                st.rerun()  # Refresh the page to load the tool
            else:
                st.error("❌ Incorrect License Key")
        
        # Stop the app here if not logged in
        st.stop()

    # --- MAIN APP (Only loads after unlock) ---
    load_dotenv()
    if (not os.path.exists(".env")) and os.path.exists(".env.example"):
        load_dotenv(".env.example")

    st.title("AuditBot — Compliance Auditor")

    # 3. SIDEBAR CONFIG
    with st.sidebar:
        st.success("✅ Logged In")
        st.markdown("---")
        st.header("Configuration")
        
        secret_key = os.getenv("GEMINI_API_KEY")
        placeholder_text = "✅ Key loaded from Secrets" if secret_key else "Enter GEMINI_API_KEY"
        
        user_key = st.text_input(
            "API Key",
            type="password",
            placeholder=placeholder_text,
            help="If you leave this empty, the app uses the secure system key."
        )
        api_key = user_key if user_key else secret_key

        model_choice = st.selectbox(
            "Model",
            options=["gemini-1.5-flash", "gemini-pro", "Auto (list models)"],
            index=0,
        )

        st.subheader("OCR (fallback)")
        ocr_threshold_chars = st.number_input(
            "OCR fallback threshold (chars)",
            min_value=0, max_value=10000, value=50, step=10
        )
        ocr_dpi = st.number_input("OCR DPI", min_value=100, max_value=600, value=300, step=50)
        ocr_lang = st.text_input("Tesseract language", value="eng")

        tessdata_prefix = st.text_input("TESSDATA_PREFIX", value=os.getenv("TESSDATA_PREFIX", ""))
        tesseract_cmd = st.text_input("Tesseract path", value=os.getenv("TESSERACT_CMD", ""))
        poppler_path = st.text_input("Poppler path", value=os.getenv("POPPLER_PATH", ""))

    if tessdata_prefix: os.environ["TESSDATA_PREFIX"] = tessdata_prefix
    if tesseract_cmd: pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    # 4. MAIN INTERFACE
    question = st.text_input("Audit question", value="What are the benefits for the Development Bank of Japan?")
    files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)

    run = st.button("Run Audit", type="primary", disabled=not (files and question.strip()))

    if not run:
        st.caption("Tip: For scanned PDFs, ensure Tesseract + Poppler are installed.")
        return

    if not api_key or not api_key.strip():
        st.error("Please enter your GEMINI_API_KEY in the sidebar.")
        return

    chosen_model = choose_model(api_key, model_choice)
    rows: List[AuditRow] = []
    progress = st.progress(0)

    for i, f in enumerate(files):
        progress.progress((i) / max(len(files), 1))
        try:
            pdf_bytes = f.getvalue()
            doc_text, used_ocr = extract_pdf_text(
                pdf_bytes,
                filename=f.name,
                ocr_threshold_chars=int(ocr_threshold_chars),
                ocr_dpi=int(ocr_dpi),
                ocr_lang=ocr_lang.strip() or "eng",
                poppler_path=poppler_path.strip() or None,
            )

            if not doc_text:
                raise RuntimeError("No text could be extracted.")

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

    df = pd.DataFrame([asdict(r) for r in rows])
    df = df.rename(columns={"filename": "Filename", "audit_finding": "Audit Finding", "evidence": "Evidence"})

    st.subheader("Results")
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "Download Report (CSV)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="audit_report.csv",
        mime="text/csv",
    )

if __name__ == "__main__":
    main()