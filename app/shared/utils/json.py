"""JSON helpers backed by orjson for fast (de)serialization."""

import orjson


def dumps(obj: object) -> str:
    """Serialize `obj` to a JSON string, falling back to ``str`` for unknown types."""
    return orjson.dumps(obj, default=str).decode("utf-8")


def loads(s: str | bytes) -> object:
    """Parse a JSON string or bytes into Python objects."""
    return orjson.loads(s)
