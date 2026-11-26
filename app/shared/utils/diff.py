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


def redact(data: Mapping[str, Any]) -> dict[str, Any]:
    """Mask secret fields (recursively). Field list: Redaction.FIELDS."""
    return {
        k: Redaction.MASK if k in Redaction.FIELDS else redact(v) if isinstance(v, Mapping) else v
        for k, v in data.items()
    }


def diff(before: Any, after: Any) -> dict[str, dict[str, Any]]:
    """Field changes `{field: {"from": x, "to": y}}`. Create: before=None; delete: after=None."""
    b, a = to_plain(before) or {}, to_plain(after) or {}
    out: dict[str, dict[str, Any]] = {}
    for key in sorted((b.keys() | a.keys()) - Redaction.IGNORED):
        if b.get(key) != a.get(key):
            masked = key in Redaction.FIELDS
            out[key] = {
                "from": Redaction.MASK if masked else b.get(key),
                "to": Redaction.MASK if masked else a.get(key),
            }
    return out
