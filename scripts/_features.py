"""Shared helpers for the feature lifecycle scripts (new/remove/check).

All three scripts import from here so no logic is duplicated. The repository root is
overridable via the `FEATURE_ROOT` environment variable (or the `root` argument) so tests
can run the scripts against a temporary copy of the repo skeleton.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from datetime import date
from pathlib import Path

# --- Locations -----------------------------------------------------------------------------

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
FEATURES_DIRNAME = "features"
REGISTRY = "docs/features.md"
PYPROJECT = "pyproject.toml"
MSG_MODULE = "app/core/messages.py"
CONSTANTS_MODULE = "app/core/constants.py"
LOCALES_DIR = "app/core/locales"


def root_path(root: str | Path | None = None) -> Path:
    """Resolve the repository root (explicit arg > FEATURE_ROOT env > default)."""
    if root is not None:
        return Path(root).resolve()
    env = os.environ.get("FEATURE_ROOT")
    return Path(env).resolve() if env else DEFAULT_ROOT


def features_dir(root: Path) -> Path:
    return root / "app" / FEATURES_DIRNAME


def feature_names(root: Path) -> list[str]:
    """List feature folder names (non-underscore directories)."""
    fdir = features_dir(root)
    if not fdir.is_dir():
        return []
    return sorted(p.name for p in fdir.iterdir() if p.is_dir() and not p.name.startswith("_"))


def current_version(root: Path) -> str:
    """Read the app version from pyproject.toml (the single source of truth)."""
    data = tomllib.loads((root / PYPROJECT).read_text("utf-8"))
    return data["project"]["version"]


def today() -> str:
    """Today's date as YYYY-MM-DD."""
    return date.today().isoformat()


# --- Registry (docs/features.md) -----------------------------------------------------------

_ACTIVE_HEADING = "## Active features"
_REMOVED_HEADING = "## Removed features"


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def read_registry(root: Path) -> tuple[list[list[str]], list[list[str]]]:
    """Return (active_rows, removed_rows) as lists of cell lists (header rows excluded)."""
    text = (root / REGISTRY).read_text("utf-8")
    active: list[list[str]] = []
    removed: list[list[str]] = []
    bucket: list[list[str]] | None = None
    for line in text.splitlines():
        if line.strip() == _ACTIVE_HEADING:
            bucket = active
            continue
        if line.strip() == _REMOVED_HEADING:
            bucket = removed
            continue
        if bucket is None:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            if stripped.startswith("##"):
                bucket = None
            continue
        cells = _split_row(stripped)
        if not cells or set("".join(cells)) <= set("-: "):
            continue  # separator row
        if cells[0].lower() == "feature":
            continue  # header row
        bucket.append(cells)
    return active, removed


def _render_table(rows: list[list[str]], header: list[str]) -> list[str]:
    out = ["| " + " | ".join(header) + " |"]
    out.append("|" + "|".join(["---"] * len(header)) + "|")
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return out


_ACTIVE_HEADER = [
    "Feature",
    "Status",
    "Prefix",
    "Prisma model(s)",
    "MCP tools",
    "Since",
    "Last changed",
    "README",
]
_REMOVED_HEADER = ["Feature", "Removed in", "Date", "Reason", "Data dropped?", "Reference"]


def write_registry(root: Path, active: list[list[str]], removed: list[list[str]]) -> None:
    """Rewrite the two registry tables in docs/features.md, preserving surrounding prose."""
    path = root / REGISTRY
    lines = path.read_text("utf-8").splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == _ACTIVE_HEADING:
            out.append(line)
            i += 1
            out.extend(_render_table(active, _ACTIVE_HEADER))
            # skip old active table lines
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            continue
        if line.strip() == _REMOVED_HEADING:
            out.append(line)
            i += 1
            out.extend(_render_table(removed, _REMOVED_HEADER))
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            continue
        out.append(line)
        i += 1
    path.write_text("\n".join(out) + "\n", "utf-8")


# --- Cross-references ----------------------------------------------------------------------


