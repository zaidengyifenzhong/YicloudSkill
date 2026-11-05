"""Exercise the distributable preview helper without importing the CLI into it."""

import json
import os
from pathlib import Path
import runpy
import stat
import subprocess
import sys

from click.testing import CliRunner
import pytest

from yicloud.cli import main
from yicloud.errors import ConfigurationError
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
        (None, "ok", 1),
        (None, "data", []),
        (None, "data", None),
        ("data", "method", "GET"),
        ("data", "method", "post"),
        ("data", "validation", "failed"),
        ("data", "validation_scope", "server"),
        ("data", "query", None),
        ("data", "query", [{"name": "x", "value": "y"}]),
        ("data", "body", []),
        ("data", "body", None),
        ("data", "body", {"nested": [{"command": "prefix[REDACTED]suffix"}]}),
        ("data", "body", {"[REDACTED]": "value"}),
    ],
)
def test_helper_rejects_non_exportable_previews(tmp_path, preview, section, key, value):
    target = preview[section] if section else preview
    target[key] = value
    result, output = export(tmp_path, json.dumps(preview).encode())
    assert result.returncode == 1 and not output.exists() and not result.stdout
    assert result.stderr and b"Traceback" not in result.stderr


@pytest.mark.parametrize("raw", [b"", b"{}{}", b"[]", b'PRIVATE_LITERAL{"broken":}', b"\xff"])
def test_helper_rejects_bad_input_without_echoing_it(tmp_path, raw):
    result, output = export(tmp_path, raw)
    assert result.returncode == 1 and not output.exists() and not result.stdout
    assert b"PRIVATE_LITERAL" not in result.stderr and b"Traceback" not in result.stderr


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e9999", "-1e9999"])
@pytest.mark.parametrize("location", ["body", "meta"])
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


def test_helper_removes_its_partial_file_on_write_failure(tmp_path, monkeypatch):
    helper = runpy.run_path(str(SCRIPT))
    output = tmp_path / "partial.json"

    class FailingWriter:
        def __init__(self, descriptor):
            self.descriptor = descriptor

        def __enter__(self):
            return self

        def write(self, payload):
            os.write(self.descriptor, payload[:5])
            raise OSError("injected write failure")

        def __exit__(self, *args):
            os.close(self.descriptor)

    monkeypatch.setattr(os, "fdopen", lambda descriptor, mode: FailingWriter(descriptor))
    with pytest.raises(OSError, match="injected"):
        helper["write_new"](output, b'{"key":"value"}')
    assert not output.exists()


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


def test_python_helper_install_status_local_edits_upgrade_and_uninstall(tmp_path, monkeypatch):
    package = tmp_path / "package"
    source = package / "skill"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    helper = scripts / "request_from_preview.py"
    helper.write_text("print('version one')", encoding="utf-8")
    (source / "SKILL.md").write_text("skill", encoding="utf-8")
    (scripts / "unsupported.sh").write_text("exit 0", encoding="utf-8")
    (source / "outside.py").write_text("pass", encoding="utf-8")
    (scripts / "nested").mkdir()
    (scripts / "nested/unsupported.py").write_text("pass", encoding="utf-8")
    monkeypatch.setattr(installer, "files", lambda _: package)
    dest = tmp_path / "installed"
    installer.install("codex", dest)
    installed = dest / "scripts/request_from_preview.py"
    assert installer.status("codex", dest)["targets"][0]["state"] == "matching"
    assert installed.read_bytes() == helper.read_bytes()
    assert not (dest / "scripts/unsupported.sh").exists()
    assert not (dest / "outside.py").exists()
    assert not (dest / "scripts/nested").exists()
    helper.write_text("print('version two')", encoding="utf-8")
    assert installer.status("codex", dest)["targets"][0]["different"] == [
        "scripts/request_from_preview.py"
    ]
    installer.install("codex", dest)
    assert installed.read_bytes() == helper.read_bytes()
    installed.write_text("local user edits", encoding="utf-8")
    row = installer.status("codex", dest)["targets"][0]
    assert row["local_edits"] == ["scripts/request_from_preview.py"]
    with pytest.raises(ConfigurationError, match="local edits"):
        installer.install("codex", dest)
    installer.install("codex", dest, uninstall=True)
    assert installed.read_text(encoding="utf-8") == "local user edits"
    assert not (dest / installer.MARKER).exists()
