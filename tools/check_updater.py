"""Exercise real uv/pipx/venv update handoffs offline in disposable environments.

The old version fixture is the current wheel relabeled 0.3.1, not a historical
0.3.1 artifact (which has no update command). Only release discovery is stubbed;
package-manager operations, process handoff and Skill protection are real.
"""

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import venv
import zipfile
from pathlib import Path

from installer_test_env import isolated_path


def old_wheel(wheel, directory):
    with zipfile.ZipFile(wheel) as source:
        metadata_name = next(n for n in source.namelist() if n.endswith("/METADATA"))
        metadata = source.read(metadata_name).decode()
        version = next(line[9:] for line in metadata.splitlines() if line.startswith("Version: "))
        old = "0.3.1"
        destination = directory / wheel.name.replace(version, old)
        files = {}
        for name in source.namelist():
            if name.endswith("/RECORD"):
                continue
            data = source.read(name)
            if name == metadata_name:
                data = metadata.replace(f"Version: {version}\n", f"Version: {old}\n").encode()
            if name == "yicloud/skill/SKILL.md":
                data += b"\nOld fixture Skill content.\n"
            if name == "yicloud/update.py":
                # Exercise the real console entry point, including Windows's .exe
                # launcher. Only the fixture's network discovery is replaced.
                release = dict(version=version, channel="fixture", spec=str(wheel))
                data += f"\nlatest_release = lambda: {release!r}\n".encode()
            files[name.replace(f"-{version}.dist-info/", f"-{old}.dist-info/")] = data
        record = io.StringIO(newline="")
        writer = csv.writer(record)
        for name, data in files.items():
            hashed = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            writer.writerow([name, "sha256=" + hashed, len(data)])
        record_name = metadata_name.replace(version, old).rsplit("/", 1)[0] + "/RECORD"
        writer.writerow([record_name, "", ""])
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as output:
            for name, data in files.items():
                output.writestr(name, data)
            output.writestr(record_name, record.getvalue())
    return destination, version


def verify(wheel, wheelhouse, manager):
    with tempfile.TemporaryDirectory(prefix=f"yicloud-update-{manager}-") as temporary:
        root = Path(temporary)
        old, version = old_wheel(wheel, root)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        for key in list(env):
            if key.startswith("YICLOUD_"):
                env.pop(key)
        env.update(
            PATH=isolated_path(root),
            HOME=str(root),
            USERPROFILE=str(root),
            CODEX_HOME=str(root / "codex"),
            YICLOUD_CONFIG=str(root / "config.json"),
            UV_TOOL_DIR=str(root / "tools"),
            UV_TOOL_BIN_DIR=str(root / "bin"),
            UV_CACHE_DIR=str(root / "cache"),
            UV_OFFLINE="true",
            UV_PYTHON_DOWNLOADS="never",
            PIPX_HOME=str(root / "pipx"),
            PIPX_BIN_DIR=str(root / "bin"),
            PIPX_LOG_DIR=str(root / "logs"),
            PIPX_MAN_DIR=str(root / "man"),
            PIPX_DEFAULT_PYTHON=sys.executable,
            PIP_NO_INDEX="1",
            PIP_FIND_LINKS=str(wheelhouse),
            PIP_DISABLE_PIP_VERSION_CHECK="1",
        )
        config = root / "uv.toml"
        config.write_text(
            "no-index = true\nfind-links = [" + json.dumps(wheelhouse.as_posix()) + "]\n"
        )
        env["UV_CONFIG_FILE"] = str(config)
        if manager == "venv":
            prefix = root / "standalone space"
            venv.EnvBuilder(with_pip=True).create(prefix)
            python = prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            command = [str(python), "-m", "pip", "install", str(old)]
        elif manager == "uv":
            prefix = root / "tools/yicloud-skill"
            command = ["uv", "tool", "install", "--python", sys.executable, str(old)]
        else:
            prefix = root / "pipx/venvs/yicloud-skill"
            command = ["pipx", "install", str(old)]
        subprocess.run(command, env=env, cwd=root, check=True, capture_output=True)
        python = prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        cli = prefix / ("Scripts/yicloud.exe" if os.name == "nt" else "bin/yicloud")

        def run(args, check=True):
            return subprocess.run(
                args,
                env=env,
                cwd=root,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=check,
            )

        # A local wheel fixture is intentionally not an automatic update source.
        # Normalize only fixture provenance to simulate a stable index installation.
        run(
            [
                str(python),
                "-I",
                "-c",
                "from importlib.metadata import distribution; from pathlib import Path; d=distribution('yicloud-skill'); Path(d._path, 'direct_url.json').unlink(missing_ok=True)",
            ]
        )
        run([str(cli), "skill", "install", "--target", "codex"])
        skill = root / "codex/skills/yicloud/SKILL.md"
        assert b"Old fixture" in skill.read_bytes()
        config_bytes = b'{"accounts": {}, "connections": {}, "migration_sentinel": "keep"}'
        (root / "config.json").write_bytes(config_bytes)
        command = [str(cli), "--json", "update"]
        checked = run([*command, "--check"])
        report = json.loads(checked.stdout)["data"]
        assert report["installation"]["manager"] == manager, report
        assert report["update_available"]
        # Local edits block the installer before any metadata/package changes.
        original = skill.read_bytes()
        skill.write_bytes(b"user edits")
        blocked = run(command, check=False)
        assert blocked.returncode != 0 and skill.read_bytes() == b"user edits"
        assert "0.3.1" in run([str(cli), "--version"]).stdout
        skill.write_bytes(original)
        result = run(command)
        data = json.loads(result.stdout)
        if os.name == "nt":
            assert data["data"]["state"] == "started" and not data["data"]["completed"]
            result_path = Path(data["data"]["result"])
            deadline = time.monotonic() + 60
            while not result_path.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            data = json.loads(result_path.read_text())
        assert data["ok"], data
        assert data["data"]["version"] == version
        assert data["data"]["skills"][0]["state"] == "matching"
        assert "Old fixture" not in skill.read_text()
        assert version in run([str(cli), "--version"]).stdout
        assert (root / "config.json").read_bytes() == config_bytes
        assert not (root / ".claude").exists()
        assert not list(prefix.parent.glob(".*-yicloud-update.lock"))
        print(
            f"{manager}: real offline update, process handoff, Skill sync/edit protection and config preservation passed"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--manager", choices=["uv", "pipx", "venv", "all"], default="all")
    args = parser.parse_args()
    wheels = list(args.dist.glob("*.whl"))
    assert len(wheels) == 1
    managers = ["uv", "pipx", "venv"] if args.manager == "all" else [args.manager]
    for selected in managers:
        if selected != "venv" and not shutil.which(selected):
            raise SystemExit(f"Required manager missing: {selected}")
        verify(wheels[0].resolve(), args.wheelhouse.resolve(), selected)