def find_references(root: Path, needle: str) -> list[str]:
    """Find `needle` across app/, docs/, tests/; return "path:line" strings."""
    hits: list[str] = []
    pattern = re.compile(re.escape(needle))
    for base in ("app", "docs", "tests", "scripts"):
        base_path = root / base
        if not base_path.exists():
            continue
        for file in base_path.rglob("*"):
            if file.suffix not in {".py", ".md"} or not file.is_file():
                continue
            for n, line in enumerate(file.read_text("utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{file.relative_to(root).as_posix()}:{n}")
    return hits


# --- Orphan detection ----------------------------------------------------------------------


def _enum_members(source: str, class_name: str) -> list[str]:
    members: list[str] = []
    inside = False
    for line in source.splitlines():
        if re.match(rf"class {class_name}\b", line):
            inside = True
            continue
        if inside:
            if line and not line[0].isspace() and not line.startswith(")"):
                break
            m = re.match(r"\s+([A-Z][A-Z0-9_]*)\s*=", line)
            if m:
                members.append(m.group(1))
    return members


def _class_constants(source: str, class_name: str) -> list[str]:
    return _enum_members(source, class_name)


def find_orphans(root: Path) -> dict[str, list[str]]:
    """Return orphaned enum members (Msg/Tag/JobType/CacheNS/Audit*) and locale/Msg mismatches."""
    messages_src = (root / MSG_MODULE).read_text("utf-8")
    constants_src = (root / CONSTANTS_MODULE).read_text("utf-8")

    # Gather all app/ source (excluding messages.py) to test usage.
    app_text: list[str] = []
    for file in (root / "app").rglob("*.py"):
        if file.as_posix().endswith(MSG_MODULE):
            continue
        app_text.append(file.read_text("utf-8", errors="ignore"))
    app_blob = "\n".join(app_text)

    enum_sources = {
        "Msg": messages_src,
        "Tag": constants_src,
        "JobType": constants_src,
        "CacheNS": constants_src,
        "AuditAction": constants_src,
        "AuditResource": constants_src,
        "AuditReason": constants_src,
        "Permission": constants_src,
        "RateBucket": constants_src,
        "TokenPurpose": constants_src,
    }
    orphans: dict[str, list[str]] = {}
    for enum_name, src in enum_sources.items():
        members = _enum_members(src, enum_name)
        orphans[enum_name] = sorted(m for m in members if f"{enum_name}.{m}" not in app_blob)

    # Locale parity.
    locales_dir = root / LOCALES_DIR
    catalogs = {jf.stem: json.loads(jf.read_text("utf-8")) for jf in locales_dir.glob("*.json")}
    msg_values: set[str] = set()
    for line in messages_src.splitlines():
        m = re.search(r'=\s*"([^"]+)"', line)
        if m:
            msg_values.add(m.group(1))
    locale_keys: set[str] = set()
    for cat in catalogs.values():
        locale_keys |= set(cat)
    keys_without_msg = sorted(locale_keys - msg_values)
    msgs_missing_in_locale: list[str] = []
    for name, cat in catalogs.items():
        for value in sorted(msg_values - set(cat)):
            msgs_missing_in_locale.append(f"{value} (missing in {name})")

    return {
        "orphan_msgs": orphans["Msg"],
        "orphan_tags": orphans["Tag"],
        "orphan_job_types": orphans["JobType"],
        "orphan_cache_ns": orphans["CacheNS"],
        "orphan_audit_actions": orphans["AuditAction"],
        "orphan_audit_resources": orphans["AuditResource"],
        "orphan_audit_reasons": orphans["AuditReason"],
        "locale_keys_without_msg": keys_without_msg,
        "msgs_missing_in_locale": msgs_missing_in_locale,
    }


_AUDIT_PREFIXES = (
    "create",
    "update",
    "delete",
    "register",
    "login",
    "logout",
    "refresh",
    "cancel",
    "request_",
    "verify",
    "reset",
    "change",
    "forgot",
    "resend",
    "erase",
)


def audit_coverage_violations(root: Path) -> list[str]:
    """Flag public async service functions that mutate but never call audit.record(...)."""
    import ast

    violations: list[str] = []
    fdir = root / "app" / "features"
    for service_file in fdir.glob("*/service.py"):
        src = service_file.read_text("utf-8")
        tree = ast.parse(src)
        lines = src.splitlines()
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef) or node.name.startswith("_"):
                continue
            if not node.name.startswith(_AUDIT_PREFIXES):
                continue
            seg = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            if "audit.record(" in seg or "# audit-exempt:" in seg:
                continue
            violations.append(f"{service_file.relative_to(root).as_posix()}:{node.name}")
    return violations
