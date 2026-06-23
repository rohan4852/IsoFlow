# IsoFlow Systems - Stateless AI Compliance Engine

IsoFlow Systems is a production-ready, highly optimized backend architecture designed to automate the mapping of unstructured enterprise policy documents directly into structured compliance frameworks such as ISO 27001 and SOC2. Built with security-first engineering, the platform employs a strict zero-retention data lifecycle, making it an ideal plug-and-play asset for established GRC platforms, cybersecurity firms, or enterprise software ecosystems.

---

## 🚀 Key Value Proposition for Acquirers

* **Build vs. Buy Advantage:** Bypasses 2–3 months of specialized R&D and senior engineering overhead.
* **Zero Data-Retention Liability:** Designed from the ground up to handle sensitive enterprise policies without storing any files, databases, or user artifacts.
* **1M+ High-Context Optimization:** Fine-tuned to ingest massive organizational files and process deep framework cross-referencing without token exhaustion or data fragmentation.
* **Verbatim Auditing (Anti-Hallucination):** Core prompt logic forces the engine to return only true, verified source quotes or explicitly flag gaps, ensuring audit-grade dependability.

---

## 🛠️ Technical Architecture & Data Flow
[User Document Upload]
│
▼ (TLS 1.3 Encryption in Transit)
[Streamlit UI Session Memory]
│
▼ (Ephemeral Memory Pass-Through)
[Stateless Logic Engine / Core Parsers] ───► [Zero-Retention Enterprise API Gateway]
│                                      (Gemini Enterprise / Anthropic)
▼
[Color-Coded Excel Audit Trail Generated]
│
▼ (Session Closure / Tab Exit)
[Memory Wipe / Pure Stateless Cleanup]


1. **Ingestion:** Supports `.pdf`, `.docx`, and `.txt` up to 200MB, as well as custom compliance matrices via `.csv`.
2. **Processing:** Ephemeral compute executes isolation mapping via RAM-only execution layers. 
3. **Export:** Generates a structured, styled Excel sheet detailing exact clause matching and gap analysis.
4. **Purge:** Zero persistence layer. No external database connections are established, ensuring a completely clean liability profile.

---

## 📦 Repository Structure

* `/ui` - Streamlit-based frontend implementation managing ephemeral user state and localized session variables.
* `/logic` - Core parsing scripts, multi-model prompt orchestration layers, framework mapping logic, and Excel export format engines.

---

## ⚙️ Local Development Setup

### 1. Environment Configuration
Clone this repository and navigate to the project directory:
```bash
git clone [https://github.com/rohan4852/IsoFlow.git](https://github.com/rohan4852/IsoFlow.git)
cd IsoFlow

