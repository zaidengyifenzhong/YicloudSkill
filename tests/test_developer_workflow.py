"""Developer-facing contracts, isolated from user accounts and remote machines."""

import json
import subprocess
from types import SimpleNamespace

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.client import YicloudClient
from yicloud.config import read_state, write_state
from yicloud.context import save_context, use_context
from yicloud.diagnostics import api_checks, remote_checks
from yicloud.errors import InputError, RemoteFailed, UnknownState, WaitTimeout
from yicloud.output import redact, secret_values
from yicloud.skill_install import install, status
from yicloud.ssh import Connection, load, run, save
from yicloud.time_input import duration_ns, timestamp_ns
from yicloud.workflows import wait


def invoke(*args):
    return CliRunner().invoke(main, ["--json", *args])


@pytest.fixture
def named_context():
    write_state(
        {
            "accounts": {"a": {"public_key": "fixture", "secret_key": "secret"}, "b": {}},
            "current": "b",
            "connections": {},
        }
    )
    save_context("lab", "a", "project-a", "zone-a")
    use_context("lab")


@pytest.mark.parametrize("login", [False, True])
def test_shell_selection_and_request_file_are_explicit(login, tmp_path):
    args = [
        "job",
        "create",
        "--name",
        "n",
        "--project",
        "p",
        "--zone",
        "z",
        "--image",
        "image",
        "--sku",
        "sku",
        "--sku-scope",
        "public",
        "--command",
        "printf 'hello world'",
        "--dry-run",
    ]
    if login:
        args += ["--login-shell"]
    result = invoke(*args)
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)["data"]["body"]
    assert body["TaskSpecs"]["t0"]["Command"] == [
        "sh",
        "-lc" if login else "-c",
        "printf 'hello world'",
    ]
    body["TaskSpecs"]["t0"]["Command"] = ["python", "-c", "print('你好')"]
    path = tmp_path / "request.json"
    path.write_text(json.dumps(body))
    result = invoke("job", "create", "--file", str(path), "--dry-run")
    assert json.loads(result.output)["data"]["body"] == body
    assert invoke("job", "create", "--file", str(path), "--login-shell", "--dry-run").exit_code == 1


def test_metrics_survive_credential_redaction():
    value = {
        "num_tokens": 42,
        "token_count": 8,
        "tokenizer": "model",
        "max_new_tokens": 32,
        "DaemonJupyterToken": "private",
        "AuthToken": "auth",
        "API_KEY": "key",
        "Env": {"HF_TOKEN": "hf"},
        "query": [{"name": "Token", "value": "query-secret"}],
    }
    hidden = redact(value)
    for key in ("num_tokens", "token_count", "tokenizer", "max_new_tokens"):
        assert hidden[key] == value[key]
    assert hidden["DaemonJupyterToken"] == "[REDACTED]"
    assert hidden["Env"]["HF_TOKEN"] == "[REDACTED]"
    assert "private" not in json.dumps(hidden)
    assert "model" not in secret_values(value)
    assert "query-secret" not in json.dumps(hidden)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0", 0),
        ("-1", -1),
        ("1970-01-01T00:00:00Z", 0),
        ("1970-01-01T08:00:00.123456789+08:00", 123456789),
        ("1969-12-31T23:59:59.999999999Z", -1),
        ("1970-01-01T00:00:00.1-01:00", 3600100000000),
    ],
)
def test_exact_timestamp_conversion(value, expected):
    assert timestamp_ns(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "today",
        "2026-10-19T12:00:00",
        "2026-13-01T00:00:00Z",
        "2026-01-01T00:00:00+00:99",
        "1.2",
        "NaN",
        "1970-01-01T00:00:00.1234567890Z",
    ],
)
def test_invalid_timestamps(value):
    with pytest.raises(InputError):
        timestamp_ns(value)


@pytest.mark.parametrize("value", ["0m", "-1m", "1.5h", "1w", "1m2s"])
def test_invalid_duration(value):
    with pytest.raises(InputError):
        duration_ns(value)


