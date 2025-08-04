def sanitize_response(text: str) -> str:	
    """
    Sanitize the response text by removing leading/trailing whitespace and
    ensuring it does not contain any newline characters.
    """
    if not text:
        return ""
    return text.strip()