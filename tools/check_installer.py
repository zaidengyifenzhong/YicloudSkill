"""Exercise the platform installer against an offline wheelhouse and isolated tool/skill roots.

Requires uv or pipx already installed, and Python 3.12 for the uv installer.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("wheel", type=Path, help="Wheel file or directory containing one project wheel.")
p.add_argument("--wheelhouse", type=Path, required=True)
p.add_argument("--manager", choices=["uv", "pipx"], default="uv")
args = p.parse_args()
if args.wheel.is_dir():
    wheels = sorted(args.wheel.glob("yicloud_skill-*.whl"))
    if len(wheels) != 1:
        p.error("Expected exactly one yicloud-skill wheel; pass a specific wheel file")
    args.wheel = wheels[0]
repo = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="yicloud-installer-") as directory:
    scratch = Path(directory)
    env = dict(os.environ)
    env.update(
        CODEX_HOME=str(scratch / "codex"),
        PYTHONUTF8="1",
        YICLOUD_CONFIG=str(scratch / "config.json"),
        UV_TOOL_DIR=str(scratch / "tools"),
        UV_TOOL_BIN_DIR=str(scratch / "bin"),
        UV_CACHE_DIR=str(scratch / "cache"),
        UV_OFFLINE="true",
        PIPX_HOME=str(scratch / "pipx"),
        PIPX_MAN_DIR=str(scratch / "man"),
        PIPX_LOG_DIR=str(scratch / "logs"),
        PIPX_BIN_DIR=str(scratch / "bin"),
        PIPX_DEFAULT_PYTHON=sys.executable,
        PIP_NO_INDEX="1",
        PIP_FIND_LINKS=str(args.wheelhouse.resolve()),
        PIP_DISABLE_PIP_VERSION_CHECK="1",
    )
    config = scratch / "uv.toml"
    config.write_text(
        "no-index = true\nfind-links = ["
        + json.dumps(args.wheelhouse.resolve().as_posix())
        + "]\n",
        encoding="utf-8",
    )
    env["UV_CONFIG_FILE"] = str(config)
    if os.name == "nt":
        shell = shutil.which("pwsh")
        if not shell:
            raise SystemExit("PowerShell 7 is required to verify the Windows installer")
        command = [
            shell,
            "-NoProfile",
            "-File",
            str(repo / "install.ps1"),
            "-Manager",
            args.manager,
            "-Target",
            "codex",
            "-Source",
            str(args.wheel.resolve()),
        ]
    else:
        command = [
            "bash",
            str(repo / "install.sh"),
            "--manager",
            args.manager,
            "--target",
            "codex",
            "--source",
            str(args.wheel.resolve()),
        ]
    subprocess.run(command, env=env, cwd=scratch, check=True)
    assert (scratch / "codex/skills/yicloud/SKILL.md").is_file()
    assert (scratch / "codex/skills/yicloud/references/diagnostics/api.md").is_file()
    assert not (scratch / "config.json").exists()
print(f"{args.manager} installer and Codex skill verified in isolated directories")