@pytest.mark.parametrize("kind,key", [("job", "Start"), ("ray", "StartTime"), ("serving", "Start")])
def test_relative_log_window_has_exact_platform_units(kind, key):
    result = invoke(
        kind,
        "logs",
        "id",
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
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    params = dict((r["name"], r["value"]) for r in data["query"]) if data["query"] else data["body"]
    assert int(params[key]) == 2700123456789
    invalid = invoke(
        kind,
        "logs",
        "id",
        "--project",
        "p",
        "--zone",
        "z",
        "--since",
        "1m",
        "--start",
        "0",
        "--dry-run",
    )
    assert invalid.exit_code == 1


@pytest.mark.parametrize(
    "phase,expected",
    [("Running", WaitTimeout), ("Failed", RemoteFailed), ("FuturePhase", UnknownState)],
)
def test_wait_errors_preserve_last_observation(account, phase, expected):
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, headers={"X-OGW-Request-Id": "req"}, json={"Code": 0, "Data": {"Phase": phase}}
        )
    )
    with YicloudClient(account, transport=transport) as client:
        with pytest.raises(expected) as caught:
            wait(client, "job", {"Project": "p", "JobId": "j"}, timeout=0)
    error = caught.value.as_dict()
    assert error["last_status"] == phase.lower()
    assert error["observed_at"] and error["request_id"] == "req"
    assert error["outcome_unknown"] is False


def test_unlimited_wait_and_option_conflict(account, monkeypatch):
    phases = iter(["Pending", "Succeeded"])
    monkeypatch.setattr(
        "yicloud.commands.workloads.client_for",
        lambda _: YicloudClient(
            account,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"Code": 0, "Data": {"Phase": next(phases)}})
            ),
        ),
    )
    result = invoke(
        "job", "wait", "j", "--project", "p", "--zone", "z", "--no-timeout", "--interval", "0.1"
    )
    assert result.exit_code == 0, result.output
    result = invoke(
        "job", "wait", "j", "--project", "p", "--zone", "z", "--no-timeout", "--timeout", "0"
    )
    assert result.exit_code == 1 and "mutually exclusive" in result.output


def test_context_lifecycle_and_credential_environment(named_context, monkeypatch):
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", "env-secret")
    result = invoke("context", "show")
    data = json.loads(result.output)["data"]
    assert data["values"]["account"] == "a" and data["sources"]["account"] == "context"
    assert data["auth_source"] == "environment" and "env-secret" not in result.output
    result = invoke("--account", "b", "context", "show")
    assert json.loads(result.output)["data"]["sources"]["account"] == "argument"
    result = invoke("--no-context", "context", "show")
    assert json.loads(result.output)["data"]["values"]["account"] == "b"
    assert invoke("context", "remove", "lab").exit_code == 0
    assert "current_context" not in read_state() and read_state()["current"] == "b"


