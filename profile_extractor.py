import io

from utils import MODEL, stream_response
from pdf_reader import pdf_to_images
from prompts import EXTRACTION_PROMPT, REASONING_PROMPT


def extract_patient_profile(pdf_path):
    """
    Step 1 — Extract structured medical data from up to 3 PDF pages (vision pass).
    Step 2 — Run a clinical reasoning pass on the extracted text (text-only pass).

    Returns:
        dict   {'profile': str, 'reasoning': str}   on success
        str    'ERROR: ...'                          on any failure
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

    # ── Vision pass: extract raw medical data from each page ────────────────
    for i, img in enumerate(images):
        print(f"[profile_extractor] Extracting page {i + 1} of {total_pages}...")
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

    combined_profile = "\n\n".join(profile_parts)
    if not combined_profile.strip():
        return "ERROR: Profile extraction produced no output."

    # ── Reasoning pass: clinical interpretation of extracted data ───────────
    print("[profile_extractor] Running clinical reasoning pass...")
    try:
        reasoning_prompt = REASONING_PROMPT.format(extracted_profile=combined_profile)
        clinical_reasoning = stream_response(
            [{"role": "user", "content": reasoning_prompt}]
        )
    except Exception as e:
        clinical_reasoning = f"[clinical reasoning unavailable: {e}]"

    return {"profile": combined_profile, "reasoning": clinical_reasoning}
