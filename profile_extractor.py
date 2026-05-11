import io

from utils import MODEL, stream_response
from pdf_reader import pdf_to_images
from prompts import EXTRACTION_PROMPT, REASONING_PROMPT


def _parse_key_flags(reasoning_text):
    """
    Extract a flat list of actionable flags from REASONING_PROMPT output.
    Picks up severity, stability, bullet-point factors, and concern lines.
    """
    flags = []
    in_factors = False
    for line in reasoning_text.split("\n"):
        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith("CLINICAL SEVERITY:"):
            val = stripped[18:].strip()
            if val and val.upper() not in ("UNKNOWN", ""):
                flags.append(f"Severity: {val}")
            in_factors = False

        elif upper.startswith("DISEASE STABILITY:"):
            val = stripped[18:].strip()
            if val and val.upper() not in ("UNKNOWN", ""):
                flags.append(f"Stability: {val}")
            in_factors = False

        elif upper.startswith("KEY CLINICAL FACTORS:"):
            val = stripped[21:].strip()
            if val:
                flags.append(val)
            in_factors = True  # following bullet lines belong here

        elif upper.startswith("POTENTIAL CONCERNS:"):
            val = stripped[19:].strip()
            if val and val.upper() != "NONE":
                flags.append(f"Concern: {val}")
            in_factors = False

        elif in_factors and (stripped.startswith("•") or stripped.startswith("-")):
            val = stripped.lstrip("•-").strip()
            if val:
                flags.append(val)

    return flags if flags else ["No specific flags identified"]


def extract_patient_profile(pdf_path):
    """
    Step 1 — Vision pass: extract raw medical data from each PDF page.
    Step 2 — Reasoning pass: clinical interpretation of severity and eligibility.
    Step 3 — Parse key_flags list from the reasoning output.

    Returns on success:
        {
            'raw_extraction':    str,   # concatenated structured data from all pages
            'clinical_reasoning': str,  # REASONING_PROMPT output (severity, stability, etc.)
            'key_flags':         list,  # parsed actionable flags for the matcher
        }

    Returns on failure:
        str  'ERROR: ...'
    """
    try:
        images = pdf_to_images(pdf_path)
    except Exception as e:
        return f"ERROR: Failed to read PDF pages: {e}"

    if not images:
        return (
            "ERROR: Could not extract any pages from the PDF. "
            "Ensure the file is a valid, non-corrupted PDF."
        )

    profile_parts = []
    total_pages = len(images)

    # ── Step 1: Vision pass ─────────────────────────────────────────────────
    for i, img in enumerate(images):
        print(f"[profile_extractor] Reading page {i + 1} of {total_pages}...")
        try:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            buf.close()
            del img

            page_text = stream_response(
                [{"role": "user", "content": EXTRACTION_PROMPT, "images": [img_bytes]}]
            )
            del img_bytes
            profile_parts.append(f"--- Page {i + 1} ---\n{page_text}")

        except Exception as e:
            err = str(e).lower()
            if any(kw in err for kw in ("connection", "refused", "connect", "socket")):
                return (
                    "ERROR: Cannot connect to Ollama. "
                    "Please ensure Ollama is running, then try again."
                )
            if any(kw in err for kw in ("not found", "model", "pull")):
                return (
                    f"ERROR: Model {MODEL!r} not found. "
                    f"Please run 'ollama pull {MODEL}' and try again."
                )
            profile_parts.append(f"--- Page {i + 1} --- [extraction error: {e}]")

    raw_extraction = "\n\n".join(profile_parts)
    if not raw_extraction.strip():
        return "ERROR: Profile extraction produced no output."

    # ── Step 2: Reasoning pass ──────────────────────────────────────────────
    print("[profile_extractor] Running clinical reasoning pass...")
    try:
        clinical_reasoning = stream_response(
            [{"role": "user", "content": REASONING_PROMPT.format(extracted_profile=raw_extraction)}]
        )
    except Exception as e:
        clinical_reasoning = f"[clinical reasoning unavailable: {e}]"

    # ── Step 3: Parse key_flags ─────────────────────────────────────────────
    key_flags = _parse_key_flags(clinical_reasoning)

    return {
        "raw_extraction": raw_extraction,
        "clinical_reasoning": clinical_reasoning,
        "key_flags": key_flags,
    }
