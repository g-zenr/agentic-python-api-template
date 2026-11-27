"""Field-level diffing and secret redaction for audit entries."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.core.constants import Redaction


def to_plain(obj: Any) -> dict[str, Any] | None:
    """Normalize a pydantic model / mapping / None to a JSON-safe dict."""
    if obj is None:
        return None
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return dict(obj)


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return redact(value)
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    return value


def redact(data: Mapping[str, Any]) -> dict[str, Any]:
    """Mask secret fields (recursively). Field list: Redaction.FIELDS."""
    return {
        k: Redaction.MASK if k.lower() in Redaction.FIELDS else _redact_value(v)
        for k, v in data.items()
    }


def diff(before: Any, after: Any) -> dict[str, dict[str, Any]]:
    """Field changes `{field: {"from": x, "to": y}}`. Create: before=None; delete: after=None."""
    b, a = to_plain(before) or {}, to_plain(after) or {}
    out: dict[str, dict[str, Any]] = {}
    for key in sorted((b.keys() | a.keys()) - Redaction.IGNORED):
        if b.get(key) != a.get(key):
            masked = key.lower() in Redaction.FIELDS
            out[key] = {
                "from": Redaction.MASK if masked else _redact_value(b.get(key)),
                "to": Redaction.MASK if masked else _redact_value(a.get(key)),
            }
    return out
