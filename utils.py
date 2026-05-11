import ollama

MODEL = "gemma3:4b"


def stream_response(messages):
    """
    Call ollama.chat with streaming and return the full concatenated response.
    Works for both text-only and multimodal (image) messages.
    Raises on connection/model errors so callers can handle them explicitly.
    """
    response_text = ""
    stream = ollama.chat(model=MODEL, messages=messages, stream=True)
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
