"""Bounded, read-only diagnostics. Results are observations, never automatic repairs."""

import shutil
import shlex
import sys
from pathlib import Path
import subprocess
from importlib.metadata import version

from .config import config_path, read_state
from .errors import YicloudError
from .skill_install import status as skill_status


def check(identifier, status, summary, evidence=None, suggestion=None):
    result = dict(id=identifier, status=status, summary=summary, evidence=evidence or {})
    if suggestion:
        result["suggestion"] = suggestion
    return result


def local_checks():
    rows = [
        check(
            "cli.package",
            "pass",
            "Package loaded",
            {
                "version": version("yicloud-skill"),
                "python": sys.executable,
                "package_path": str(Path(__file__).parent),
                "command_on_path": shutil.which("yicloud"),
            },
        )
    ]
    try:
        read_state()
        rows.append(
            check(
                "config.read",
                "pass",
                "Configuration readable or not yet created",
                {"path": str(config_path()), "exists": config_path().exists()},
            )
        )
    except (YicloudError, OSError) as e:
        rows.append(check("config.read", "fail", str(e), suggestion="Check YICLOUD_CONFIG"))
    for tool in ("ssh", "scp", "rsync"):
        path = shutil.which(tool)
        rows.append(
            check(
                f"tool.{tool}",
                "pass" if path else "unknown",
                "Executable found" if path else "Executable not found",
                {"path": path, "optional": tool == "rsync"},
            )
        )
    for target in ("codex", "claude"):
        try:
            result = skill_status(target)["targets"][0]
            state = (
                "pass"
                if result["state"] == "matching"
                else ("skipped" if result["state"] == "missing" else "fail")
            )
            rows.append(check(f"skill.{target}", state, result["state"], result))
        except (YicloudError, OSError) as e:
            rows.append(check(f"skill.{target}", "fail", str(e)))
    return rows


def api_checks(client, project=None, zone=None):
    rows = []
    checks = [("api.zones", "mc", "ListZones", {}, "Available zones request succeeded")]
    if project:
        checks.append(
            ("api.project", "mc", "GetProject", {"Project": project}, "Project request succeeded")
        )
    for identifier, service, action, params, summary in checks:
        try:
            result = client.call(service, action, params)
            if identifier == "api.zones" and zone:
                data = result.data
                items = data.get("Items") if isinstance(data, dict) else None
                if not isinstance(items, list) or any(
                    not isinstance(item, dict) or not isinstance(item.get("ZoneId"), str)
                    for item in items
                ):
                    state, summary_zone = "unknown", "Unrecognized zone response"
                else:
                    found = any(item["ZoneId"] == zone for item in items)
                    state = "pass" if found else "fail"
                    summary_zone = (
                        "Selected zone is visible" if found else "Selected zone not visible"
                    )
                rows.append(check("api.zone", state, summary_zone, {"zone": zone}))
            # Only report evidence needed for diagnosis, never dump project inventories.
            rows.append(
                check(
                    identifier,
                    "pass",
                    summary,
                    {"request_id": result.request_id, "requested_zone": zone},
                )
            )
        except YicloudError as e:
            rows.append(
                check(
                    identifier,
                    "fail",
                    str(e),
                    e.as_dict(),
                    "Check credentials, API host and scope permissions",
                )
            )
    if not project:
        rows.append(check("api.project", "skipped", "No project selected"))
    rows.append(check("api.capacity", "skipped", "Capacity was not checked"))
    return rows


def remote_checks(connection, timeout=8):
    binary = shutil.which("ssh")
    if not binary:
        return [check("ssh.connect", "fail", "OpenSSH executable not found")]
    try:
        options = connection.options()
    except YicloudError as e:
        return [check("ssh.identity", "fail", str(e))]
    probes = [
        ("ssh.connect", ["uname", "-s"], "Remote command execution"),
        ("remote.disk", ["df", "-Pk", "."], "Disk containing the remote working directory"),
        (
            "remote.gpu",
            [
                "sh",
                "-c",
                "command -v nvidia-smi >/dev/null 2>&1 || exit 127; "
                "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader",
            ],
            "NVIDIA GPU information",
        ),
    ]
    rows = []
    for identifier, command, summary in probes:
        args = [
            binary,
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectionAttempts=1",
            "-o",
            f"ConnectTimeout={timeout}",
            *options,
            "--",
            connection.destination,
            shlex.join(command),
        ]
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            status = (
                "pass"
                if result.returncode == 0
                else ("unknown" if identifier == "remote.gpu" else "fail")
            )
            rows.append(
                check(
                    identifier,
                    status,
                    summary,
                    {
                        "exit_code": result.returncode,
                        "stdout": result.stdout[:2000],
                        "stderr": result.stderr[:2000],
                    },
                )
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            rows.append(
                check(
                    identifier,
                    "unknown",
                    "Probe did not complete",
                    {"reason": type(e).__name__, "timeout_seconds": timeout},
                )
            )
        if identifier == "ssh.connect" and rows[-1]["status"] != "pass":
            rows.extend(
                check(i, "skipped", "Connection probe did not succeed") for i, _, _ in probes[1:]
            )
            break
    return rows
