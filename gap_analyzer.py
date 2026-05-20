"""
ISO 27001:2022 Gap Analysis Engine

Core orchestration layer for evaluating extracted document text against
the complete ISO 27001:2022 framework (Clauses 4-10 and Annex A Controls).

This module implements:
- Systematic control evaluation
- Verbatim evidence extraction (no hallucinations)
- Gap detection with root cause analysis
- Exponential backoff retry logic for API rate limits
- JSON validation for LLM responses
- Zero-database architecture (stateless, volatile memory)
- Parallel control evaluation with ThreadPoolExecutor (max_workers=10)

Source: ISO 27001:2022 Internal Audit Checklist (CIC)
"""

import json
import time
from dataclasses import dataclass
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import google.generativeai as genai


@dataclass
class AnalysisResult:
    """
    Immutable result of analyzing a single control against document text.
    
    Attributes:
        id: Control identifier (e.g., "4.1", "A.5.15")
        name: Short name of the control/clause
        category: "Clause" or "Annex A"
        section: Logical section grouping
        requirement: Official requirement description
        status: "Compliant" or "Gap Detected"
        evidenceCitation: Verbatim quote from document (empty if Gap Detected)
        gapComment: Explanation of missing element (empty if Compliant)
    """
    id: str
    name: str
    category: str
    section: str
    requirement: str
    status: str  # "Compliant" | "Gap Detected"
    evidenceCitation: str
    gapComment: str


# ============================================================================
# SYSTEM PROMPT & EXECUTION INSTRUCTIONS
# ============================================================================

SYSTEM_PROMPT_TEMPLATE = """You are a strict ISO 27001:2022 Compliance Auditor performing gap analysis.

CRITICAL RULES:
1. VERBATIM EXTRACTION ONLY: If evidence of compliance is found, extract the EXACT, word-for-word text snippet from the provided document. Do NOT paraphrase, summarize, or interpret.
2. STRICT MATCHING: Match the control requirement against the actual document text. If the text does not directly address the requirement, do NOT force a compliance decision.
3. NO HALLUCINATION: If the document does not contain evidence of compliance, acknowledge this explicitly and identify what specific element is missing.
4. GAP ANALYSIS: When a gap is detected, explain clearly and concisely what critical element or control statement is absent from the document relative to the ISO 27001:2022 standard.

RESPONSE FORMAT:
Return ONLY valid JSON (no markdown, no backticks) with this exact structure:
{{
  "status": "Compliant" or "Gap Detected",
  "evidence_citation": "EXACT verbatim quote from document or empty string",
  "gap_comment": "Clear explanation of missing element or empty string"
}}

Ensure JSON is valid and parseable."""

CONTROL_EVALUATION_TEMPLATE = """
CONTROL TO EVALUATE:
ID: {control_id}
Name: {control_name}
Requirement: {requirement_text}

DOCUMENT TEXT FOR ANALYSIS:
{document_text}

Task: Analyze the document text above. Determine if this control requirement is met.

If compliance evidence exists in the text:
- Extract the EXACT, verbatim sentence or paragraph that demonstrates compliance
- Return status "Compliant"

If no evidence exists or requirement is not addressed:
- Identify the specific element that is missing
- Return status "Gap Detected"
- Explain what aspect of the requirement is not covered

Remember: Only return valid JSON. Do NOT add markdown or extra text."""


# ============================================================================
# EXPONENTIAL BACKOFF RETRY LOGIC
# ============================================================================

