"""Lifecycle guards: registry parity, workflow docs, orphan checks, and an ADD/REMOVE round trip."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts._features import find_orphans, read_registry

ROOT = Path(__file__).resolve().parents[1]


def _feature_dirs() -> list[str]:
    fdir = ROOT / "app" / "features"
    return sorted(p.name for p in fdir.iterdir() if p.is_dir() and not p.name.startswith("_"))


def test_registry_parity():
    active, removed = read_registry(ROOT)
    active_names = {r[0] for r in active}
    removed_names = {r[0] for r in removed}
    folders = set(_feature_dirs())
    assert folders == active_names, f"folder/registry mismatch: {folders ^ active_names}"
    assert not (active_names & removed_names), "a feature is in both tables"


def test_feature_readmes_have_change_history():
    for name in _feature_dirs():
        text = (ROOT / "app" / "features" / name / "README.md").read_text("utf-8")
        tail = text.split("## Change history", 1)[1]
        rows = [ln for ln in tail.splitlines() if ln.strip().startswith("|")]
        data_rows = [r for r in rows if not set(r.replace("|", "").strip()) <= set("-: ")]
        assert len(data_rows) >= 2, f"{name}: empty Change history"


def test_lifecycle_docs_exist_and_linked():
    readme = (ROOT / "docs" / "README.md").read_text("utf-8")
    for rel in (
        "12-feature-lifecycle.md",
        "playbooks/update-feature.md",
        "playbooks/remove-feature.md",
    ):
        assert rel in readme, f"{rel} not linked from docs/README.md"


def test_agents_md_has_required_sections():
    text = (ROOT / "AGENTS.md").read_text("utf-8")
    assert "Task workflow" in text
    assert "Definition of Done" in text


def test_no_orphans_or_locale_drift():
    orphans = find_orphans(ROOT)
    assert not orphans["orphan_msgs"], orphans["orphan_msgs"]
    assert not orphans["orphan_tags"], orphans["orphan_tags"]
    assert not orphans["locale_keys_without_msg"], orphans["locale_keys_without_msg"]
    assert not orphans["msgs_missing_in_locale"], orphans["msgs_missing_in_locale"]


def test_check_feature_exits_zero():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_feature.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _copy_skeleton(dest: Path) -> None:
    """Copy the minimal repo skeleton the scripts need into `dest`."""
    (dest / "app" / "core" / "locales").mkdir(parents=True)
    (dest / "docs").mkdir()
    shutil.copy(ROOT / "pyproject.toml", dest / "pyproject.toml")
    shutil.copy(ROOT / "docs" / "features.md", dest / "docs" / "features.md")
    shutil.copy(ROOT / "app" / "core" / "messages.py", dest / "app" / "core" / "messages.py")
    shutil.copy(ROOT / "app" / "core" / "constants.py", dest / "app" / "core" / "constants.py")
    for jf in (ROOT / "app" / "core" / "locales").glob("*.json"):
        shutil.copy(jf, dest / "app" / "core" / "locales" / jf.name)
    shutil.copytree(
        ROOT / "app" / "features",
        dest / "app" / "features",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # check_feature also wants a CHANGELOG; copy it.
    shutil.copy(ROOT / "docs" / "CHANGELOG.md", dest / "docs" / "CHANGELOG.md")


def test_add_remove_round_trip_on_temp_copy():
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "repo"
        dest.mkdir()
        _copy_skeleton(dest)

        add = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "new_feature.py"), "demo", "--root", str(dest)],
            capture_output=True,
            text=True,
        )
        assert add.returncode == 0, add.stdout + add.stderr
        assert (dest / "app" / "features" / "demo" / "README.md").exists()
        active, _ = read_registry(dest)
        assert any(r[0] == "demo" for r in active)

        remove = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "remove_feature.py"),
                "demo",
                "--reason",
                "verification",
                "--drop-data",
                "false",
                "--root",
                str(dest),
            ],
            capture_output=True,
            text=True,
        )
        assert remove.returncode == 0, remove.stdout + remove.stderr
        assert not (dest / "app" / "features" / "demo").exists()
        _, removed = read_registry(dest)
        assert any(r[0] == "demo" for r in removed)


def test_new_docs_and_adrs_linked():
    readme = (ROOT / "docs" / "README.md").read_text("utf-8")
    for rel in (
        "13-background-jobs.md",
        "14-audit-and-activity-logging.md",
        "15-caching.md",
        "playbooks/add-background-job.md",
        "playbooks/add-cached-read.md",
        "playbooks/add-audit-event.md",
        "decisions/0005-postgres-backed-job-queue.md",
        "decisions/0006-audit-and-activity-split.md",
        "decisions/0007-cache-design.md",
        "decisions/0008-infrastructure-repositories-and-import-rules.md",
    ):
        assert rel in readme, f"{rel} not linked from docs/README.md"


def test_registry_has_new_features():
    active, _ = read_registry(ROOT)
    names = {r[0] for r in active}
    assert {"jobs", "audit", "maintenance"} <= names


def test_planted_unaudited_mutation_fails_check():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "repo"
        dest.mkdir()
        _copy_skeleton(dest)
        bad = (
            "\n\nasync def create_x(user, payload):\n    return await notes_repo.create(data={})\n"
        )
        svc = dest / "app" / "features" / "notes" / "service.py"
        svc.write_text(svc.read_text("utf-8") + bad, "utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_feature.py"), "--root", str(dest)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "mutation without audit.record" in result.stdout
