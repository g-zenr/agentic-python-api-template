"""Read-only feature audit. Exit code 1 on any problem.

Usage:
  `uv run python scripts/check_feature.py`          # audit all features
  `uv run python scripts/check_feature.py <name>`   # audit one + print its references
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _features import (
    audit_coverage_violations,
    current_version,
    feature_names,
    features_dir,
    find_orphans,
    find_references,
    read_registry,
    root_path,
)

REQUIRED_HEADINGS = [
    "## Status",
    "## Purpose",
    "## Endpoints",
    "## Data model",
    "## Business rules",
    "## Dependencies",
    "## Extending",
    "## Change history",
]
_CHANGELOG = "docs/CHANGELOG.md"
_REGISTRY = "docs/features.md"


def _readme_problems(root, name: str) -> list[str]:
    readme = features_dir(root) / name / "README.md"
    if not readme.exists():
        return [f"{name}: missing README.md"]
    text = readme.read_text("utf-8")
    problems: list[str] = []
    positions = []
    for heading in REQUIRED_HEADINGS:
        idx = text.find(heading)
        if idx == -1:
            problems.append(f"{name}: README missing heading '{heading}'")
        positions.append(idx)
    if all(p >= 0 for p in positions) and positions != sorted(positions):
        problems.append(f"{name}: README headings out of order")
    # Change history has at least one data row.
    if "## Change history" in text:
        tail = text.split("## Change history", 1)[1]
        rows = [ln for ln in tail.splitlines() if ln.strip().startswith("|")]
        data_rows = [r for r in rows if not set(r.replace("|", "").strip()) <= set("-: ")]
        # first data row is the header; require at least one more
        if len(data_rows) < 2:
            problems.append(f"{name}: README Change history has no data row")
    return problems


def _registry_last_changed(root, name: str) -> str | None:
    active, _ = read_registry(root)
    for row in active:
        if row[0] == name:
            return row[6] if len(row) > 6 else None
    return None


def audit(root, only: str | None = None) -> list[str]:
    problems: list[str] = []
    names = feature_names(root)
    active, removed = read_registry(root)
    active_names = [r[0] for r in active]
    removed_names = [r[0] for r in removed]

    # Parity.
    for name in names:
        if name not in active_names:
            problems.append(f"{name}: folder has no Active registry row")
    for name in active_names:
        if name not in names:
            problems.append(f"{name}: Active row has no feature folder")
    for name in set(active_names) & set(removed_names):
        problems.append(f"{name}: appears in both Active and Removed tables")

    targets = [only] if only else names
    for name in targets:
        problems.extend(_readme_problems(root, name))
        last = _registry_last_changed(root, name)
        readme = features_dir(root) / name / "README.md"
        if last and readme.exists() and last not in readme.read_text("utf-8"):
            problems.append(f"{name}: 'Last changed' {last} not in README Change history")

    # Orphans / locale parity.
    orphans = find_orphans(root)
    for key, label in (
        ("orphan_msgs", "Msg"),
        ("orphan_tags", "Tag"),
        ("orphan_job_types", "JobType"),
        ("orphan_cache_ns", "CacheNS"),
        ("orphan_audit_actions", "AuditAction"),
        ("orphan_audit_resources", "AuditResource"),
        ("orphan_audit_reasons", "AuditReason"),
    ):
        for m in orphans[key]:
            problems.append(f"orphan {label}.{m} (unused in app/)")
    for k in orphans["locale_keys_without_msg"]:
        problems.append(f"locale key without Msg member: {k}")
    for m in orphans["msgs_missing_in_locale"]:
        problems.append(f"Msg value missing from a locale: {m}")

    # Audit coverage: every mutation must call audit.record.
    for v in audit_coverage_violations(root):
        problems.append(f"mutation without audit.record: {v}")

    # Routes must declare summary + description; no HTTPException in features.
    for py in (root / "app" / "features").rglob("router.py"):
        src = py.read_text("utf-8")
        for call in re.finditer(r"@router\.(get|post|put|patch|delete)\(", src):
            tail = src[call.end() : call.end() + 400]
            if "summary=" not in tail or "description=" not in tail:
                problems.append(
                    f"{py.relative_to(root).as_posix()}: route missing summary/description"
                )  # noqa: E501
        if "HTTPException" in src:
            problems.append(f"{py.relative_to(root).as_posix()}: HTTPException in a feature router")

    # Every JobType has a handler and vice versa.
    try:
        from app.core.constants import JobType
        from app.core.discovery import feature_modules
        from app.core.jobs import registry

        feature_modules("jobs")
        if set(registry.handlers()) != set(JobType):
            problems.append("JobType/handler mismatch: every JobType needs a handler")
    except Exception as exc:  # pragma: no cover - import guard
        problems.append(f"could not verify job handlers: {exc}")

    # Docs mentioning removed features outside allowed files.
    for name in removed_names:
        for hit in find_references(root, f"features/{name}"):
            path = hit.split(":")[0]
            if path in {_REGISTRY, _CHANGELOG}:
                continue
            if path.startswith("docs/decisions/"):
                continue
            problems.append(f"docs mention removed feature '{name}': {hit}")

    # Version in CHANGELOG first section.
    version = current_version(root)
    changelog = root / _CHANGELOG
    if changelog.exists():
        text = changelog.read_text("utf-8")
        first = re.search(r"##\s*\[([0-9.]+)\]", text)
        if not first or first.group(1) != version:
            problems.append(f"pyproject version {version} not in first CHANGELOG section")
    else:
        problems.append("missing docs/CHANGELOG.md")

    return problems


def _print_references(root, name: str) -> None:
    hits = find_references(root, f"app.features.{name}")
    print(f"\nReferences to app.features.{name}:")
    if not hits:
        print("  (none)")
    for hit in hits:
        print(f"  {hit}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit features (read-only).")
    parser.add_argument("name", nargs="?", default=None)
    parser.add_argument("--root", default=None)
    args = parser.parse_args()

    root = root_path(args.root)
    if args.name:
        _print_references(root, args.name)
    problems = audit(root, args.name)
    if problems:
        print(f"\nfeature-check: {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("feature-check: OK")


if __name__ == "__main__":
    main()