def ask_with_backoff(model, prompt: str, max_retries: int = 3) -> Optional[str]:
    """
    Execute a Gemini API call with exponential backoff for rate limiting.
    
    Handles 429 (Too Many Requests) and ResourceExhausted errors gracefully.
    Thread-safe for concurrent execution.
    
    Args:
        model: Generative model instance configured with API key
        prompt: Text prompt to send to the model
        max_retries: Maximum number of retry attempts (default: 3)
    
    Returns:
        Response text if successful, None if all retries failed
    
    Raises:
        Exception: If non-rate-limit error occurs or all retries exhausted
    """
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return response.text
        
        except Exception as e:
            error_str = str(e)
            
            # Check for rate limit errors
            is_rate_limit = (
                "429" in error_str or
                "ResourceExhausted" in error_str or
                "RESOURCE_EXHAUSTED" in error_str or
                "Too Many Requests" in error_str
            )
            
            if is_rate_limit:
                if attempt < max_retries - 1:
                    # Exponential backoff: 5s, 10s, 15s
                    wait_time = (attempt + 1) * 5
                    print(f"⏳ Rate limit hit. Waiting {wait_time}s before retry {attempt + 2}/{max_retries}...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Final retry failed
                    raise Exception(f"Rate limit exceeded after {max_retries} retries: {error_str}")
            else:
                # Non-rate-limit error: fail immediately
                raise Exception(f"API Error (non-recoverable): {error_str}")
    
    raise Exception("Unexpected state: retry loop completed without result")


# ============================================================================
# JSON VALIDATION & PARSING
# ============================================================================

def parse_gap_analysis_response(response_text: str) -> tuple[str, str, str]:
    """
    Parse and validate JSON response from LLM gap analysis.
    
    Args:
        response_text: Raw text response from model (should be JSON)
    
    Returns:
        Tuple of (status, evidence_citation, gap_comment)
        status: "Compliant" or "Gap Detected"
        evidence_citation: Verbatim text or empty string
        gap_comment: Gap explanation or empty string
    
    Raises:
        ValueError: If JSON is invalid or missing required fields
    """
    try:
        # Clean response: remove markdown fences if present
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        # Parse JSON
        if not cleaned or "{" not in cleaned:
            raise ValueError("Response does not contain valid JSON")
        
        data = json.loads(cleaned)
        
        # Validate required fields
        required_fields = ["status", "evidence_citation", "gap_comment"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        status = data.get("status", "").strip()
        evidence = data.get("evidence_citation", "").strip()
        gap_comment = data.get("gap_comment", "").strip()
        
        # Validate status value
        if status not in ["Compliant", "Gap Detected"]:
            raise ValueError(f"Invalid status value: {status}. Must be 'Compliant' or 'Gap Detected'")
        
        # Logical validation: Compliant should have evidence, Gap Detected should have comment
        if status == "Compliant" and not evidence:
            raise ValueError("Compliant status must include evidence_citation")
        if status == "Gap Detected" and not gap_comment:
            raise ValueError("Gap Detected status must include gap_comment")
        
        return status, evidence, gap_comment
    
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response: {e}")
    except Exception as e:
        raise ValueError(f"Response parsing failed: {e}")


# ============================================================================
# CORE GAP ANALYSIS ENGINE
# ============================================================================

def evaluate_single_control(
    model,
    document_text: str,
    control: object,
    max_truncation: int = 45000
) -> AnalysisResult:
    """
    Evaluate a single control requirement against document text.
    
    Implements strict LLM prompting to prevent hallucination:
    - Verbatim evidence extraction only
    - No interpretation or paraphrasing
    - Clear gap identification when requirements are not met
    
    Thread-safe for concurrent execution.
    
    Args:
        model: Configured Gemini model instance
        document_text: Full or processed document text to analyze
        control: ControlRequirement object from framework
        max_truncation: Maximum characters to send to model (default: 45000)
    
    Returns:
        AnalysisResult with status, evidence, and gap analysis
    """
    try:
        # Truncate document if necessary to avoid API limits
        truncated_text = document_text[:max_truncation]
        if len(document_text) > max_truncation:
            truncated_text += f"\n\n[... document truncated at {max_truncation} characters ...]"
        
        # Build control evaluation prompt
        prompt = CONTROL_EVALUATION_TEMPLATE.format(
            control_id=control.id,
            control_name=control.name,
            requirement_text=control.requirement,
            document_text=truncated_text
        )
        
        # Execute with exponential backoff (rate limit protected)
        response_text = ask_with_backoff(model, prompt, max_retries=3)
        
        if not response_text:
            raise Exception("Empty response from model")
        
        # Parse and validate response
        status, evidence, gap_comment = parse_gap_analysis_response(response_text)
        
        # Build result
        result = AnalysisResult(
            id=control.id,
            name=control.name,
            category=control.category,
            section=control.section,
            requirement=control.requirement,
            status=status,
            evidenceCitation=evidence,
            gapComment=gap_comment
        )
        
        return result
    
    except Exception as e:
        # Return error result
        error_msg = str(e)
        return AnalysisResult(
            id=control.id,
            name=control.name,
            category=control.category,
            section=control.section,
            requirement=control.requirement,
            status="Gap Detected",  # Treat errors as gaps
            evidenceCitation="",
            gapComment=f"Analysis error: {error_msg}. Manual review required."
        )


def run_gap_analysis(
    combined_text: str,
    model,
    framework: List[object],
    max_workers: int = 10
) -> List[AnalysisResult]:
    """
    Execute full gap analysis against all controls in the framework using parallel processing.
    
    This is the main orchestration function that:
    1. Uses ThreadPoolExecutor with max_workers threads for concurrent evaluation
    2. Evaluates each control against the document text in parallel
    3. Extracts verbatim evidence for compliant items
    4. Identifies gaps and root causes for non-compliant items
    5. Maintains result order matching framework order (thread-safe)
    6. Applies exponential backoff retry logic to all concurrent workers
    
    Args:
        combined_text: Full concatenated text from all uploaded documents
        model: Configured Gemini model instance
        framework: List of ControlRequirement objects from iso27001_framework
        max_workers: Number of concurrent threads (default: 10)
    
    Returns:
        List of AnalysisResult objects in framework order
    """
    
    if not combined_text or combined_text.strip() == "":
        # Return gaps for all controls if no text provided
        return [
            AnalysisResult(
                id=ctrl.id,
                name=ctrl.name,
                category=ctrl.category,
                section=ctrl.section,
                requirement=ctrl.requirement,
                status="Gap Detected",
                evidenceCitation="",
                gapComment="No document text provided for analysis."
            )
            for ctrl in framework
        ]
    
    print(f"\n🔍 Starting gap analysis for {len(framework)} controls...")
    print(f"📄 Document text length: {len(combined_text)} characters")
    print(f"⚡ Using {max_workers} concurrent threads for parallel evaluation")
    
    # Create a mapping of control ID to framework index for result ordering
    control_index_map = {ctrl.id: idx for idx, ctrl in enumerate(framework)}
    
    # Dictionary to store results indexed by control ID for thread-safe access
    results_dict = {}
    completed_count = 0
    
    # Execute controls in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks to the executor
        future_to_control = {
            executor.submit(evaluate_single_control, model, combined_text, control): control
            for control in framework
        }
        
        # Process completed tasks as they finish
        for future in as_completed(future_to_control):
            control = future_to_control[future]
            completed_count += 1
            
            try:
                result = future.result()
                results_dict[result.id] = result
                
                # Log result
                if result.status == "Compliant":
                    print(f"[{completed_count}/{len(framework)}] ✅ {control.id} - Compliant")
                else:
                    gap_preview = result.gapComment[:60].replace('\n', ' ')
                    print(f"[{completed_count}/{len(framework)}] ⚠️  {control.id} - Gap Detected: {gap_preview}...")
            
            except Exception as e:
                # Handle task execution errors
                error_result = AnalysisResult(
                    id=control.id,
                    name=control.name,
                    category=control.category,
                    section=control.section,
                    requirement=control.requirement,
                    status="Gap Detected",
                    evidenceCitation="",
                    gapComment=f"Task execution failed: {str(e)}. Manual review required."
                )
                results_dict[error_result.id] = error_result
                print(f"[{completed_count}/{len(framework)}] ❌ {control.id} - Task failed: {str(e)[:50]}...")
    
    # Reconstruct results list in original framework order (thread-safe)
    results = [results_dict[ctrl.id] for ctrl in framework]
    
    print(f"\n✅ Gap analysis complete!")
    print(f"   Total: {len(results)} controls")
    print(f"   Compliant: {sum(1 for r in results if r.status == 'Compliant')}")
    print(f"   Gaps: {sum(1 for r in results if r.status == 'Gap Detected')}")
    
    return results


# ============================================================================
# ANALYSIS SUMMARY & STATISTICS
# ============================================================================

def compute_analysis_summary(results: List[AnalysisResult]) -> dict:
    """
    Compute summary statistics from analysis results.
    
    Args:
        results: List of AnalysisResult objects
    
    Returns:
        Dictionary with compliance metrics
    """
    total = len(results)
    compliant = sum(1 for r in results if r.status == "Compliant")
    gaps = sum(1 for r in results if r.status == "Gap Detected")
    
    compliance_percentage = (compliant / total * 100) if total > 0 else 0
    
    by_section = {}
    for result in results:
        section = result.section
        if section not in by_section:
            by_section[section] = {"compliant": 0, "gaps": 0}
        
        if result.status == "Compliant":
            by_section[section]["compliant"] += 1
        else:
            by_section[section]["gaps"] += 1
    
    by_category = {}
    for result in results:
        category = result.category
        if category not in by_category:
            by_category[category] = {"compliant": 0, "gaps": 0}
        
        if result.status == "Compliant":
            by_category[category]["compliant"] += 1
        else:
            by_category[category]["gaps"] += 1
    
    return {
        "total_controls": total,
        "compliant_count": compliant,
        "gap_count": gaps,
        "compliance_percentage": round(compliance_percentage, 2),
        "by_section": by_section,
        "by_category": by_category,
    }


def filter_results_by_status(
    results: List[AnalysisResult],
    status: str
) -> List[AnalysisResult]:
    """
    Filter analysis results by compliance status.
    
    Args:
        results: List of AnalysisResult objects
        status: "Compliant" or "Gap Detected"
    
    Returns:
        Filtered list of results
    """
    return [r for r in results if r.status == status]


def filter_results_by_section(
    results: List[AnalysisResult],
    section: str
) -> List[AnalysisResult]:
    """
    Filter analysis results by section name.
    
    Args:
        results: List of AnalysisResult objects
        section: Section name to filter by
    
    Returns:
        Filtered list of results
    """
    return [r for r in results if r.section == section]


def export_results_to_dict(results: List[AnalysisResult]) -> List[dict]:
    """
    Convert AnalysisResult objects to dictionaries for JSON serialization.
    
    Args:
        results: List of AnalysisResult objects
    
    Returns:
        List of dictionaries
    """
    return [
        {
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "section": r.section,
            "requirement": r.requirement,
            "status": r.status,
            "evidenceCitation": r.evidenceCitation,
            "gapComment": r.gapComment,
        }
        for r in results
    ]


# ============================================================================
# MAIN EXECUTION EXAMPLE (for testing)
# ============================================================================

if __name__ == "__main__":
    """
    Example usage of the gap analysis engine.
    
    This demonstrates:
    - Importing framework
    - Configuring model
    - Running gap analysis with parallel processing (max_workers=10)
    - Computing statistics
    """
    print("=" * 70)
    print("ISO 27001:2022 Gap Analysis Engine")
    print("=" * 70)
    
    # Import framework
    try:
        from iso27001_framework import ISO27001_FRAMEWORK
        print(f"\n✅ Framework loaded: {len(ISO27001_FRAMEWORK)} controls")
    except ImportError as e:
        print(f"❌ Failed to import framework: {e}")
        exit(1)
    
    # Example usage (requires API key)
    print("\nTo use this engine in your application:")
    print("  1. Configure Gemini API with your key")
    print("  2. Call run_gap_analysis(combined_text, model, ISO27001_FRAMEWORK)")
    print("     - Default: 10 concurrent workers for optimal throughput")
    print("     - Customize: run_gap_analysis(..., max_workers=N)")
    print("  3. Process results with compute_analysis_summary()")
    
    print("\n" + "=" * 70)
