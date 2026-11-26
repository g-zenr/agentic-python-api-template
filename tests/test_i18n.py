"""Localization tests: catalog parity, placeholder parity, and locale resolution."""

import json
import re
from pathlib import Path

from app.core.config import settings
from app.core.i18n import catalogs, resolve_locale
from app.core.messages import Msg

LOCALES_DIR = Path(__file__).resolve().parents[1] / "app" / "core" / "locales"


def _load_all() -> dict[str, dict[str, str]]:
    return {p.stem: json.loads(p.read_text("utf-8")) for p in LOCALES_DIR.glob("*.json")}


def test_every_msg_value_exists_in_every_locale():
    catalogs_ = _load_all()
    msg_values = {m.value for m in Msg}
    for name, cat in catalogs_.items():
        missing = msg_values - set(cat)
        assert not missing, f"{name} missing keys: {sorted(missing)}"


def test_all_locales_share_identical_key_sets():
    catalogs_ = _load_all()
    key_sets = {name: set(cat) for name, cat in catalogs_.items()}
    reference = key_sets[next(iter(key_sets))]
    for name, keys in key_sets.items():
        assert keys == reference, f"{name} key set differs"


def test_placeholders_match_across_locales():
    catalogs_ = _load_all()
    placeholder = re.compile(r"\{(\w+)\}")
    reference_name = next(iter(catalogs_))
    reference = catalogs_[reference_name]
    for name, cat in catalogs_.items():
        for key, text in reference.items():
            other = cat.get(key, "")
            assert set(placeholder.findall(text)) == set(placeholder.findall(other)), (
                f"{name}:{key} placeholder mismatch"
            )


def test_resolve_locale_picks_first_supported():
    assert resolve_locale("fil-PH,en;q=0.8") == "fil"
    assert resolve_locale("en-US,en;q=0.9") == "en"


def test_resolve_locale_unknown_falls_back_to_default():
    assert resolve_locale("de-DE") == settings.default_locale
    assert resolve_locale(None) == settings.default_locale


def test_catalogs_accessor_matches_files():
    assert set(catalogs()) == {p.stem for p in LOCALES_DIR.glob("*.json")}
