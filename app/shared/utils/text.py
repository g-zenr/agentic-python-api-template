"""Text helpers: truncation."""


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    """Shorten `text` to at most `limit` characters, appending `suffix` when cut."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(suffix))].rstrip() + suffix
