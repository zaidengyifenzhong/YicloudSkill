"""The installed Skill has all its referenced instructions and helpers."""

import importlib
from pathlib import Path


from yicloud.skill_install import install


ROOT = Path(__file__).resolve().parents[1]


def test_actual_temporary_install_has_a_closed_reference_set(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    references = importlib.import_module("skill_references")
    validator = importlib.import_module("validate_skill")
    dest = tmp_path / "installed"
    install("codex", dest)
    count, broken = references.local_references(dest, sorted(dest.rglob("*.md")))
    assert count > 0 and not broken
    assert (dest / "scripts/request_from_preview.py").is_file()
    validator.validate(dest)
    install("codex", dest, uninstall=True)
    assert not dest.exists()
