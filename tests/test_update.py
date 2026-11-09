"""No user directories, real package managers or remote credentials are used here."""

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from click.testing import CliRunner

from yicloud import _update_worker as worker
from yicloud import update as updater
from yicloud.cli import main
from yicloud.errors import ConfigurationError, NetworkError
from yicloud.skill_install import (
    MARKER,
    existing_paths,
    install,
    remember_path,
    status,
    sync_existing,
)


@pytest.fixture(autouse=True)
def agent_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))


def response(data, code=200):
    return httpx.Response(code, json=data, request=httpx.Request("GET", "https://pypi.org/"))


def remote(monkeypatch, responses):
    iterator = iter(responses)
    monkeypatch.setattr(httpx.Client, "get", lambda *a, **kw: next(iterator))


def release(version="0.4.0"):
    return {"version": version, "channel": "pypi", "spec": f"yicloud-skill=={version}"}


def test_release_filters_prereleases_yanks_and_python(monkeypatch):
    remote(
        monkeypatch,
        [
            response(
                {
                    "releases": {
                        "0.4.0": [{"packagetype": "bdist_wheel", "requires_python": ">=3.10"}],
                        "0.5.0": [{"packagetype": "sdist", "yanked": True}],
                        "0.6.0rc1": [{"packagetype": "sdist"}],
                        "0.7.0": [{"packagetype": "sdist", "requires_python": ">=99"}],
                    }
                }
            )
        ],
    )
    assert updater.latest_release() == release()


def test_release_fallback_official_tag(monkeypatch):
    remote(monkeypatch, [response({}, 404), response({"tag_name": "v0.4.0"})])
    assert updater.latest_release()["spec"].endswith(".git@v0.4.0")


@pytest.mark.parametrize("tag", ["main", "v1.2.3rc1", "v1.2.3;echo x", "v01.2.3"])
def test_invalid_github_release_rejected(monkeypatch, tag):
    remote(monkeypatch, [response({}, 404), response({"tag_name": tag})])
    with pytest.raises(NetworkError):
        updater.latest_release()


@pytest.mark.parametrize("code", [403, 429, 500])
def test_network_failure_no_fallback_or_changes(monkeypatch, tmp_path, code):
    remote(monkeypatch, [response({}, code)])
    with pytest.raises(NetworkError, match="No changes made"):
        updater.latest_release()
    assert not (tmp_path / "codex").exists()


def test_offline_error_redacts_network_exception(monkeypatch):
    def fail(*a, **kw):
        raise httpx.ConnectError("https://user:secret@proxy")

    monkeypatch.setattr(httpx.Client, "get", fail)
    result = CliRunner().invoke(main, ["update", "--check"])
    assert result.exit_code == 1 and "secret" not in result.output
    assert "network" in result.output


@pytest.fixture
def environment(tmp_path, monkeypatch):
    prefix = tmp_path / "space venv"
    prefix.mkdir()
    (prefix / "pyvenv.cfg").touch()
    monkeypatch.setattr(updater.sys, "prefix", str(prefix))
    monkeypatch.setattr(updater.sys, "base_prefix", str(tmp_path / "base"))
    monkeypatch.setattr(updater.sys, "executable", str(prefix / "bin/python"))
    direct = {}
    dist = SimpleNamespace(
        version="0.3.1",
        read_text=lambda _: json.dumps(direct),
        locate_file=lambda _: prefix / "lib",
    )
    monkeypatch.setattr(updater, "distribution", lambda _: dist)
    monkeypatch.setattr(updater, "query", lambda _: "pip")
    return prefix, direct


def test_legacy_venv_without_uv(environment, monkeypatch):
    monkeypatch.setattr(updater.shutil, "which", lambda _: None)
    env = updater.installation()
    assert env["manager"] == "venv"
    command = updater.update_command(env, release())
    assert command == [
        env["python"],
        "-I",
        "-m",
        "pip",
        "install",
        "--upgrade",
        "yicloud-skill==0.4.0",
    ]


