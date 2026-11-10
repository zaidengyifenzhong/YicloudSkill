"""Exercise the distributable preview helper without importing the CLI into it."""

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from click.testing import CliRunner
import pytest

from yicloud.cli import main
import yicloud.skill_install as installer


SCRIPT = Path(__file__).resolve().parents[1] / "src/yicloud/skill/scripts/request_from_preview.py"


@pytest.fixture
def preview():
    return {
        "ok": True,
        "data": {
            "method": "POST",
            "validation": "passed",
            "validation_scope": "local_pinned_sdk_request",
            "query": [],
            "body": {
                "False": False,
                "Zero": 0,
                "Null": None,
                "List": [False, 0, None, {"text": "中文"}],
                "Command": ["sh", "-c", "printf '%s\\n' \"$HOME\"; echo `date`; echo '你好'"],
            },
        },
    }


def export(tmp_path, raw, *args, output=None, script=SCRIPT):
    path = output if output is not None else tmp_path / "request.json"
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(script), "--output", str(path), *args],
        input=raw,
        cwd=tmp_path,
        capture_output=True,
        timeout=15,
        check=False,
    )
    return result, path


@pytest.mark.parametrize("use_file", [False, True])
def test_helper_preserves_values_outside_skill_without_site_packages(tmp_path, preview, use_file):
    raw = json.dumps(preview, ensure_ascii=False).encode("utf-8")
    args = []
    if use_file:
        source = tmp_path / "preview.json"
        source.write_bytes(raw)
        args = ["--input", str(source)]
    result, output = export(tmp_path, raw, *args)
    assert result.returncode == 0 and not result.stdout and not result.stderr
    assert json.loads(output.read_text(encoding="utf-8")) == preview["data"]["body"]
    if os.name != "nt":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "section,key,value",
    [
        (None, "ok", False),
        ("data", "method", "GET"),
        ("data", "body", []),
        ("data", "body", {"nested": [{"command": "prefix[REDACTED]suffix"}]}),
    ],
)
def test_helper_rejects_non_exportable_previews(tmp_path, preview, section, key, value):
    target = preview[section] if section else preview
    target[key] = value
    result, output = export(tmp_path, json.dumps(preview).encode())
    assert result.returncode == 1 and not output.exists() and not result.stdout
    assert result.stderr and b"Traceback" not in result.stderr


@pytest.mark.parametrize("raw", [b'PRIVATE_LITERAL{"broken":}', b"\xff"])
def test_helper_rejects_bad_input_without_echoing_it(tmp_path, raw):
    result, output = export(tmp_path, raw)
    assert result.returncode == 1 and not output.exists() and not result.stdout
    assert b"PRIVATE_LITERAL" not in result.stderr and b"Traceback" not in result.stderr


@pytest.mark.parametrize("number,location", [("NaN", "body"), ("1e9999", "meta")])
def test_helper_rejects_nonfinite_json_everywhere(tmp_path, preview, number, location):
    if location == "body":
        preview["data"]["body"]["bad"] = "NUMBER_LITERAL"
    else:
        preview["meta"] = "NUMBER_LITERAL"
    raw = json.dumps(preview).replace('"NUMBER_LITERAL"', number).encode()
    result, output = export(tmp_path, raw)
    assert result.returncode == 1 and not output.exists() and not result.stdout


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "dangling_symlink", "parent"])
def test_helper_never_replaces_existing_paths_or_creates_parents(tmp_path, preview, kind):
    output = tmp_path / "output.json"
    existing = tmp_path / "user.json"
    existing.write_text("keep", encoding="utf-8")
    if kind == "file":
        output.write_text("keep output", encoding="utf-8")
    elif kind == "directory":
        output.mkdir()
    elif kind in {"symlink", "dangling_symlink"}:
        try:
            output.symlink_to(existing if kind == "symlink" else tmp_path / "absent")
        except OSError:
            pytest.skip("Symlink creation is unavailable")
        link_target = output.readlink()
        assert not (tmp_path / "absent").exists()
    else:
        output = tmp_path / "absent-parent" / "request.json"
    result, _ = export(tmp_path, json.dumps(preview).encode(), output=output)
    assert result.returncode == 1 and not result.stdout
    assert existing.read_text(encoding="utf-8") == "keep"
    if kind == "file":
        assert output.read_text(encoding="utf-8") == "keep output"
    elif kind == "directory":
        assert output.is_dir()
    elif kind in {"symlink", "dangling_symlink"}:
        assert output.is_symlink() and output.readlink() == link_target
        assert not (tmp_path / "absent").exists()
    else:
        assert not output.parent.exists()


def test_installed_helper_exports_real_shortcut_preview_for_file_dryrun(tmp_path):
    result = CliRunner().invoke(
        main,
        [
            "--json",
            "job",
            "create",
            "--name",
            "fixture",
            "--project",
            "p",
            "--zone",
            "z",
            "--image",
            "fixture/image",
            "--quota-group",
            "quota",
            "--cpu",
            "2",
            "--memory",
            "8Gi",
            "--command",
            "printf '你好'",
            "--no-use-private-machine",
            "--max-running-duration",
            "2h",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    expected = json.loads(result.output)["data"]["body"]
    skill = tmp_path / "installed"
    installer.install("codex", skill)
    script = skill / "scripts/request_from_preview.py"
    assert script.is_file() and not script.is_symlink()
    exported, request = export(tmp_path, result.output.encode("utf-8"), script=script)
    assert exported.returncode == 0, exported.stderr
    assert json.loads(request.read_text(encoding="utf-8")) == expected
    checked = CliRunner().invoke(
        main, ["--json", "job", "create", "--file", str(request), "--dry-run"]
    )
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.output)["data"]["body"] == expected
    installer.install("codex", skill, uninstall=True)
    assert not skill.exists()
