import io

import ollama

from pdf_reader import pdf_to_images
from prompts import EXTRACTION_PROMPT

_MODEL = "gemma3:4b"


def _stream_response(messages):
    """Call ollama.chat with streaming and return the concatenated text."""
    response_text = ""
    stream = ollama.chat(model=_MODEL, messages=messages, stream=True)
    for chunk in stream:
        try:
            # ollama SDK >= 0.2: chunk is a ChatResponse object
            content = chunk.message.content
            if content:
                response_text += content
        except AttributeError:
            # Fallback for dict-style response
            try:
                content = chunk["message"]["content"]
                if content:
                    response_text += content
            except (KeyError, TypeError):
                pass
    return response_text


def extract_patient_profile(pdf_path):
    """
    Read up to 3 pages of pdf_path, send each page image to Gemma 4,
    and return a concatenated patient profile string.
    Returns an 'ERROR: ...' string on failure instead of raising.
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

    for i, img in enumerate(images):
        print(f"[profile_extractor] Reading page {i + 1} of {total_pages}...")
        try:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            buf.close()
            del img  # free PIL image memory

            messages = [
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT,
                    "images": [img_bytes],
                }
            ]
            page_text = _stream_response(messages)
            del img_bytes

            profile_parts.append(f"--- Page {i + 1} ---\n{page_text.strip()}")

        except Exception as e:
            err_lower = str(e).lower()
            if any(kw in err_lower for kw in ("connection", "refused", "connect", "socket")):
                return (
                    "ERROR: Cannot connect to Ollama. "
                    "Please start Ollama by running 'ollama serve' in a terminal, then try again."
                )
            if any(kw in err_lower for kw in ("not found", "model", "pull")):
                return (
                    f"ERROR: Model {_MODEL!r} not found in Ollama. "
                    f"Please run 'ollama pull {_MODEL}' in a terminal, then try again."
                )
            profile_parts.append(f"--- Page {i + 1} --- [extraction error: {e}]")

    if not profile_parts:
        return "ERROR: Profile extraction produced no output."

    return "\n\n".join(profile_parts)
