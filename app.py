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
"You are an ISO 27001 Auditor. Analyze the text and find evidence for ONLY these 5 controls: "
"A.5.17 (Auth), A.8.10 (Data Deletion), A.5.1 (Policies), A.7.2 (Training), A.8.1 (Endpoints). "
"Return a JSON list: [{'control_id': '...', 'finding': '...', 'evidence': '...'}]"
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

st.title("IsoFlowAI — Automated Auditor")

# SIDEBAR
with st.sidebar:
st.success("✅ Logged In")
st.markdown("---")

secret_key = st.secrets.get("GEMINI_API_KEY", "")
api_key = secret_key # Always use the secret key directly

# Set your preferred model by default
model_choice = "Auto (list models)" 

# Set your standard OCR settings
ocr_threshold_chars = 50
ocr_dpi = 200
ocr_lang = "eng"
poppler_path = None
        
# MAIN INTERFACE
st.info("💡 Upload your policy PDFs below. IsoFlow will automatically discover and map internal controls to ISO 27001:2022 Annex A.")
files = st.file_uploader("Upload Evidence (PDF)", type=["pdf"], accept_multiple_files=True)

# Note: 'question' is no longer needed for dynamic mapping, so we use a generic check
run = st.button("Run Automated Mapping", type="primary", disabled=not files)

if not run:
return

if not api_key:
st.error("⚠️ Please enter your Gemini API Key.")
return

chosen_model = choose_model(api_key, model_choice)
all_rows: List[AuditRow] = []
progress = st.progress(0)

# START MAPPING LOOP
for i, f in enumerate(files):
progress.progress((i) / max(len(files), 1))
        
try:
pdf_bytes = f.getvalue()
# Ensure you removed @st.cache_data from extract_pdf_text for privacy
doc_text, used_ocr = extract_pdf_text(
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
            
# Use the new dynamic mapping function we defined earlier
mappings = ask_gemini_mapper(
api_key=api_key,
model_name=chosen_model,
document_text=doc_text
)
            
for m in mappings:
# Add filename to the ID column for the final report
m.filename = f"{m.filename} | {f.name}"
            
all_rows.extend(mappings)

# Cleanup memory
del pdf_bytes
del doc_text

except Exception as e:
all_rows.append(AuditRow(filename=f.name, audit_finding="ERROR", evidence=_safe_str(e)))

progress.progress(1.0)
    
# Final RAM purge
import gc
gc.collect()

if all_rows:
st.success("✅ Mapping Complete")
df = pd.DataFrame([asdict(r) for r in all_rows])
# Rename columns for the final display
df.columns = ["Control ID | Source File", "Audit Finding / Discovery", "Evidence (Verbatim Quote)"]
        
st.subheader("ISO 27001:2022 Annex A Mapping Report")
st.dataframe(df, use_container_width=True)
        
csv = df.to_csv(index=False).encode('utf-8')                                    
st.download_button("Download Mapping CSV", csv, "iso_annex_a_report.csv", "text/csv")

all_rows.clear() # Clear the list of results
gc.collect()
    
st.markdown("---")
st.caption("🛡️ **Security Note:** IsoFlow uses a stateless architecture. Documents are processed in volatile memory and purged immediately after analysis. No data is stored on our servers.")

if __name__ == "__main__":
main()