@pytest.mark.parametrize("manager", ["uv", "pipx"])
def test_manager_detection_and_exact_environment(environment, monkeypatch, manager):
    prefix, _ = environment
    if manager == "uv":
        (prefix / "uv-receipt.toml").touch()
    else:
        (prefix / "pipx_metadata.json").write_text(
            json.dumps({"main_package": {"package": "yicloud-skill"}})
        )
    real = prefix.with_name("yicloud-skill")
    prefix.rename(real)
    monkeypatch.setattr(updater.sys, "prefix", str(real))
    monkeypatch.setattr(
        updater,
        "distribution",
        lambda _: SimpleNamespace(
            version="0.3.1", read_text=lambda _: None, locate_file=lambda _: real / "lib"
        ),
    )
    monkeypatch.setattr(updater.shutil, "which", lambda _: "/tools/" + manager)
    monkeypatch.setattr(updater, "query", lambda _: str(real.parent))
    env = updater.installation()
    assert env["manager"] == manager
    assert updater.update_command(env, release())[0] == "/tools/" + manager
    monkeypatch.setattr(updater, "query", lambda _: "/different/root")
    assert updater.installation()["manager"] == "unsupported"
    monkeypatch.setattr(updater.shutil, "which", lambda _: None)
    assert updater.installation()["manager"] == "unsupported"


@pytest.mark.parametrize(
    "direct",
    [
        {"dir_info": {"editable": True}, "url": "file:///checkout"},
        {"url": "file:///custom.whl"},
        {"url": "https://example.com/custom.git", "vcs_info": {"vcs": "git"}},
    ],
)
def test_custom_or_editable_not_guessed(environment, direct):
    environment[1].update(direct)
    assert updater.installation()["manager"] == "unsupported"


def test_official_git_source_supported(environment):
    environment[1].update(url=updater.REPOSITORY + ".git", vcs_info={"vcs": "git"})
    assert updater.installation()["manager"] == "venv"


def test_system_environment_not_modified(environment, monkeypatch):
    monkeypatch.setattr(updater.sys, "base_prefix", updater.sys.prefix)
    assert updater.installation()["manager"] == "unsupported"


def test_no_pip_or_bad_metadata(environment, monkeypatch):
    monkeypatch.setattr(updater, "query", lambda _: None)
    assert updater.installation()["manager"] == "unsupported"
    (environment[0] / "pipx_metadata.json").write_text("{")
    assert updater.installation()["manager"] == "unsupported"


def report_fixture(environment, monkeypatch, latest="0.4.0"):
    monkeypatch.setattr(updater, "latest_release", lambda: release(latest))
    return updater.inspect_update()


