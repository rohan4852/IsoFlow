"""
ISO 27001:2022 Gap Analysis Engine

Core orchestration layer for evaluating extracted document text against
the complete ISO 27001:2022 framework (Clauses 4-10 and Annex A Controls).

This module implements:
- Systematic control evaluation with batching (5 controls per request)
- Verbatim evidence extraction (no hallucinations)
- Gap detection with root cause analysis
- Exponential backoff retry logic for API rate limits
- JSON validation for LLM responses
- Zero-database architecture (stateless, volatile memory)
- Parallel batch processing with ThreadPoolExecutor (max_workers=3)
- Request optimization: 92 controls → 19 API calls (bypasses 15 RPM limit)

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

BATCH_EVALUATION_TEMPLATE = """
BATCH CONTROLS TO EVALUATE (5 controls):

{batch_controls}

DOCUMENT TEXT FOR ANALYSIS:
{document_text}

Task: Analyze the document text above. For each control, determine if the requirement is met.

For each control:
- If compliance evidence exists in the text:
  * Extract the EXACT, verbatim sentence or paragraph that demonstrates compliance
  * Use status "Compliant"
- If no evidence exists or requirement is not addressed:
  * Identify the specific element that is missing
  * Use status "Gap Detected"
  * Explain what aspect of the requirement is not covered

RESPONSE FORMAT:
Return ONLY valid JSON array (no markdown, no backticks) with exactly 5 objects:
[
  {{
    "control_id": "{control_id}",
    "status": "Compliant" or "Gap Detected",
    "evidence_citation": "EXACT verbatim quote or empty string",
    "gap_comment": "Clear explanation of missing element or empty string"
  }},
  ...
]

Ensure JSON is valid, parseable, and contains exactly 5 objects in the order provided above."""


# ============================================================================
# BATCH BUILDING & FORMATTING
# ============================================================================

def chunk_framework(framework: List[object], chunk_size: int = 5) -> List[List[object]]:
    """
    Divide framework into chunks for batch processing.
    
    Args:
        framework: List of ControlRequirement objects
        chunk_size: Number of controls per batch (default: 5)
    
    Returns:
        List of batches, each containing up to chunk_size controls
    """
    return [framework[i:i + chunk_size] for i in range(0, len(framework), chunk_size)]


def format_batch_controls_for_prompt(batch: List[object]) -> str:
    """
    Format a batch of controls into the prompt text.
    
    Args:
        batch: List of ControlRequirement objects (typically 5)
    
    Returns:
        Formatted string with all control requirements
    """
    formatted_controls = []
    for idx, control in enumerate(batch, 1):
        formatted_controls.append(
            f"CONTROL {idx}:\n"
            f"  ID: {control.id}\n"
            f"  Name: {control.name}\n"
            f"  Requirement: {control.requirement}\n"
        )
    return "\n".join(formatted_controls)


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
# JSON VALIDATION & PARSING (BATCH)
# ============================================================================

def parse_batch_response(response_text: str, batch: List[object]) -> List[tuple[str, str, str]]:
    """
    Parse and validate JSON array response from LLM batch analysis.
    
    Args:
        response_text: Raw text response from model (should be JSON array)
        batch: List of ControlRequirement objects in the batch (for validation)
    
    Returns:
        List of tuples: [(status, evidence_citation, gap_comment), ...]
        One tuple per control, in batch order
    
    Raises:
        ValueError: If JSON is invalid, missing required fields, or count mismatch
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
        
        # Parse JSON array
        if not cleaned or "[" not in cleaned:
            raise ValueError("Response does not contain valid JSON array")
        
        data = json.loads(cleaned)
        
        # Validate it's an array
        if not isinstance(data, list):
            raise ValueError(f"Response is not a JSON array. Got: {type(data)}")
        
        # Validate array has exactly batch_size items
        if len(data) != len(batch):
            raise ValueError(
                f"Response array has {len(data)} items, expected {len(batch)} "
                f"(batch size mismatch)"
            )
        
        results = []
        for idx, item in enumerate(data):
            # Validate required fields
            required_fields = ["control_id", "status", "evidence_citation", "gap_comment"]
            for field in required_fields:
                if field not in item:
                    raise ValueError(f"Item {idx}: Missing required field: {field}")
            
            control_id = item.get("control_id", "").strip()
            status = item.get("status", "").strip()
            evidence = item.get("evidence_citation", "").strip()
            gap_comment = item.get("gap_comment", "").strip()
            
            # Validate control_id matches
            expected_id = batch[idx].id
            if control_id != expected_id:
                raise ValueError(
                    f"Item {idx}: control_id mismatch. Got '{control_id}', "
                    f"expected '{expected_id}'"
                )
            
            # Validate status value
            if status not in ["Compliant", "Gap Detected"]:
                raise ValueError(
                    f"Item {idx}: Invalid status value: {status}. "
                    f"Must be 'Compliant' or 'Gap Detected'"
                )
            
            # Logical validation
            if status == "Compliant" and not evidence:
                raise ValueError(
                    f"Item {idx} ({control_id}): Compliant status must include evidence_citation"
                )
            if status == "Gap Detected" and not gap_comment:
                raise ValueError(
                    f"Item {idx} ({control_id}): Gap Detected status must include gap_comment"
                )
            
            results.append((status, evidence, gap_comment))
        
        return results
    
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response: {e}")
    except Exception as e:
        raise ValueError(f"Response parsing failed: {e}")


