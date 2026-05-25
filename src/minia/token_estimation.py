import tiktoken


def estimate_tokens(text: str) -> int:
    """Estimate token count using tiktoken (cl100k_base encoding).

    Falls back to word*4 heuristic if tiktoken is unavailable.
    """
    try:
        encoder = tiktoken.get_encoding("cl100k_base")
        return len(encoder.encode(text))
    except Exception:
        return len(text.split()) * 4
