"""Text helpers: truncation and slug generation."""

import re
import unicodedata


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    """Shorten `text` to at most `limit` characters, appending `suffix` when cut."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(suffix))].rstrip() + suffix


def slugify(text: str) -> str:
    """Lowercase, deaccent, and hyphenate `text` into a URL-safe slug."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug
