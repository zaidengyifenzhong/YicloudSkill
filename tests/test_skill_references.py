"""Keep source and installed Skill reference checks consistent."""

import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from yicloud.skill_install import install


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "src/yicloud/skill"


@pytest.fixture
def checkers(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    return (
        importlib.import_module("skill_references"),
        importlib.import_module("validate_skill"),
        importlib.import_module("evaluate_skill"),
    )


@pytest.fixture
def skill(tmp_path):
    root = tmp_path / "skill"
    shutil.copytree(SKILL, root)
    return root


def add_link(skill, target):
    probe = skill / "references/jobs/probe.md"
    probe.write_text(f"[reference]({target})\n", encoding="utf-8")
    return probe


def reports(checkers, monkeypatch, skill):
    references, validator, evaluator = checkers
    monkeypatch.setattr(evaluator, "SKILL", skill)
    count, broken = references.local_references(skill, sorted(skill.rglob("*.md")))
    context = evaluator.measure_skill()
    assert context["local_links"] == count
    assert context["broken_links"] == broken
    return validator, context


@pytest.mark.parametrize(
    "kind", ["escape", "directory", "unshipped", "symlink_internal", "symlink_external"]
)
def test_both_checks_reject_existing_but_undistributed_targets(
    tmp_path, skill, checkers, monkeypatch, kind
):
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    if kind == "escape":
        target = "../../../outside.md"
    elif kind == "directory":
        target = ".."
    elif kind == "unshipped":
        (skill / "references/request.json").write_text("{}", encoding="utf-8")
        target = "../request.json"
    else:
        alias = skill / "references/alias.md"
        try:
            alias.symlink_to(
                skill / "references/access.md" if kind == "symlink_internal" else outside
            )
        except OSError:
            pytest.skip("Symlink creation is unavailable")
        target = "../alias.md"
    add_link(skill, target)
    validator, context = reports(checkers, monkeypatch, skill)
    assert context["broken_links"] == [{"file": "references/jobs/probe.md", "target": target}]
    with pytest.raises(ValueError, match="Invalid local Skill references"):
        validator.validate(skill)


@pytest.mark.parametrize(
    "target",
    [
        "observe.md",
        "../access.md",
        "../encoded%20name.md?download=1#heading",
        "../../scripts/request_from_preview.py",
    ],
)
def test_both_checks_accept_distributed_files_and_decoded_paths(
    skill, checkers, monkeypatch, target
):
    (skill / "references/encoded name.md").write_text("encoded filename", encoding="utf-8")
    add_link(skill, target)
    validator, context = reports(checkers, monkeypatch, skill)
    assert not context["broken_links"]
    validator.validate(skill)


def test_drive_absolute_path_is_not_mistaken_for_an_external_url(skill, checkers, monkeypatch):
    target = "C:/outside/safe.md"
    add_link(skill, target)
    validator, context = reports(checkers, monkeypatch, skill)
    assert context["broken_links"] == [{"file": "references/jobs/probe.md", "target": target}]
    with pytest.raises(ValueError, match="Invalid local Skill references"):
        validator.validate(skill)


@pytest.mark.parametrize("kind", ["external_alias", "internal_alias", "same_target_alias", "empty"])
def test_cancelled_path_prefixes_must_also_exist_in_the_installed_skill(
    tmp_path, skill, checkers, monkeypatch, kind
):
    (skill / "references/safe.md").write_text("safe", encoding="utf-8")
    prefix = skill / "references/unused"
    if kind == "empty":
        prefix.mkdir()
    else:
        if kind == "external_alias":
            target_dir = tmp_path / "outside/deep"
        elif kind == "internal_alias":
            target_dir = skill / "scripts/deep"
        else:
            target_dir = skill / "references/deep"
        target_dir.mkdir(parents=True)
        (target_dir.parent / "safe.md").write_text("target", encoding="utf-8")
        try:
            prefix.symlink_to(target_dir, target_is_directory=True)
        except OSError:
            pytest.skip("Symlink creation is unavailable")
    target = "../unused/../safe.md"
    add_link(skill, target)
    validator, context = reports(checkers, monkeypatch, skill)
    assert context["broken_links"] == [{"file": "references/jobs/probe.md", "target": target}]
    with pytest.raises(ValueError, match="Invalid local Skill references"):
        validator.validate(skill)
    monkeypatch.setattr("yicloud.skill_install.files", lambda _: skill.parent)
    installed = tmp_path / "installed"
    install("codex", installed)
    assert not (installed / "references/unused").exists()
    assert (installed / "references/safe.md").is_file()
    install("codex", installed, uninstall=True)
    assert not installed.exists()


def test_external_urls_and_same_page_fragments_are_not_file_targets(skill, checkers, monkeypatch):
    references, _, _ = checkers
    before, _ = references.local_references(skill, sorted(skill.rglob("*.md")))
    probe = add_link(skill, "https://example.invalid/absent.md")
    with probe.open("a", encoding="utf-8") as stream:
        stream.write("[mail](mailto:reader@example.invalid)\n[fragment](#missing-heading)\n")
    validator, context = reports(checkers, monkeypatch, skill)
    assert context["local_links"] == before and not context["broken_links"]
    validator.validate(skill)


def test_actual_temporary_install_has_a_closed_reference_set(tmp_path, checkers):
    references, validator, _ = checkers
    dest = tmp_path / "installed"
    install("codex", dest)
    count, broken = references.local_references(dest, sorted(dest.rglob("*.md")))
    assert count > 0 and not broken
    assert (dest / "scripts/request_from_preview.py").is_file()
    validator.validate(dest)
    install("codex", dest, uninstall=True)
    assert not dest.exists()


def test_tool_entrypoints_work_outside_repo_and_reject_mutation_under_optimization(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(ROOT / "src", project / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "tools", project / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    copied_skill = project / "src/yicloud/skill"
    # A real existing file beyond the Skill root used to pass the exists-only checks.
    probe = add_link(copied_skill, outside.as_posix())
    validation = subprocess.run(
        [sys.executable, "-O", str(project / "tools/validate_skill.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert validation.returncode != 0 and "Invalid local Skill references" in validation.stderr
    # CI runs the full evaluator separately; this mutation targets its real link/report path.
    evaluate_links = """
import runpy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).parent))
main = runpy.run_path(sys.argv[1])["main"]
main.__globals__["cli_cases"] = lambda env: []
raise SystemExit(main())
"""
    evaluation = subprocess.run(
        [sys.executable, "-I", "-c", evaluate_links, str(project / "tools/evaluate_skill.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    report = json.loads(evaluation.stdout)
    assert evaluation.returncode == 1 and report["passed"] is False
    assert report["network_guard_passed"] is True
    assert report["cases"] == [] and report["context"]["local_links"] > 0
    assert report["context"]["broken_links"] == [
        {"file": "references/jobs/probe.md", "target": outside.as_posix()}
    ]
    probe.unlink()
    valid = subprocess.run(
        [sys.executable, "-O", str(project / "tools/validate_skill.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert valid.returncode == 0, valid.stderr