def test_check_is_read_only_and_detects_update(environment, monkeypatch, tmp_path):
    report = report_fixture(environment, monkeypatch)
    assert report["update_available"] and report["current_version"] == "0.3.1"
    result = CliRunner().invoke(main, ["--json", "update", "--check"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["latest_version"] == "0.4.0"
    assert not (tmp_path / "codex").exists()
    assert not (environment[0] / ".yicloud-update.lock").exists()


@pytest.mark.parametrize("latest", ["0.3.1", "0.2.0"])
def test_same_or_newer_version_no_reinstall(environment, monkeypatch, latest):
    report = report_fixture(environment, monkeypatch, latest)
    monkeypatch.setattr(updater, "handoff", lambda *a: pytest.fail("unnecessary reinstall"))
    assert updater.apply_update(report)["state"] == "current"


def test_same_version_repairs_existing_skill_only(environment, monkeypatch, tmp_path):
    dest = tmp_path / "custom"
    install("codex", dest)
    remember_path(dest)
    (dest / "SKILL.md").unlink()
    report = report_fixture(environment, monkeypatch, "0.3.1")
    assert updater.apply_update(report)["skills"][0]["state"] == "matching"
    assert not (tmp_path / ".claude").exists()


@pytest.mark.parametrize("conflict", ["edits", "unowned"])
def test_preflight_blocks_before_package_update(environment, monkeypatch, tmp_path, conflict):
    dest = tmp_path / "custom"
    install("codex", dest)
    remember_path(dest)
    if conflict == "edits":
        (dest / "SKILL.md").write_text("my edits")
    else:
        (dest / MARKER).unlink()
    report = report_fixture(environment, monkeypatch)
    with pytest.raises(ConfigurationError):
        updater.apply_update(report)
    assert not (environment[0] / ".yicloud-update.lock").exists()


def test_prepare_lock_and_handoff_uses_independent_python(environment, monkeypatch):
    report = report_fixture(environment, monkeypatch)
    directory, plan = updater.prepare_update(report)
    assert (directory / "worker.py").is_file()
    with pytest.raises(ConfigurationError, match="Another update"):
        updater.prepare_update(report)

    def fail(binary, args):
        assert binary == updater.sys._base_executable
        assert args[1] == "-I"
        assert str(directory) in args[2]
        raise OSError("exec failure")

    monkeypatch.setattr(updater.os, "execv", fail)
    # POSIX handoff failure must release the lock and temp files.
    if os.name == "nt":
        Path(plan["lock"]).unlink()
        return
    with pytest.raises(ConfigurationError, match="no package changes"):
        updater.handoff(directory, plan)
    assert not Path(plan["lock"]).exists() and not directory.exists()


def test_unsupported_no_package_mutation(environment, monkeypatch):
    environment[1].update(dir_info={"editable": True})
    report = report_fixture(environment, monkeypatch)
    with pytest.raises(ConfigurationError, match="Editable"):
        updater.apply_update(report)


def test_repeat_install_keeps_mtime_and_registry_sync(tmp_path):
    dest = tmp_path / "custom space"
    install("codex", dest)
    remember_path(dest)
    stamp = (dest / "SKILL.md").stat().st_mtime_ns
    marker_stamp = (dest / MARKER).stat().st_mtime_ns
    install("codex", dest)
    assert (dest / "SKILL.md").stat().st_mtime_ns == stamp
    assert (dest / MARKER).stat().st_mtime_ns == marker_stamp
    assert existing_paths() == [dest]
    assert sync_existing()[0]["state"] == "matching"
    remember_path(dest, uninstall=True)


def test_sync_detects_edits_after_package_install(tmp_path):
    dest = tmp_path / "custom"
    install("codex", dest)
    (dest / "SKILL.md").write_text("user content")
    with pytest.raises(ConfigurationError, match="local edits"):
        sync_existing([dest])
    assert (dest / "SKILL.md").read_text() == "user content"


def test_cross_platform_commands_are_argument_lists():
    command = [r"C:\Users\name space\python.exe", "-m", "pip", "install", "x;echo evil"]
    assert updater.command_text(command, windows=True).startswith("& 'C:")
    assert "'x;echo evil'" in updater.command_text(command, windows=False)


@pytest.fixture
def worker_plan(tmp_path):
    path = tmp_path / "plan.json"
    lock = tmp_path / "lock"
    lock.touch()
    plan = dict(
        command=["installer", "argument with spaces"],
        python="python",
        prefix="env",
        version="0.4.0",
        paths=[],
        lock=str(lock),
        json=True,
        wait_pid=None,
    )
    path.write_text(json.dumps(plan))
    return path, plan


def test_worker_success_verifies_before_reporting(worker_plan, monkeypatch, capsys):
    path, plan = worker_plan
    calls = []

    def run(args, **kw):
        calls.append(args)
        assert not kw.get("shell")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"version": "0.4.0", "skills": []}))

    monkeypatch.setattr(worker.subprocess, "run", run)
    monkeypatch.setattr(worker.shutil, "rmtree", lambda _: None)
    assert worker.main(path) == 0
    assert len(calls) == 3
    assert json.loads(capsys.readouterr().out)["ok"]
    assert not Path(plan["lock"]).exists()