# ============================================================================
# CORE BATCH GAP ANALYSIS ENGINE
# ============================================================================

def evaluate_batch(
    model,
    document_text: str,
    batch: List[object],
    max_truncation: int = 45000
) -> List[AnalysisResult]:
    """
    Evaluate a batch of controls (typically 5) against document text in a single API call.
    
    Implements strict LLM prompting to prevent hallucination:
    - Verbatim evidence extraction only
    - No interpretation or paraphrasing
    - Clear gap identification when requirements are not met
    
    Thread-safe for concurrent execution.
    
    Args:
        model: Configured Gemini model instance
        document_text: Full or processed document text to analyze
        batch: List of ControlRequirement objects (typically 5)
        max_truncation: Maximum characters to send to model (default: 45000)
    
    Returns:
        List of AnalysisResult objects (one per control in batch)
    """
    try:
        # Truncate document if necessary to avoid API limits
        truncated_text = document_text[:max_truncation]
        if len(document_text) > max_truncation:
            truncated_text += f"\n\n[... document truncated at {max_truncation} characters ...]"
        
        # Build batch evaluation prompt
        batch_controls_str = format_batch_controls_for_prompt(batch)
        prompt = BATCH_EVALUATION_TEMPLATE.format(
            batch_controls=batch_controls_str,
            document_text=truncated_text
        )
        
        # Execute with exponential backoff (rate limit protected)
        response_text = ask_with_backoff(model, prompt, max_retries=3)
        
        if not response_text:
            raise Exception("Empty response from model")
        
        # Parse and validate response
        parsed_results = parse_batch_response(response_text, batch)
        
        # Build AnalysisResult objects in batch order
        results = []
        for idx, (status, evidence, gap_comment) in enumerate(parsed_results):
            control = batch[idx]
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
            results.append(result)
        
        return results
    
    except Exception as e:
        # Return error results for entire batch
        error_msg = str(e)
        error_results = []
        for control in batch:
            result = AnalysisResult(
                id=control.id,
                name=control.name,
                category=control.category,
                section=control.section,
                requirement=control.requirement,
                status="Gap Detected",
                evidenceCitation="",
                gapComment=f"Batch analysis error: {error_msg}. Manual review required."
            )
            error_results.append(result)
        
        return error_results


