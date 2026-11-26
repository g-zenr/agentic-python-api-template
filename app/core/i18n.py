"""Localization: load locale JSON catalogs, resolve the request locale, translate keys."""

import json
from pathlib import Path

from app.core.config import settings
from app.core.context import locale_var
from app.core.messages import Msg

_LOCALES_DIR = Path(__file__).parent / "locales"
_catalog: dict[str, dict[str, str]] = {
    p.stem: json.loads(p.read_text("utf-8")) for p in _LOCALES_DIR.glob("*.json")
}


def resolve_locale(header: str | None) -> str:
    """Pick the first supported language from an Accept-Language header, else the default."""
    for part in (header or "").split(","):
        lang = part.split(";")[0].strip().lower().split("-")[0]
        if lang in settings.supported_locales and lang in _catalog:
            return lang
    return settings.default_locale


def t(key: Msg | str, locale: str | None = None, **params: object) -> str:
    """Translate `key` into `locale` (default: current request locale), with {placeholders}."""
    loc = locale or locale_var.get()
    text = _catalog.get(loc, {}).get(key) or _catalog[settings.default_locale].get(key) or str(key)
    return text.format(**params) if params else text


def catalogs() -> dict[str, dict[str, str]]:
    """Expose loaded catalogs (used by tests and scripts)."""
    return _catalog
