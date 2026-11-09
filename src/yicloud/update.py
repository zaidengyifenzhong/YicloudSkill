"""Stable release discovery and conservative, environment-bound update planning."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from importlib.metadata import distribution
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .errors import ConfigurationError, NetworkError
from .skill_install import existing_paths, install, status, sync_existing

PACKAGE = "yicloud-skill"
REPOSITORY = "https://github.com/zaidengyifenzhong/YicloudSkill"
STABLE = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")


def latest_release():
    """PyPI first; only a missing project falls back to official GitHub Releases."""
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=True) as client:
            response = client.get(f"https://pypi.org/pypi/{PACKAGE}/json")
            if response.status_code == 404:
                response = client.get(
                    "https://api.github.com/repos/zaidengyifenzhong/YicloudSkill/releases/latest",
                    headers={"Accept": "application/vnd.github+json"},
                )
                response.raise_for_status()
                release = response.json()
                tag = release["tag_name"]
                if (
                    release.get("draft")
                    or release.get("prerelease")
                    or not tag.startswith("v")
                    or not STABLE.fullmatch(tag[1:])
                ):
                    raise ValueError("Invalid stable release tag")
                return {
                    "version": tag[1:],
                    "channel": "github",
                    "spec": f"git+{REPOSITORY}.git@{tag}",
                }
            response.raise_for_status()
            releases = response.json()["releases"]
            compatible = []
            for number, artifacts in releases.items():
                if not STABLE.fullmatch(number):
                    continue
                if any(
                    not item.get("yanked", False)
                    and item.get("packagetype") in {"sdist", "bdist_wheel"}
                    and Version(".".join(map(str, sys.version_info[:3])))
                    in SpecifierSet(item.get("requires_python") or "")
                    for item in artifacts
                ):
                    compatible.append(Version(number))
            if not compatible:
                raise ValueError("No compatible stable distribution")
            number = str(max(compatible))
            return {"version": number, "channel": "pypi", "spec": f"{PACKAGE}=={number}"}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as e:
        # Do not echo response bodies, proxy credentials or unrelated environment values.
        raise NetworkError(
            "Cannot determine a compatible stable release from PyPI/GitHub; "
            "check network access and published releases, then retry. No changes made."
        ) from e


def command_text(command, windows=None):
    if windows if windows is not None else os.name == "nt":
        return "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in command)
    return shlex.join(command)


def query(command):
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=20, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def installation():
    dist = distribution(PACKAGE)
    prefix = Path(sys.prefix).absolute()
    python = Path(sys.executable).absolute()
    result = {
        "version": dist.version,
        "python": str(python),
        "prefix": str(prefix),
        "manager": "unsupported",
        "reason": None,
    }
    try:
        direct = json.loads(dist.read_text("direct_url.json") or "{}")
        if direct.get("dir_info", {}).get("editable"):
            result["reason"] = (
                "Editable checkout: update the checkout and reinstall with its development workflow."
            )
            parsed = urlsplit(direct.get("url", ""))
            if parsed.scheme == "file" and not parsed.netloc:
                checkout = unquote(parsed.path)
                if os.name == "nt" and re.match(r"^/[A-Za-z]:/", checkout):
                    checkout = checkout[1:]
                result["recovery_commands"] = [
                    ["git", "-C", checkout, "pull", "--ff-only"],
                    [str(python), "-m", "pip", "install", "--editable", checkout],
                ]
            return result
        url = direct.get("url")
        if url and not (
            url.rstrip("/") in {REPOSITORY, REPOSITORY + ".git"}
            and direct.get("vcs_info", {}).get("vcs") == "git"
        ):
            result["reason"] = (
                "Local/archive/custom source: use the original installer with the intended source."
            )
            return result
        if prefix == Path(sys.base_prefix).absolute() or not Path(
            dist.locate_file("")
        ).resolve().is_relative_to(prefix.resolve()):
            result["reason"] = (
                "System/user or external package installation: use its original package manager."
            )
            return result
        uv_receipt = prefix / "uv-receipt.toml"
        pipx_receipt = prefix / "pipx_metadata.json"
        if uv_receipt.is_file():
            manager = shutil.which("uv")
            if prefix.name == PACKAGE:
                result.update(
                    recovery_manager="uv",
                    executable=manager or "uv",
                    recovery_environment={"UV_TOOL_DIR": str(prefix.parent)},
                )
            root = query([manager, "tool", "dir"]) if manager else None
            if not root or (Path(root) / PACKAGE).resolve() != prefix.resolve():
                result["reason"] = (
                    "uv is missing or its active tool directory differs from this environment. Restore UV_TOOL_DIR and uv on PATH."
                )
                return result
            result.update(manager="uv", executable=manager)
        elif pipx_receipt.is_file():
            metadata = json.loads(pipx_receipt.read_text(encoding="utf-8"))
            name = metadata["main_package"]["package"]
            manager = shutil.which("pipx")
            if name == PACKAGE and prefix.name == PACKAGE and prefix.parent.name == "venvs":
                result.update(
                    recovery_manager="pipx",
                    executable=manager or "pipx",
                    recovery_environment={"PIPX_HOME": str(prefix.parent.parent)},
                )
            root = (
                query([manager, "environment", "--value", "PIPX_LOCAL_VENVS"]) if manager else None
            )
            if name != PACKAGE or not root or (Path(root) / PACKAGE).resolve() != prefix.resolve():
                result["reason"] = (
                    "pipx is missing, suffixed or its active environment differs. Use the original pipx environment/settings."
                )
                return result
            result.update(manager="pipx", executable=manager)
        elif (prefix / "pyvenv.cfg").is_file():
            if query([str(python), "-I", "-m", "pip", "--version"]) is None:
                result["reason"] = (
                    "This venv has no usable pip. Restore pip in this environment before updating."
                )
                result.update(
                    recovery_manager="venv",
                    recovery_commands=[[str(python), "-I", "-m", "ensurepip", "--upgrade"]],
                )
                return result
            result.update(manager="venv")
        else:
            result["reason"] = "Unrecognized environment; use the original installer."
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        result.update(
            manager="unsupported",
            reason="Invalid installation metadata; repair with the original installer.",
        )
    return result


def update_command(environment, release):
    spec = release["spec"]
    manager = environment["manager"]
    if manager == "uv":
        # Explicit source replaces legacy Git/main requirements; verified tool root above.
        return [
            environment["executable"],
            "tool",
            "install",
            "--force",
            "--upgrade",
            "--python",
            str(Path(sys._base_executable)),
            spec,
        ]
    if manager == "pipx":
        return [environment["executable"], "install", "--force", spec]
    if manager == "venv":
        return [environment["python"], "-I", "-m", "pip", "install", "--upgrade", spec]
    return None


def inspect_update():
    environment = installation()
    release = latest_release()
    try:
        available = Version(release["version"]) > Version(environment["version"])
    except InvalidVersion as e:
        raise ConfigurationError("Installed package has invalid version metadata") from e
    paths = existing_paths()
    command = update_command(environment, release)
    recovery = [command_text(c) for c in environment.get("recovery_commands", [])]
    manual = command
    if manual is None and environment.get("recovery_manager"):
        manual = update_command(dict(environment, manager=environment["recovery_manager"]), release)
    if manual:
        rendered = command_text(manual)
        for key, value in environment.get("recovery_environment", {}).items():
            if os.name == "nt":
                rendered = f"$env:{key}='" + value.replace("'", "''") + "'; " + rendered
            else:
                rendered = command_text(["env", f"{key}={value}"]) + " " + rendered
        recovery.append(rendered)
    return dict(
        current_version=environment["version"],
        latest_version=release["version"],
        update_available=available,
        channel=release["channel"],
        installation=environment,
        command=command,
        manual_command="\n".join(recovery) or None,
        skills=[status("codex", p)["targets"][0] for p in paths],
        remote_checked=True,
    )


def prepare_update(report):
    if not report["command"]:
        raise ConfigurationError(
            "Automatic update unavailable: " + report["installation"]["reason"],
            hints=[
                "No changes made. Restore the original manager first; do not install a second CLI.",
                report.get("manual_command")
                or "The original installer cannot be identified safely; no update command was guessed.",
            ],
        )
    paths = [Path(row["path"]) for row in report["skills"]]
    install("all", destinations=paths, preflight=True)
    # Exclusive lock follows the environment, not the current working directory.
    prefix = Path(report["installation"]["prefix"])
    lock = prefix.with_name(f".{prefix.name}-yicloud-update.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as e:
        raise ConfigurationError(
            f"Another update is active, or a previous update was interrupted: {lock}. Remove this lock only after checking no updater is running."
        ) from e
    except OSError as e:
        raise ConfigurationError(
            f"Cannot write update lock in this environment: {lock}; check ownership and permissions."
        ) from e
    os.close(fd)
    directory = None
    try:
        directory = Path(tempfile.mkdtemp(prefix="yicloud-update-"))
        worker = directory / "worker.py"
        shutil.copyfile(Path(__file__).with_name("_update_worker.py"), worker)
        plan = {
            "command": report["command"],
            "manual_command": report["manual_command"],
            "python": report["installation"]["python"],
            "prefix": report["installation"]["prefix"],
            "version": report["latest_version"],
            "paths": [str(p) for p in paths],
            "lock": str(lock),
            "json": False,
            "wait_pid": os.getpid() if os.name == "nt" else None,
        }
        (directory / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        return directory, plan
    except BaseException:
        lock.unlink(missing_ok=True)
        if directory:
            shutil.rmtree(directory)
        raise


def handoff(directory, plan, json_output=False):
    plan["json"] = json_output
    (directory / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    # The base interpreter and worker live outside the environment being modified.
    command = [
        sys._base_executable,
        "-I",
        str(directory / "worker.py"),
        str(directory / "plan.json"),
    ]
    try:
        if os.name == "nt":
            from ._update_worker import windows_launcher_pid

            plan["launcher_pid"] = windows_launcher_pid(os.getppid())
            (directory / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            log_path = directory / "update.log"
            with log_path.open("w", encoding="utf-8") as log:
                subprocess.Popen(
                    command,
                    stdout=log,
                    stderr=log,
                    stdin=subprocess.DEVNULL,
                    close_fds=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                )
            return {
                "state": "started",
                "completed": False,
                "log": str(log_path),
                "result": str(directory / "result.json"),
                "message": "Updater starts after this CLI exits. Inspect result.json for ok=true before treating the update as successful.",
            }
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(command[0], command)
    except OSError as e:
        Path(plan["lock"]).unlink(missing_ok=True)
        shutil.rmtree(directory)
        raise ConfigurationError("Cannot start independent updater; no package changes made") from e


def apply_update(report, json_output=False):
    if not report["update_available"]:
        report.update(state="current", skills=sync_existing([r["path"] for r in report["skills"]]))
        return report
    directory, plan = prepare_update(report)
    return handoff(directory, plan, json_output)