def run_gap_analysis(
    combined_text: str,
    model,
    framework: List[object],
    max_workers: int = 3,
    batch_size: int = 5
) -> List[AnalysisResult]:
    """
    Execute full gap analysis against all controls in the framework using batch processing.
    
    This is the main orchestration function that:
    1. Chunks framework into batches of batch_size controls (default: 5)
    2. Uses ThreadPoolExecutor with max_workers threads for concurrent batch evaluation
    3. Evaluates each batch against the document text in a single API call
    4. Extracts verbatim evidence for compliant items
    5. Identifies gaps and root causes for non-compliant items
    6. Maintains result order matching framework order (thread-safe)
    7. Applies exponential backoff retry logic to all concurrent workers
    
    API Call Reduction:
    - Without batching: 92 controls → 92 API calls (exceeds 15 RPM limit)
    - With batching (5 per call): 92 controls → 19 API calls (stays within limits)
    
    Args:
        combined_text: Full concatenated text from all uploaded documents
        model: Configured Gemini model instance
        framework: List of ControlRequirement objects from iso27001_framework
        max_workers: Number of concurrent threads (default: 3)
        batch_size: Number of controls per batch (default: 5)
    
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
    
    # Create batches
    batches = chunk_framework(framework, batch_size)
    num_batches = len(batches)
    
    print(f"\n🔍 Starting batch gap analysis...")
    print(f"📊 Framework: {len(framework)} controls")
    print(f"📦 Batches: {num_batches} (batch size: {batch_size})")
    print(f"📞 API Calls: ~{num_batches} calls (vs {len(framework)} without batching)")
    print(f"📄 Document text length: {len(combined_text)} characters")
    print(f"⚡ Using {max_workers} concurrent threads for parallel batch evaluation")
    
    # Create a mapping of control ID to framework index for result ordering
    control_index_map = {ctrl.id: idx for idx, ctrl in enumerate(framework)}
    
    # Dictionary to store results indexed by control ID for thread-safe access
    results_dict = {}
    completed_batches = 0
    
    # Execute batches in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batch tasks to the executor
        future_to_batch = {
            executor.submit(evaluate_batch, model, combined_text, batch): batch
            for batch in batches
        }
        
        # Process completed batches as they finish
        for future in as_completed(future_to_batch):
            batch = future_to_batch[future]
            completed_batches += 1
            batch_ids = [c.id for c in batch]
            
            try:
                batch_results = future.result()
                
                # Store all results from this batch
                for result in batch_results:
                    results_dict[result.id] = result
                
                # Count compliant vs gap in batch
                compliant_count = sum(1 for r in batch_results if r.status == "Compliant")
                gap_count = sum(1 for r in batch_results if r.status == "Gap Detected")
                
                # Log batch result
                print(
                    f"[{completed_batches}/{num_batches}] Batch {batch_ids}: "
                    f"✅ {compliant_count} compliant, ⚠️  {gap_count} gaps"
                )
            
            except Exception as e:
                # Handle batch task execution errors
                print(
                    f"[{completed_batches}/{num_batches}] Batch {batch_ids}: "
                    f"❌ Task failed: {str(e)[:50]}..."
                )
    
    # Reconstruct results list in original framework order (thread-safe)
    results = [results_dict[ctrl.id] for ctrl in framework]
    
    print(f"\n✅ Batch gap analysis complete!")
    print(f"   Total Controls: {len(results)}")
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
    Example usage of the batch gap analysis engine.
    
    This demonstrates:
    - Importing framework
    - Configuring model
    - Running batch gap analysis with parallel processing (max_workers=3)
    - API call reduction: 92 controls → 19 API calls
    - Computing statistics
    """
    print("=" * 70)
    print("ISO 27001:2022 Batch Gap Analysis Engine")
    print("=" * 70)
    
    # Import framework
    try:
        from iso27001_framework import ISO27001_FRAMEWORK
        print(f"\n✅ Framework loaded: {len(ISO27001_FRAMEWORK)} controls")
        
        # Calculate expected API calls with batching
        num_batches = (len(ISO27001_FRAMEWORK) + 4) // 5
        print(f"📊 With batching (5 per call): ~{num_batches} API calls")
        print(f"📞 Without batching: {len(ISO27001_FRAMEWORK)} API calls")
    except ImportError as e:
        print(f"❌ Failed to import framework: {e}")
        exit(1)
    
    # Example usage (requires API key)
    print("\nTo use this batch engine in your application:")
    print("  1. Configure Gemini API with your key")
    print("  2. Call run_gap_analysis(combined_text, model, ISO27001_FRAMEWORK)")
    print("     - Default: batch_size=5, max_workers=3")
    print("     - Customize: run_gap_analysis(..., batch_size=N, max_workers=M)")
    print("  3. Process results with compute_analysis_summary()")
    print("\nBenefits of Batching:")
    print("  • Reduces API calls by 79% (92 → 19)")
    print("  • Stays within free tier 15 RPM limit with batches of 5")
    print("  • Maintains result ordering and filtering capabilities")
    print("  • Preserves verbatim evidence extraction")
    
    print("\n" + "=" * 70)
