"""Install a wheel in an independent venv and exercise CLI/packaged skill outside the repository.

Optional --wheelhouse DIR keeps dependency installation offline after pip download.
"""

import argparse
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("wheel", type=Path)
p.add_argument("--wheelhouse", type=Path)
args = p.parse_args()
wheel = args.wheel.resolve()
with tempfile.TemporaryDirectory(prefix="yicloud-wheel-") as scratch:
    root = Path(scratch)
    environment = root / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    bin_dir = environment / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    cli = bin_dir / ("yicloud.exe" if os.name == "nt" else "yicloud")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    for name in list(env):
        if name.startswith("YICLOUD_"):
            env.pop(name)
    env["YICLOUD_CONFIG"] = str(root / "config.json")
    command = [str(python), "-m", "pip", "install"]
    if args.wheelhouse:
        command += ["--no-index", "--find-links", str(args.wheelhouse.resolve())]
    subprocess.run([*command, str(wheel)], cwd=root, env=env, check=True)

    def call(*values):
        result = subprocess.run(
            [str(cli), *values],
            cwd=root,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)

    assert len(call("--json", "api", "list")["data"]) == 227
    assert call("--json", "api", "describe", "job", "CreateJob")["data"]["schema"]["required"]
    skill = root / "installed-skill"
    call("--json", "skill", "install", "--target", "codex", "--path", str(skill))
    assert (skill / "SKILL.md").is_file()
    assert len(list((skill / "references").glob("*.md"))) == 13
    call("--json", "skill", "uninstall", "--target", "codex", "--path", str(skill))
    assert not skill.exists()
    assert not (root / "config.json").exists()
print("Independent wheel installation and packaged skill verified")
