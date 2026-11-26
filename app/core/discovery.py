"""Feature auto-discovery: import `app.features.<feature>.<submodule>` for every feature."""

import importlib
import pkgutil
from types import ModuleType

import app.features as features_pkg


def feature_modules(submodule: str) -> list[ModuleType]:
    found: list[ModuleType] = []
    for info in pkgutil.iter_modules(features_pkg.__path__):
        if info.name.startswith("_"):
            continue
        target = f"{features_pkg.__name__}.{info.name}.{submodule}"
        try:
            found.append(importlib.import_module(target))
        except ModuleNotFoundError as exc:
            if exc.name != target:  # only swallow "this feature has no such module"
                raise
    return found
