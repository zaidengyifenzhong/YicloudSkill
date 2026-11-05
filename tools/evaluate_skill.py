"""Repeatable offline CLI contracts and skill context measurements.

Run with the project's development interpreter. No platform credentials or network
access are used; behavioral skill-selection scenarios are recorded separately.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "src/yicloud/skill"
NETWORK_MARKER = "YICLOUD_EVAL_NETWORK_BLOCKED"
GUARD = f"""
import sys
def deny_network(event, args):
    if event.startswith('socket.'):
        print({NETWORK_MARKER!r}, file=sys.stderr)
        raise RuntimeError('Offline evaluation forbids socket operations')
sys.addaudithook(deny_network)
"""
CLI = (
    GUARD
    + f"""
import runpy
sys.path.insert(0, {str(ROOT / "src")!r})
runpy.run_module('yicloud', run_name='__main__')
"""
)


def invoke(code, args, env, stdin=None):
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=ROOT,
        timeout=15,
        check=False,
    )
    return result, round(time.perf_counter() - started, 4)


def cli_cases(env):
    # Discover current commands rather than pinning a count that hides additions.
    sys.path.insert(0, str(ROOT / "src"))
    from yicloud.cli import main

    paths = [[], *[[name] for name in sorted(main.commands)]]
    for name in ("workspace", "job", "ray", "serving", "skill", "api", "context"):
        paths.extend([name, sub] for sub in sorted(main.commands[name].commands))
    cases = []
    for path in paths:
        result, elapsed = invoke(CLI, [*path, "--help"], env)
        passed = (
            result.returncode == 0
            and "Usage:" in result.stdout
            and NETWORK_MARKER not in result.stderr
        )
        case = {"id": "help:" + "/".join(path), "passed": passed, "seconds": elapsed}
        if not passed:
            case["diagnostic"] = (result.stdout + result.stderr)[:3000]
        cases.append(case)

    contracts = [
        ("context-conflict", ["--context", "x", "--no-context", "workspace", "list"], None),
        ("unknown-command", ["not-a-command"], None),
        ("unknown-operation", ["api", "describe", "invalid", "UnknownAction"], None),
        ("negative-timeout", ["workspace", "wait", "x", "--timeout", "-1"], None),
        ("zero-interval", ["workspace", "wait", "x", "--interval", "0"], None),
        ("missing-scope", ["workspace", "status", "x"], None),
        ("array-request", ["job", "create", "--file", "-", "--dry-run"], "[]"),
        (
            "invalid-request",
            ["job", "create", "--file", "-", "--dry-run"],
            '{"not-valid":true}',
        ),
    ]
    for workload in ("job", "workspace"):
        contracts.append(
            (
                workload + "-dry-run",
                [
                    workload,
                    "create",
                    "--file",
                    str(ROOT / f"tests/fixtures/requests/{workload}.json"),
                    "--dry-run",
                ],
                None,
            )
        )
    for name, args, stdin in contracts:
        result, elapsed = invoke(CLI, ["--json", *args], env, stdin)
        success = name.endswith("-dry-run")
        try:
            # The fixed envelope is a single document on stdout (success) or stderr.
            payload = json.loads(result.stdout if success else result.stderr)
            passed = (
                result.returncode == (0 if success else 1)
                and payload.get("ok") is success
                and not (result.stderr if success else result.stdout)
                and (success or payload.get("error", {}).get("kind") == "input")
                and NETWORK_MARKER not in result.stderr
            )
        except (ValueError, AttributeError):
            passed = False
        case = {"id": "json:" + name, "passed": passed, "seconds": elapsed}
        if not passed:
            case["diagnostic"] = (result.stdout + result.stderr)[:3000]
        cases.append(case)
    return cases


def measure_skill():
    markdown = sorted(SKILL.rglob("*.md"))
    entry = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    scenarios = {
        "ssh": "references/workspace/connect.md",
        "job_run": "references/jobs/run.md",
        "serving_create": "references/serving/create.md",
        "auth": "references/access.md",
    }
    links, broken = 0, []
    for path in markdown:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            links += 1
            if not (path.parent / unquote(parsed.path)).exists():
                broken.append({"file": str(path.relative_to(SKILL)), "target": target})
    return {
        "markdown_files": len(markdown),
        "entry_bytes": len(entry.encode("utf-8")),
        "entry_characters": len(entry),
        "all_markdown_bytes": sum(path.stat().st_size for path in markdown),
        "scenario_bytes": {
            name: len(entry.encode("utf-8")) + (SKILL / ref).stat().st_size
            for name, ref in scenarios.items()
        },
        "local_links": links,
        "broken_links": broken,
    }


def main():
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="yicloud-offline-eval-") as directory:
            env = {k: v for k, v in os.environ.items() if not k.startswith("YICLOUD_")}
            env["YICLOUD_CONFIG"] = str(Path(directory) / "config.json")
            probe, _ = invoke(GUARD + "\nimport socket\nsocket.socket()\n", [], env)
            guard_passed = probe.returncode != 0 and NETWORK_MARKER in probe.stderr
            if not guard_passed:
                raise RuntimeError("Offline network guard self-check failed")
            cases = cli_cases(env)
            context = measure_skill()
        report = {
            "schema_version": 1,
            "evaluation": "offline-contracts",
            "network_guard_passed": guard_passed,
            "help": {
                "total": sum(c["id"].startswith("help:") for c in cases),
                "passed": sum(c["id"].startswith("help:") and c["passed"] for c in cases),
            },
            "json_contracts": {
                "total": sum(c["id"].startswith("json:") for c in cases),
                "passed": sum(c["id"].startswith("json:") and c["passed"] for c in cases),
            },
            "context": context,
            "cases": cases,
            "seconds": round(time.perf_counter() - started, 4),
            "limitations": [
                "Contracts and reference availability do not measure agent trigger accuracy.",
                "Context sizes are UTF-8 bytes and characters, not tokens.",
                "No live platform, SSH, workload, or artifact verification is performed.",
            ],
        }
        report["passed"] = all(c["passed"] for c in cases) and not context["broken_links"]
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, ImportError) as error:
        report = {"schema_version": 1, "passed": False, "error": type(error).__name__}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
