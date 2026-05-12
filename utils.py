import ollama

MODEL = "gemma4:e4b"

# Per-call token budgets — keeps each LLM call short and predictable.
# Ollama's num_predict caps new tokens generated (not context window).
TOKENS = {
    "extract":   450,   # vision pass per page — needs room for 9 structured fields
    "reason":    280,   # clinical reasoning summary
    "match":     220,   # VERDICT / CONFIDENCE / REASON / DISQUALIFIERS / NEXT STEP
    "email":     420,   # subject + body
    "translate": 300,   # three labelled fields translated
    "urdu":      600,   # full results explanation
}


def stream_response(messages, max_tokens=None):
    """
    Call ollama.chat with streaming and return the full concatenated response.
    Works for both text-only and multimodal (image) messages.
    max_tokens caps output length (Ollama num_predict). Pass None for no cap.
    Raises on connection/model errors so callers can handle them explicitly.
    """
    opts = {"num_predict": max_tokens} if max_tokens else {}
    response_text = ""
    stream = ollama.chat(model=MODEL, messages=messages, stream=True, options=opts)
    for chunk in stream:
        try:
            content = chunk.message.content
            if content:
                response_text += content
        except AttributeError:
            try:
                content = chunk["message"]["content"]
                if content:
                    response_text += content
            except (KeyError, TypeError):
                pass
    return response_text.strip()