@pytest.mark.parametrize("stage", [0, 1, 2])
def test_worker_failures_never_report_success(worker_plan, monkeypatch, capsys, stage):
    path, plan = worker_plan
    count = 0

    def run(*args, **kw):
        nonlocal count
        code = 1 if count == stage else 0
        count += 1
        return SimpleNamespace(returncode=code, stdout="{}", stderr="verification conflict")

    monkeypatch.setattr(worker.subprocess, "run", run)
    assert worker.main(path) == 1
    result = json.loads(capsys.readouterr().err)
    assert not result["ok"] and "success" not in result["error"]["message"]
    assert not Path(plan["lock"]).exists()
    assert not json.loads((path.parent / "result.json").read_text())["ok"]


def test_worker_timeout_is_failure(worker_plan, monkeypatch, capsys):
    def fail(*a, **kw):
        raise subprocess.TimeoutExpired("installer", 1800)

    monkeypatch.setattr(worker.subprocess, "run", fail)
    assert worker.main(worker_plan[0]) == 1
    assert not json.loads(capsys.readouterr().err)["ok"]


def test_missing_skill_status_is_local_only(tmp_path):
    assert status("codex")["targets"][0]["state"] == "missing"


def test_invalid_registry_fails_before_installing_skill(tmp_path):
    from yicloud.skill_install import registry_path

    registry = registry_path()
    registry.write_text("{")
    dest = tmp_path / "not-created"
    result = CliRunner().invoke(
        main, ["skill", "install", "--target", "codex", "--path", str(dest)]
    )
    assert result.exit_code == 1
    assert not dest.exists()


def test_registry_never_occupies_account_config_filename(tmp_path, monkeypatch):
    from yicloud.config import config_path, read_state
    from yicloud.skill_install import registry_path

    monkeypatch.setenv("YICLOUD_CONFIG", str(tmp_path / "skill-installs.json"))
    dest = tmp_path / "custom"
    result = CliRunner().invoke(
        main, ["skill", "install", "--target", "codex", "--path", str(dest)]
    )
    assert result.exit_code == 0
    assert registry_path() != config_path()
    assert not config_path().exists()
    assert read_state() == {"accounts": {}, "connections": {}}


def test_editable_manual_commands_use_observed_checkout(environment, monkeypatch):
    environment[1].update(url="file:///checkout%20space", dir_info={"editable": True})
    report = report_fixture(environment, monkeypatch)
    assert report["command"] is None
    assert "git -C" in report["manual_command"]
    assert "checkout space" in report["manual_command"]
    assert "--editable" in report["manual_command"]


def test_missing_pip_reports_exact_repair(environment, monkeypatch):
    monkeypatch.setattr(updater, "query", lambda _: None)
    report = report_fixture(environment, monkeypatch)
    assert "ensurepip" in report["manual_command"]
    assert "pip install --upgrade" in report["manual_command"]
    assert report["command"] is None


def test_update_lock_permission_error_is_clear(environment, monkeypatch):
    report = report_fixture(environment, monkeypatch)

    def deny(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(updater.os, "open", deny)
    with pytest.raises(ConfigurationError, match="permissions"):
        updater.prepare_update(report)


def test_release_workflow_does_not_interpolate_tags_into_shell():
    import yaml

    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/release.yml").read_text()
    )
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            assert "${{ github.ref_name }}" not in step.get("run", "")


@pytest.mark.parametrize("suffix", ["", ".git", ".git/"])
def test_official_github_url_variants(environment, suffix):
    environment[1].update(url=updater.REPOSITORY + suffix, vcs_info={"vcs": "git"})
    assert updater.installation()["manager"] == "venv"


@pytest.mark.parametrize("metadata", ["null", "[]", '{"url": true}', '{"dir_info": null}'])
def test_malformed_install_metadata_returns_explanation(environment, monkeypatch, metadata):
    prefix = environment[0]
    monkeypatch.setattr(
        updater,
        "distribution",
        lambda _: SimpleNamespace(
            version="0.3.1", read_text=lambda _: metadata, locate_file=lambda _: prefix / "lib"
        ),
    )
    result = updater.installation()
    assert result["manager"] == "unsupported"
    assert "Invalid installation metadata" in result["reason"]
