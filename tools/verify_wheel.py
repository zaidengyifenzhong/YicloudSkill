"""Install a wheel in an independent venv and exercise CLI/packaged skill outside the repository.

Optional --wheelhouse DIR keeps dependency installation offline after pip download.
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
import venv
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("wheel", type=Path, help="Wheel file or directory containing one project wheel.")
p.add_argument("--wheelhouse", type=Path)
args = p.parse_args()
if args.wheel.is_dir():
    wheels = sorted(args.wheel.glob("yicloud_skill-*.whl"))
    if len(wheels) != 1:
        p.error("Expected exactly one yicloud-skill wheel; pass a specific wheel file")
    args.wheel = wheels[0]
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
    # Exercise packaged command adapters, pure creation rules and the client protocol together.
    for kind, scope in (("workspace", "project"), ("job", "tenant")):
        options = [
            "--name",
            "fixture",
            "--project",
            "fixture-project",
            "--zone",
            "fixture-zone",
            "--image",
            "fixture/image:tag",
            "--sku",
            "fixture-sku",
            "--sku-scope",
            scope,
            "--dry-run",
        ]
        if kind == "job":
            options += ["--command", "printf fixture"]
        request = call("--json", kind, "create", *options)["data"]
        assert request["validation"] == "passed" and request["body"]["Name"] == "fixture"
    assert (
        call(
            "--json",
            "ray",
            "stop",
            "fixture",
            "--project",
            "fixture-project",
            "--zone",
            "fixture-zone",
            "--dry-run",
        )["data"]["validation"]
        == "passed"
    )
    assert (
        call(
            "--json",
            "serving",
            "scale",
            "fixture",
            "--project",
            "fixture-project",
            "--zone",
            "fixture-zone",
            "--replicas",
            "0",
            "--dry-run",
        )["data"]["body"]["Replicas"]
        == 0
    )
    skill = root / "installed-skill"
    call("--json", "skill", "install", "--target", "codex", "--path", str(skill))
    assert (skill / "SKILL.md").is_file()
    # Templates must work without a source checkout or user account.
    for kind in ("workspace", "job", "ray", "serving"):
        template = skill / "assets" / "examples" / f"{kind}.json"
        request = call("--json", kind, "create", "--file", str(template), "--dry-run")["data"]
        assert request["validation"] == "passed"
    workers = skill / "assets" / "examples" / "workers.json"
    request = call(
        "--json",
        "ray",
        "workers",
        "fixture",
        "--project",
        "fixture-project",
        "--zone",
        "fixture-zone",
        "--file",
        str(workers),
        "--dry-run",
    )["data"]
    assert request["validation"] == "passed"
    # Validate links after installation, rather than relying on a reference file count.
    for document in skill.rglob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if "://" not in target and not target.startswith("#"):
                assert (document.parent / target.split("#")[0]).exists(), (document, target)
    call("--json", "skill", "uninstall", "--target", "codex", "--path", str(skill))
    assert not skill.exists()
    assert not (root / "config.json").exists()
print("Independent wheel installation and packaged skill verified")
