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

    operations = call("--json", "api", "list")["data"]
    assert len(operations) == 227
    assert sum(row["command"] is not None for row in operations) == 225
    assert (
        call("--json", "api", "describe", "job", "EditJob")["data"]["command"] == "yicloud job edit"
    )
    edited = call(
        "--json",
        "job",
        "edit",
        "fixture-job",
        "--project",
        "p",
        "--operation",
        "priority",
        "--priority",
        "5",
        "--dry-run",
    )["data"]["body"]
    assert edited == {
        "JobId": "fixture-job",
        "Project": "p",
        "Operation": "priority",
        "Priority": "5",
    }
    bucket = call(
        "--json",
        "oss",
        "create-bucket",
        "--project",
        "p",
        "--bucket",
        "fixture-bucket",
        "--capacity",
        "0",
        "--dry-run",
    )["data"]["body"]
    assert bucket == {"Project": "p", "Bucket": "fixture-bucket", "Capacity": 0}
    sku = call("--json", "api", "describe", "mc", "ListSKUs")["data"]
    assert sku["definitions"] == {}  # This request has no referenced types.
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
    installed = call("--json", "skill", "status", "--target", "codex", "--path", str(skill))["data"]
    assert installed["targets"][0]["state"] == "matching"
    assert installed["version"]  # Taken from package metadata, not a second version constant.
    result = call(
        "--json",
        "job",
        "logs",
        "fixture",
        "--project",
        "p",
        "--zone",
        "z",
        "--since",
        "15m",
        "--end",
        "1970-01-01T01:00:00.123456789Z",
        "--dry-run",
    )
    query = {p["name"]: p["value"] for p in result["data"]["query"]}
    assert int(query["Start"]) == 2700123456789
    # Fake local credentials exercise context plumbing, never network access.
    config = root / "config.json"
    config.write_text(
        json.dumps({"accounts": {"fixture": {}}, "connections": {}}), encoding="utf-8"
    )
    try:
        call(
            "--json",
            "context",
            "set",
            "lab",
            "--account",
            "fixture",
            "--project",
            "p",
            "--zone",
            "z",
        )
        call("--json", "context", "use", "lab")
        assert call("--json", "context", "show")["data"]["values"]["project"] == "p"
        assert (
            call("--json", "job", "stop", "fixture", "--dry-run")["data"]["body"]["Project"] == "p"
        )
        call("--json", "workspace", "connection", "set", "dev", "--ssh-command", "ssh user@host")
        assert len(call("--json", "workspace", "connection", "list")["data"]) == 1
        call("--json", "workspace", "connection", "remove", "dev")
        assert call("--json", "workspace", "connection", "list")["data"] == []
    finally:
        config.unlink()

    # Old skeletal examples and maintenance matrix must not reach execution agents.
    assert not list((skill / "assets").rglob("*.json"))
    assert not (skill / "references/support.md").exists()
    assert (skill / "references/jobs/run.md").is_file()
    assert (skill / "references/serving/scaling.md").is_file()
    preview = call(
        "--json", "job", "stop", "fixture", "--project", "p", "--zone", "z", "--dry-run"
    )["data"]
    assert preview["validation_scope"] == "local_pinned_sdk_request"
    # Validate the new attached-fields contract outside the source tree.
    extra = root / "workers.json"
    extra.write_text('{"WorkerGroups": []}', encoding="utf-8")
    request = call(
        "--json",
        "ray",
        "workers",
        "fixture",
        "--project",
        "p",
        "--zone",
        "z",
        "--extra-file",
        str(extra),
        "--dry-run",
    )["data"]
    assert request["body"]["WorkerGroups"] == []
    # Validate links after installation, rather than relying on a reference file count.
    for document in skill.rglob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if "://" not in target and not target.startswith("#"):
                assert (document.parent / target.split("#")[0]).exists(), (document, target)
    call("--json", "skill", "uninstall", "--target", "codex", "--path", str(skill))
    assert not skill.exists()
    assert not (root / "config.json").exists()
print("Independent wheel installation and packaged skill verified")