def test_context_scope_override_and_files_untouched(named_context, monkeypatch, tmp_path, account):
    calls = []

    def handler(req):
        calls.append(dict(req.url.params))
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": []}})

    monkeypatch.setattr(
        "yicloud.commands.discovery.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    assert invoke("workspace", "list", "--project", "override").exit_code == 0
    assert calls[-1]["Project"] == "override" and calls[-1]["ZoneId"] == "zone-a"
    assert invoke("workspace", "list", "--set", 'Project="set-project"').exit_code == 0
    assert calls[-1]["Project"] == "set-project"
    assert invoke("project", "list").exit_code == 0
    assert "Project" not in calls[-1] and "ZoneId" not in calls[-1]
    path = tmp_path / "list.json"
    path.write_text('{"Project":"file-project","ZoneId":"file-zone"}')
    assert invoke("workspace", "list", "--file", str(path)).exit_code == 0
    assert calls[-1]["Project"] == "file-project" and calls[-1]["ZoneId"] == "file-zone"
    result = invoke("job", "stop", "j", "--dry-run")
    assert json.loads(result.output)["data"]["body"] == {
        "JobId": "j",
        "Project": "project-a",
        "ZoneId": "zone-a",
    }
    result = invoke("api", "call", "job", "StopJob", "--dry-run")
    assert result.exit_code == 1  # Generic API fields never inherited.


def test_context_create_and_missing_scope(named_context):
    result = invoke(
        "workspace",
        "create",
        "--name",
        "dev",
        "--image",
        "image",
        "--sku",
        "s",
        "--sku-scope",
        "public",
        "--dry-run",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["body"]["Project"] == "project-a"
    assert invoke("--no-context", "workspace", "status", "w", "--dry-run").exit_code == 1
    assert invoke("--context", "missing", "context", "show").exit_code == 1
    assert invoke("--context", "lab", "--no-context", "context", "show").exit_code == 1


def test_local_connection_management_respects_scope(named_context):
    save("a", "workspace", "project-a", "zone-a", "dev", Connection("host"))
    save("a", "workspace", "other", "zone-a", "dev", Connection("other"))
    result = invoke("workspace", "connection", "list")
    assert len(json.loads(result.output)["data"]) == 1
    assert invoke("workspace", "connection", "show", "dev").exit_code == 0
    assert invoke("workspace", "connection", "remove", "dev").exit_code == 0
    assert load("a", "workspace", "other", "zone-a", "dev").host == "other"
    assert read_state()["accounts"]["a"]["secret_key"] == "secret"


def test_recursive_copy_preserves_native_arguments(monkeypatch, tmp_path):
    captured = []
    monkeypatch.setattr("yicloud.ssh.shutil.which", lambda _: "/bin/scp")
    monkeypatch.setattr(
        "yicloud.ssh.subprocess.run",
        lambda args, **kwargs: captured.append((args, kwargs)) or SimpleNamespace(returncode=37),
    )
    assert (
        run(
            Connection("host", port=2202),
            scp_paths=[str(tmp_path / "中文 a"), "host:/tmp/b"],
            recursive=True,
        )
        == 37
    )
    args, options = captured[0]
    assert args[:3] == ["/bin/scp", "-P", "2202"] and "-r" in args
    assert options["shell"] is False and args[-2] == str(tmp_path / "中文 a")


def test_skill_status_detects_content_not_just_version(tmp_path):
    dest = tmp_path / "skill"
    assert status("codex", dest)["targets"][0]["state"] == "missing"
    install("codex", dest)
    assert status("codex", dest)["targets"][0]["state"] == "matching"
    (dest / "SKILL.md").write_text("local edits")
    (dest / "references/jobs/run.md").unlink()
    row = status("codex", dest)["targets"][0]
    assert row["state"] == "different" and row["local_edits"] == ["SKILL.md"]
    assert row["missing"] == ["references/jobs/run.md"]
    assert (dest / "SKILL.md").read_text() == "local edits"


def test_skill_status_unmanaged_path_is_not_modified(tmp_path):
    (tmp_path / "user-file").write_text("keep")
    result = invoke("skill", "status", "--target", "codex", "--path", str(tmp_path))
    assert json.loads(result.output)["data"]["targets"][0]["state"] == "conflict"
    assert (tmp_path / "user-file").read_text() == "keep"


def test_api_doctor_checks_zone_and_does_not_return_inventory(account):
    def handler(req):
        assert req.method == "GET"
        if req.url.path.endswith("ListZones"):
            return httpx.Response(200, json={"Code": 0, "Data": {"Items": [{"ZoneId": "z"}]}})
        return httpx.Response(200, json={"Code": 0, "Data": {"PrivateDetail": "not-for-report"}})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        rows = api_checks(client, "p", "wrong-zone")
    assert next(r for r in rows if r["id"] == "api.zone")["status"] == "fail"
    assert "not-for-report" not in json.dumps(rows)
    assert rows[-1]["status"] == "skipped"


def test_remote_doctor_is_bounded_and_gpu_absence_is_unknown(monkeypatch):
    calls = []
    monkeypatch.setattr("yicloud.diagnostics.shutil.which", lambda _: "/bin/ssh")

    def capture(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=127 if len(calls) == 3 else 0, stdout="output", stderr="")

    monkeypatch.setattr("yicloud.diagnostics.subprocess.run", capture)
    rows = remote_checks(Connection("host"), 3)
    assert [r["status"] for r in rows] == ["pass", "pass", "unknown"]
    assert all(k["timeout"] == 3 for _, k in calls)
    assert all("BatchMode=yes" in a and "StrictHostKeyChecking=no" not in a for a, _ in calls)
    assert len(calls) == 3


def test_remote_timeout_skips_dependent_checks(monkeypatch):
    monkeypatch.setattr("yicloud.diagnostics.shutil.which", lambda _: "/bin/ssh")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("ssh", 1)

    monkeypatch.setattr("yicloud.diagnostics.subprocess.run", timeout)
    assert [r["status"] for r in remote_checks(Connection("host"), 1)] == [
        "unknown",
        "skipped",
        "skipped",
    ]


def test_explicit_null_scope_is_not_replaced_by_context(named_context, monkeypatch, account):
    def forbidden(_):
        pytest.fail("Invalid explicit Project must fail before transport")

    monkeypatch.setattr(
        "yicloud.commands.discovery.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(forbidden)),
    )
    result = invoke("job", "list", "--set", "Project=null")
    assert result.exit_code == 1 and "required" in result.output


def test_named_context_does_not_change_create_request_file(named_context, tmp_path):
    from pathlib import Path

    body = json.loads(Path("tests/fixtures/requests/job.json").read_text())
    path = tmp_path / "job.json"
    path.write_text(json.dumps(body))
    result = invoke("job", "create", "--file", str(path), "--dry-run")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["body"] == body


def test_project_directory_cannot_select_context(tmp_path, monkeypatch):
    (tmp_path / ".yicloud.json").write_text('{"account":"unexpected","project":"unexpected"}')
    monkeypatch.chdir(tmp_path)
    result = invoke("context", "show")
    data = json.loads(result.output)["data"]
    assert data["values"]["account"] == "environment" and "project" not in data["values"]


def test_local_doctor_never_uses_network_and_reports_failures(monkeypatch, tmp_path):
    import yicloud.diagnostics as diagnostic

    monkeypatch.setattr(
        diagnostic,
        "skill_status",
        lambda target: {"targets": [{"state": "missing", "path": str(tmp_path / target)}]},
    )
    monkeypatch.setattr(diagnostic.shutil, "which", lambda name: None)
    result = invoke("doctor", "local")
    assert result.exit_code == 0
    checks = json.loads(result.output)["data"]["checks"]
    assert next(r for r in checks if r["id"] == "tool.ssh")["status"] == "unknown"
    assert next(r for r in checks if r["id"] == "skill.codex")["status"] == "skipped"
    monkeypatch.setattr(
        diagnostic, "local_checks", lambda: [diagnostic.check("config.read", "fail", "bad")]
    )
    result = invoke("doctor", "local")
    assert (
        result.exit_code == 1 and json.loads(result.output)["data"]["checks"][0]["status"] == "fail"
    )


def test_remote_doctor_cli_does_not_replace_failure_with_success(monkeypatch):
    save("environment", "workspace", "p", "z", "dev", Connection("host"))
    monkeypatch.setattr(
        "yicloud.diagnostics.remote_checks",
        lambda *args: [
            {"id": "ssh.connect", "status": "fail", "summary": "Denied", "evidence": {}}
        ],
    )
    result = invoke("workspace", "doctor", "dev", "--project", "p", "--zone", "z")
    assert result.exit_code == 1 and json.loads(result.output)["data"]["checks"]


def test_invalid_saved_connection_reports_configuration_error():
    from yicloud.ssh import key

    write_state(
        {
            "accounts": {},
            "connections": {key("environment", "workspace", "p", "z", "dev"): {"host": None}},
        }
    )
    result = invoke("workspace", "connection", "show", "dev", "--project", "p", "--zone", "z")
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["kind"] == "configuration"


def test_explicit_empty_since_is_rejected():
    result = invoke("job", "logs", "j", "--project", "p", "--zone", "z", "--since", "", "--dry-run")
    assert result.exit_code == 1 and "positive whole duration" in result.output


@pytest.mark.parametrize("value", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"])
def test_timestamp_utc_overflow_is_json_input_error(value):
    result = invoke(
        "job", "logs", "j", "--project", "p", "--zone", "z", "--start", value, "--dry-run"
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["kind"] == "input"
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "field,value",
    [
        ("host", True),
        ("user", 12),
        ("identity", 12),
        ("proxy_jump", False),
        ("ssh_flags", None),
        ("port", True),
        ("port", 22.5),
        ("port", "22"),
    ],
)
@pytest.mark.parametrize("command", ["show", "list", "doctor"])
def test_corrupt_connection_fields_preserve_cli_error_contract(field, value, command):
    from yicloud.ssh import key

    connection = {"host": "host", field: value}
    write_state(
        {
            "accounts": {},
            "connections": {key("environment", "workspace", "p", "z", "dev"): connection},
        }
    )
    args = (
        ["workspace", "doctor", "dev"]
        if command == "doctor"
        else ["workspace", "connection", command] + (["dev"] if command == "show" else [])
    )
    result = invoke(*args, "--project", "p", "--zone", "z")
    assert result.exit_code == 1
    payload = json.loads(result.output)
    if command == "doctor":
        assert payload["data"]["checks"][0]["status"] == "fail"
    else:
        assert payload["error"]["kind"] == "configuration"
