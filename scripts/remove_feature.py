"""Remove a feature: delete its folder/tests, move its registry row to Removed.

Usage: `uv run python scripts/remove_feature.py <name> --reason "..." --drop-data true|false`
Refuses if the feature is not in the registry or if another feature imports it.
"""

from __future__ import annotations

import argparse
import shutil
import sys

from _features import (
    current_version,
    features_dir,
    find_orphans,
    read_registry,
    root_path,
    today,
    write_registry,
)


def _importing_features(root, name: str) -> list[str]:
    """Other feature folders that import app.features.<name>."""
    needle = f"app.features.{name}"
    offenders: list[str] = []
    fdir = features_dir(root)
    for file in fdir.rglob("*.py"):
        if file.parent.name == name:
            continue
        text = file.read_text("utf-8", errors="ignore")
        if needle in text:
            offenders.append(file.relative_to(root).as_posix())
    return offenders


def remove(root, name: str, reason: str, drop_data: bool) -> None:
    active, removed = read_registry(root)
    if not any(row[0] == name for row in active):
        sys.exit(f"error: '{name}' is not in the Active registry")

    offenders = _importing_features(root, name)
    if offenders:
        sys.exit(
            "error: other features import this feature; refactor them FIRST:\n  "
            + "\n  ".join(offenders)
        )

    version = current_version(root)
    row = next(r for r in active if r[0] == name)
    active.remove(row)
    removed.append(
        [
            name,
            version,
            today(),
            reason or "n/a",
            "yes" if drop_data else "no",
            "n/a",
        ]
    )
    write_registry(root, active, removed)

    fdir = features_dir(root) / name
    if fdir.exists():
        shutil.rmtree(fdir)
    test_file = root / "tests" / "features" / f"test_{name}.py"
    if test_file.exists():
        test_file.unlink()

    orphans = find_orphans(root)
    print(f"removed app/features/{name}/ and moved its registry row to Removed.")
    print("\nRemaining manual steps (see docs/playbooks/remove-feature.md):")
    if drop_data:
        print("  - Remove the Prisma model from prisma/schema.prisma and run `make migrate`.")
    else:
        print("  - Keep the Prisma model (data retained); note this in the ADR.")
    print("  - Remove now-orphaned Msg keys from messages.py and EVERY locale file:")
    print(f"      {orphans['orphan_msgs'] or '(none)'}")
    print(f"      locale keys without Msg: {orphans['locale_keys_without_msg'] or '(none)'}")
    print("  - Remove now-orphaned Tag/Limits/enum constants:")
    print(f"      {orphans['orphan_tags'] or '(none)'}")
    print("  - Remove the feature from docs/03-project-structure.md and glossary terms.")
    print("  - Add a CHANGELOG `Removed` entry and bump the minor version.")
    print("  - Run `make lint && make test && make feature-check`.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove a feature.")
    parser.add_argument("name")
    parser.add_argument("--reason", default="")
    parser.add_argument("--drop-data", default="false")
    parser.add_argument("--root", default=None)
    args = parser.parse_args()

    drop = str(args.drop_data).lower() in {"true", "1", "yes"}
    remove(root_path(args.root), args.name, args.reason, drop)


if __name__ == "__main__":
    main()
