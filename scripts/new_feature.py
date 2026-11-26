"""Scaffold a new feature folder, its README, and its registry row.

Usage: `uv run python scripts/new_feature.py <name>` (or `make feature name=<name>`).
The script is idempotent-safe: it refuses to overwrite an existing folder or registry row.
"""

from __future__ import annotations

import argparse
import re
import sys

from _features import (
    current_version,
    features_dir,
    read_registry,
    root_path,
    today,
    write_registry,
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_INIT = '"""<Feature> feature package."""\n'

_ROUTER = '''"""<Name> router: HTTP layer only; delegate all rules to `service.py`."""

from fastapi import APIRouter

from app.core.constants import Tag
from app.shared.schemas import ApiResponse

router = APIRouter(prefix="/{name}", tags=["<Name>"])


# Add routes here. Each route: response_model + summary + description, body calls the service.
'''

_SERVICE = '''"""<Name> service: business rules; raise `AppError` subclasses with `Msg` keys."""

# Implement module-level async functions. Copy the pattern from app/features/notes/service.py.
'''

_REPOSITORY = '''"""<Name> repository: data access only; subclass `BaseRepository`."""

from app.core.database import db
from app.shared.helpers.repository import BaseRepository


class {cls}Repository(BaseRepository):
    """Add only feature-specific queries here."""


{name}_repo = {cls}Repository(db.{name})
'''

_SCHEMAS = '''"""<Name> schemas: request/response models extending `ApiModel`."""

# Define Pydantic models extending app.shared.schemas.ApiModel (camelCase, ORM-friendly).
'''

_README = """# {name} feature

> One-line summary.

## Status
`experimental`. Since: {version}. Owner files: this folder + <prisma models>.

## Purpose
_TODO: why this feature exists._

## Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| _TBD_ | _TBD_ | _TBD_ | _TBD_ |

## Data model
_TODO: Prisma models or "none"._

## Business rules
_TODO: the rules the service enforces._

## Dependencies
_TODO: other features' services/repos/deps used._

## Extending
_TODO: how to grow this feature._

## Change history
| Version | Date | Type | Summary |
|---|---|---|---|
| {version} | {today} | Added | Initial version |
"""


def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def scaffold(root, name: str) -> None:
    fdir = features_dir(root)
    target = fdir / name
    version = current_version(root)

    if target.exists():
        sys.exit(f"error: folder already exists: {target}")
    active, _ = read_registry(root)
    if any(row[0] == name for row in active):
        sys.exit(f"error: '{name}' already has an Active registry row")

    target.mkdir(parents=True)
    (target / "__init__.py").write_text(_INIT.replace("<Feature>", _camel(name)), "utf-8")
    (target / "router.py").write_text(_ROUTER.format(name=name), "utf-8")
    (target / "service.py").write_text(_SERVICE.replace("<Name>", _camel(name)), "utf-8")
    (target / "schemas.py").write_text(_SCHEMAS.replace("<Name>", _camel(name)), "utf-8")
    (target / "repository.py").write_text(_REPOSITORY.format(cls=_camel(name), name=name), "utf-8")
    (target / "README.md").write_text(
        _README.format(name=name, version=version, today=today()), "utf-8"
    )

    active.append(
        [
            name,
            "experimental",
            f"/{name}",
            "none",
            "none",
            version,
            version,
            f"[link](../app/features/{name}/README.md)",
        ]
    )
    write_registry(root, active, read_registry(root)[1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a new feature.")
    parser.add_argument("name")
    parser.add_argument("--root", default=None, help="repo root (default: FEATURE_ROOT or auto)")
    args = parser.parse_args()

    name = args.name
    if not _NAME_RE.match(name):
        sys.exit(f"error: invalid name '{name}' (use ^[a-z][a-z0-9_]*$)")

    root = root_path(args.root)
    scaffold(root, name)

    print(f"created app/features/{name}/ and a registry row (experimental).")
    print("\nNext steps (see docs/playbooks/add-feature.md):")
    print(f"  1. Fill app/features/{name}/README.md (Purpose, Endpoints, Data model, Rules).")
    print("  2. If persistence is needed: edit prisma/schema.prisma, run `make migrate`.")
    print("  3. Add Tag/Limits constants and Msg keys in EVERY locale file.")
    print("  4. Implement schemas.py -> repository.py -> service.py -> router.py (copy notes).")
    print(f"  5. Add tests/features/test_{name}.py.")
    print("  6. Update docs/03-project-structure.md and docs/CHANGELOG.md; bump version.")
    print("  7. Run `make lint && make test && make feature-check`.")


if __name__ == "__main__":
    main()
