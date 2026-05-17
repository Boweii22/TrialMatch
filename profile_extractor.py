import io
import time

from utils import MODEL, TOKENS, stream_response
from pdf_reader import pdf_to_text, pdf_to_images
from prompts import TEXT_EXTRACTION_PROMPT, EXTRACTION_PROMPT

# Keywords that signal clinically relevant lines anywhere in the document.
# Used by _smart_trim_pdf to pull high-value content from later pages.
_CLINICAL_KW = (
    'diagnosis', 'diagnosed', 'condition', 'disease', 'disorder', 'impression',
    'medication', 'prescribed', 'drug', 'dose', 'mg', 'tablet', 'capsule',
    'lab', 'result', 'hba1c', 'glucose', 'creatinine', 'egfr', 'cholesterol',
    'hemoglobin', 'platelet', 'sodium', 'potassium', 'wbc', 'rbc', 'bilirubin',
    'allerg', 'reaction', 'intolerant', 'contraindicated',
    'blood pressure', 'bp:', 'pulse', 'heart rate', 'temperature', 'weight',
    'procedure', 'surgery', 'biopsy', 'imaging', 'scan', 'echocardiogram',
    'cancer', 'tumor', 'diabetes', 'hypertension', 'failure', 'asthma',
    'age:', 'sex:', 'gender:', 'male', 'female', 'dob:', 'date of birth',
)


def _smart_trim_pdf(text, max_chars=3500):
    """
    Smarter than [:N]: always include the first 1500 chars (demographics,
    chief complaint), then scan the remainder line-by-line and pull in any
    line that contains a clinical keyword — catching lab values or diagnoses
    on later pages that a hard chop would silently drop.
    """
    if len(text) <= max_chars:
        return text

    first_chunk = text[:1500]
    remainder   = text[1500:]
    budget      = max_chars - len(first_chunk)
    extra_lines = []
    collected   = 0

    for line in remainder.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(kw in lower for kw in _CLINICAL_KW):
            need = len(stripped) + 1
            if collected + need > budget:
                break
            extra_lines.append(stripped)
            collected += need

    return (first_chunk + '\n' + '\n'.join(extra_lines)).strip()

# Reasoning fields now produced by the combined extraction prompt — no separate call needed.
_REASONING_FIELDS = ("CLINICAL SEVERITY:", "DISEASE STABILITY:", "KEY CLINICAL FACTORS:", "POTENTIAL CONCERNS:")
_EXTRACTION_FIELDS = (
    "PRIMARY DIAGNOSIS:", "SECONDARY CONDITIONS:", "CURRENT MEDICATIONS:",
    "PATIENT AGE:", "PATIENT SEX:", "RECENT LAB VALUES:",
    "RECENT PROCEDURES:", "ALLERGIES:", "EXCLUSION FLAGS:",
)


def _split_combined_output(combined_text):
    """
    Split the combined extraction+reasoning output into two logical sections.
    raw_extraction  — the 9 clinical fields (used as patient_profile in matching)
    clinical_reasoning — the 4 reasoning lines (used for key_flags display)
    """
    extraction_lines = []
    reasoning_lines  = []

    for line in combined_text.split("\n"):
        upper = line.strip().upper()
        if any(upper.startswith(f) for f in _REASONING_FIELDS):
            reasoning_lines.append(line)
        elif any(upper.startswith(f) for f in _EXTRACTION_FIELDS) or extraction_lines:
            # once extraction has started, keep appending until a reasoning field appears
            if not any(upper.startswith(f) for f in _REASONING_FIELDS):
                extraction_lines.append(line)

    raw_extraction     = "\n".join(extraction_lines).strip() or combined_text.strip()
    clinical_reasoning = "\n".join(reasoning_lines).strip()
    return raw_extraction, clinical_reasoning


def _parse_key_flags(reasoning_text):
    """Extract a flat list of actionable flags from the reasoning fields."""
    flags = []
    in_factors = False
    for line in reasoning_text.split("\n"):
        stripped = line.strip()
        upper    = stripped.upper()

        if upper.startswith("CLINICAL SEVERITY:"):
            val = stripped[18:].strip()
            if val and val.upper() not in ("UNKNOWN", "NOT FOUND", ""):
                flags.append(f"Severity: {val}")
            in_factors = False

        elif upper.startswith("DISEASE STABILITY:"):
            val = stripped[18:].strip()
            if val and val.upper() not in ("UNKNOWN", "NOT FOUND", ""):
                flags.append(f"Stability: {val}")
            in_factors = False

        elif upper.startswith("KEY CLINICAL FACTORS:"):
            val = stripped[21:].strip()
            if val:
                flags.append(val)
            in_factors = True

        elif upper.startswith("POTENTIAL CONCERNS:"):
            val = stripped[19:].strip()
            if val and val.upper() not in ("NONE", "NOT FOUND", ""):
                flags.append(f"Concern: {val}")
            in_factors = False

        elif in_factors and (stripped.startswith("•") or stripped.startswith("-")):
            val = stripped.lstrip("•-").strip()
            if val:
                flags.append(val)

    return flags if flags else ["No specific flags identified"]


