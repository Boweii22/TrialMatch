import ollama

MODEL = "gemma4:e4b"

# Per-call token budgets — keeps each LLM call short and predictable.
# Ollama's num_predict caps new tokens generated (not context window).
TOKENS = {
    "extract":      380,   # 13 fields (9 extraction + 4 reasoning) — one combined call
    "match":        100,   # 5-line verdict block
    "reason_chain": 100,   # 3-sentence reasoning chain
    "email":        300,   # subject + brief body
    "translate":    450,   # non-Latin script overhead kept
    "urdu":         700,   # full results explanation
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
    # think=False disables gemma4's internal reasoning phase so num_predict
    # budget is spent entirely on the structured output we need.
    stream = ollama.chat(model=MODEL, messages=messages, stream=True, think=False, options=opts)
    for chunk in stream:
        content = chunk.message.content
        if content:
            response_text += content
    return response_text.strip()
