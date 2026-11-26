"""Documentation structure guards: READMEs, doc links, module docstrings, root files."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
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


def _feature_dirs() -> list[Path]:
    fdir = ROOT / "app" / "features"
    return [p for p in fdir.iterdir() if p.is_dir() and not p.name.startswith("_")]


def test_feature_readmes_have_all_headings_in_order():
    for feature in _feature_dirs():
        readme = feature / "README.md"
        assert readme.exists(), f"{feature.name}: missing README.md"
        text = readme.read_text("utf-8")
        positions = [text.find(h) for h in REQUIRED_HEADINGS]
        assert all(p >= 0 for p in positions), f"{feature.name}: missing a required heading"
        assert positions == sorted(positions), f"{feature.name}: headings out of order"


def test_every_doc_is_linked_from_docs_readme():
    readme = (DOCS / "README.md").read_text("utf-8")
    for md in DOCS.rglob("*.md"):
        if md.name == "README.md" and md.parent == DOCS:
            continue
        rel = md.relative_to(DOCS).as_posix()
        assert rel in readme, f"{rel} is not linked from docs/README.md"


def test_python_modules_have_docstrings():
    for base in (ROOT / "app", ROOT / "scripts"):
        for py in base.rglob("*.py"):
            text = py.read_text("utf-8")
            if not text.strip():
                continue
            module = ast.parse(text)
            assert ast.get_docstring(module), f"{py.relative_to(ROOT)}: missing module docstring"


def test_root_files_exist():
    for name in ("AGENTS.md", "CLAUDE.md", "README.md"):
        assert (ROOT / name).exists(), f"missing {name}"


def test_features_appear_in_project_structure():
    structure = (DOCS / "03-project-structure.md").read_text("utf-8")
    for feature in _feature_dirs():
        assert feature.name in structure, f"{feature.name} missing from 03-project-structure.md"
