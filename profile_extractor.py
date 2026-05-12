import io

from utils import MODEL, TOKENS, stream_response
from pdf_reader import pdf_to_text, pdf_to_images
from prompts import TEXT_EXTRACTION_PROMPT, EXTRACTION_PROMPT, REASONING_PROMPT


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
            in_factors = True

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
    Fast path  — PyMuPDF extracts text directly (< 1 s), then one text LLM call.
    Fallback   — vision inference if the PDF is scanned / image-only.

    Returns on success:
        {
            'raw_extraction':    str,
            'clinical_reasoning': str,
            'key_flags':         list,
        }
    Returns on failure:
        str  'ERROR: ...'
    """

    # ── Fast path: direct text extraction ──────────────────────────────────
    pdf_text, text_ok = pdf_to_text(pdf_path)

    if text_ok:
        print("[profile_extractor] Text extracted from PDF — skipping vision inference.")
        try:
            raw_extraction = stream_response(
                [{"role": "user", "content": TEXT_EXTRACTION_PROMPT.format(pdf_text=pdf_text)}],
                max_tokens=TOKENS["extract"],
            )
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ("connection", "refused", "connect", "socket")):
                return "ERROR: Cannot connect to Ollama. Please ensure Ollama is running, then try again."
            if any(k in err for k in ("not found", "model", "pull")):
                return f"ERROR: Model {MODEL!r} not found. Run 'ollama pull {MODEL}' and try again."
            return f"ERROR: Extraction failed: {e}"

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
        for i, img in enumerate(images):
            print(f"[profile_extractor] Vision pass: page {i + 1} of {len(images)}...")
            try:
                buf = io.BytesIO()
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
                if any(k in err for k in ("not found", "model", "pull")):
                    return f"ERROR: Model {MODEL!r} not found. Run 'ollama pull {MODEL}' and try again."
                profile_parts.append(f"--- Page {i + 1} --- [extraction error: {e}]")

        raw_extraction = "\n\n".join(profile_parts)

    if not raw_extraction.strip():
        return "ERROR: Profile extraction produced no output."

    # ── Reasoning pass (always text-only, fast) ─────────────────────────────
    print("[profile_extractor] Running clinical reasoning pass...")
    try:
        clinical_reasoning = stream_response(
            [{"role": "user", "content": REASONING_PROMPT.format(extracted_profile=raw_extraction)}],
            max_tokens=TOKENS["reason"],
        )
    except Exception as e:
        clinical_reasoning = f"[clinical reasoning unavailable: {e}]"

    key_flags = _parse_key_flags(clinical_reasoning)

    return {
        "raw_extraction":     raw_extraction,
        "clinical_reasoning": clinical_reasoning,
        "key_flags":          key_flags,
    }