def extract_patient_profile(pdf_path):
    """
    Fast path  — PyMuPDF extracts text directly, then ONE combined LLM call
                 for both extraction and clinical reasoning (eliminates a second
                 round trip that would re-read the same data).
    Fallback   — vision inference if the PDF is scanned / image-only.

    Returns on success:
        {
            'raw_extraction':     str,
            'clinical_reasoning': str,
            'key_flags':          list,
            'step_timings':       dict,
        }
    Returns on failure:
        str  'ERROR: ...'
    """
    step_timings = {}

    # ── Fast path: direct text extraction ──────────────────────────────────
    t0 = time.time()
    pdf_text, text_ok = pdf_to_text(pdf_path)
    step_timings["pdf_read"] = time.time() - t0

    if text_ok:
        print("[profile_extractor] Text extracted from PDF — single combined LLM call.")
        pdf_text_trimmed = _smart_trim_pdf(pdf_text)
        try:
            t0 = time.time()
            combined = stream_response(
                [{"role": "user", "content": TEXT_EXTRACTION_PROMPT.format(pdf_text=pdf_text_trimmed)}],
                max_tokens=TOKENS["extract"],
            )
            step_timings["ai_extract"] = time.time() - t0
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ("connection", "refused", "connect", "socket")):
                return "ERROR: Cannot connect to Ollama. Please ensure Ollama is running, then try again."
            if any(k in err for k in ("memory", "system memory", "out of memory")):
                return "ERROR: Not enough RAM. Gemma 4 needs ~10 GB free. Close other apps and try again."
            if "not found" in err:
                return f"ERROR: Model {MODEL!r} not found. Run 'ollama pull {MODEL}' and try again."
            return f"ERROR: Extraction failed: {e}"

        raw_extraction, clinical_reasoning = _split_combined_output(combined)

    else:
        # ── Fallback: vision inference for image-only PDFs ──────────────────
        print("[profile_extractor] No extractable text — using vision inference (this will be slow).")
        try:
            images = pdf_to_images(pdf_path, max_pages=2)
        except Exception as e:
            return f"ERROR: Failed to read PDF pages: {e}"

        if not images:
            return "ERROR: Could not extract any pages from the PDF. Ensure the file is a valid, non-corrupted PDF."

        profile_parts = []
        t0 = time.time()
        for i, img in enumerate(images):
            print(f"[profile_extractor] Vision pass: page {i + 1} of {len(images)}...")
            try:
                buf      = io.BytesIO()
                img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
                buf.close()
                del img

                page_text = stream_response(
                    [{"role": "user", "content": EXTRACTION_PROMPT, "images": [img_bytes]}],
                    max_tokens=TOKENS["extract"],
                )
                del img_bytes
                profile_parts.append(f"--- Page {i + 1} ---\n{page_text}")

            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ("connection", "refused", "connect", "socket")):
                    return "ERROR: Cannot connect to Ollama. Please ensure Ollama is running, then try again."
                if any(k in err for k in ("memory", "system memory", "out of memory")):
                    return "ERROR: Not enough RAM. Gemma 4 needs ~10 GB free. Close other apps and try again."
                if "not found" in err:
                    return f"ERROR: Model {MODEL!r} not found. Run 'ollama pull {MODEL}' and try again."
                profile_parts.append(f"--- Page {i + 1} --- [extraction error: {e}]")
        step_timings["ai_extract"] = time.time() - t0

        combined = "\n\n".join(profile_parts)
        raw_extraction, clinical_reasoning = _split_combined_output(combined)

    if not raw_extraction.strip():
        return "ERROR: Profile extraction produced no output."

    key_flags = _parse_key_flags(clinical_reasoning)

    return {
        "raw_extraction":     raw_extraction,
        "clinical_reasoning": clinical_reasoning,
        "key_flags":          key_flags,
        "step_timings":       step_timings,
        "used_vision":        not text_ok,
    }
