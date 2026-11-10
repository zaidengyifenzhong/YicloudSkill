"""Dedicated command coverage and request semantics, without platform credentials."""

import json
import subprocess
import sys

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.client import YicloudClient
from yicloud.config import write_state


def invoke(*args, input=None):
    return CliRunner().invoke(main, ["--json", *args], input=input)


@pytest.mark.parametrize(
    "args,body",
    [
        (
            ["job", "edit", "j", "--project", "p", "--operation", "priority", "--priority", "5"],
            {"Project": "p", "JobId": "j", "Operation": "priority", "Priority": "5"},
        ),
        (
            [
                "workspace",
                "edit",
                "w",
                "--project",
                "p",
                "--zone",
                "z",
                "--internet",
                "false",
                "--env",
                '{"MODE":"test"}',
            ],
            {
                "WorkspaceId": "w",
                "Project": "p",
                "ZoneId": "z",
                "Internet": False,
                "Env": {"MODE": "test"},
            },
        ),
        (
            [
                "serving",
                "update",
                "i",
                "--project",
                "p",
                "--replicas",
                "0",
                "--command",
                "[]",
                "--set",
                "Description=null",
            ],
            {"ID": "i", "Project": "p", "Replicas": 0, "Command": [], "Description": None},
        ),
        (
            [
                "job",
                "batch-delete",
                "--resources",
                '[{"Project":"p","JobId":"j1"},{"Project":"p","JobId":"j2"}]',
            ],
            {"Resources": [{"Project": "p", "JobId": "j1"}, {"Project": "p", "JobId": "j2"}]},
        ),
    ],
)
def test_writes_verify_scope_then_send_exactly_one_write(args, body, account, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "GET":
            fields = dict(request.url.params)
            key = next(k for k in ("WorkspaceId", "JobId", "ID") if k in fields)
            return httpx.Response(
                200,
                json={"Code": 0, "Data": {key: fields[key], "Project": "p", "ZoneId": "z"}},
            )
        assert request.method == "POST"
        assert json.loads(request.content) == body
        return httpx.Response(200, json={"Code": 0, "Data": {"saved": True}})

    monkeypatch.setattr(
        "yicloud.commands.catalog_commands.client_for",
        lambda ctx: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    if "--zone" not in args:
        args = [*args, "--zone", "z"]
    result = invoke(*args)
    assert result.exit_code == 0, result.output
    assert sum(request.method == "POST" for request in calls) == 1
    assert calls[0].method == "GET" and calls[-1].method == "POST"


@pytest.fixture
def named_context():
    write_state(
        {
            "accounts": {"test": {}},
            "contexts": {"lab": {"account": "test", "project": "context-p", "zone": "context-z"}},
            "current_context": "lab",
        }
    )


def test_context_only_supplies_missing_fields_and_does_not_mutate_files(named_context):
    result = invoke("workspace", "edit", "w", "--name", "new", "--project", "explicit", "--dry-run")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["data"]["body"] == {
        "WorkspaceId": "w",
        "Name": "new",
        "Project": "explicit",
        "ZoneId": "context-z",
    }
    assert data["meta"]["context"]["project"]["source"] == "argument"
    assert data["meta"]["context"]["zone"]["source"] == "context"
    result = invoke(
        "workspace", "edit", "--file", "-", "--dry-run", input='{"WorkspaceId":"w","Project":"p"}'
    )
    assert result.exit_code == 1 and "ZoneId" in result.output
    result = invoke("workspace", "edit", "w", "--set", "Project=null", "--dry-run")
    assert result.exit_code == 1 and "Project" in result.output
    result = invoke("--no-context", "workspace", "edit", "w", "--dry-run")
    assert result.exit_code == 1 and "Project" in result.output


@pytest.mark.parametrize(
    "args,input",
    [
        (["job", "edit", "j", "--file", "-"], "{}"),
        (["job", "edit", "--file", "-", "--operation", "top"], "{}"),
        (["job", "edit", "j", "--job-id", "other"], None),
        (["job", "edit", "j", "--project", "p", "--set", 'Project="other"'], None),
        (["job", "edit", "j", "--project", "p", "--operation", "bad"], None),
        (["job", "edit", "--project", "p", "--operation", "top"], None),
        (["workspace", "edit", "w", "--env", "{broken"], None),
        (["workspace", "edit", "w", "--internet", "maybe"], None),
        (["serving", "update", "i", "--replicas", "1.5"], None),
        (["dataset", "list-data-sets", "--project", "p", "--all", "--dry-run"], None),
        (["dataset", "list-data-sets", "--project", "p", "--all", "--limit", "0"], None),
        (["dataset", "list-data-sets", "--project", "p", "--all", "--set", "Limit=null"], None),
        (["dataset", "list-data-sets", "--project", "p", "--all", "--offset", "-1"], None),
        (["oss", "create-bucket", "--project", "p", "--bucket", "b", "--set", "Unknown=1"], None),
    ],
)
def test_invalid_input_fails_before_client(args, input, monkeypatch, separated_cli_runner):
    def forbidden(ctx):
        pytest.fail("Invalid input constructed a client")

    monkeypatch.setattr("yicloud.commands.catalog_commands.client_for", forbidden)
    result = separated_cli_runner.invoke(main, ["--json", *args], input=input)
    assert result.exit_code == 1 and result.stdout == "", result.output
    assert json.loads(result.stderr)["error"]["kind"] == "input"


def test_pagination_is_explicit_and_request_file_stays_unchanged(account, monkeypatch):
    calls = []

    def handler(request):
        query = dict(request.url.params)
        calls.append(query)
        offset = int(query.get("Offset", 0))
        return httpx.Response(
            200, json={"Code": 0, "Data": {"Items": [{"ID": offset}], "Total": 2}}
        )

    monkeypatch.setattr(
        "yicloud.commands.catalog_commands.client_for",
        lambda ctx: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    result = invoke("dataset", "list-data-sets", "--file", "-", input='{"Project":"p"}')
    assert result.exit_code == 0, result.output
    assert calls == [{"Project": "p"}]
    calls.clear()
    result = invoke("dataset", "list-data-sets", "--project", "p", "--limit", "1", "--all")
    assert result.exit_code == 0, result.output
    assert [c["Offset"] for c in calls] == ["0", "1"]
    assert json.loads(result.output)["data"]["Total"] == 2


def test_file_directory_pagination_handles_files_response(account, monkeypatch):
    calls = []

    def handler(request):
        assert request.url.path == "/fs/v1alpha2/ListDir"
        offset = int(request.url.params["Offset"])
        calls.append(offset)
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Data": {
                    "Files": [{"Name": f"file-{offset}"}],
                    "Limit": 1,
                    "Offset": offset,
                    "Total": 2,
                },
            },
        )

    monkeypatch.setattr(
        "yicloud.commands.catalog_commands.client_for",
        lambda ctx: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    result = invoke("fs", "list-dir", "--path", "/fixture", "--limit", "1", "--all")
    assert result.exit_code == 0, result.output
    assert calls == [0, 1]
    assert json.loads(result.output)["data"] == {
        "Items": [{"Name": "file-0"}, {"Name": "file-1"}],
        "Total": 2,
    }


def test_download_and_required_output(account, monkeypatch, tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"fixture logs")

    monkeypatch.setattr(
        "yicloud.commands.catalog_commands.client_for",
        lambda ctx: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    params = {"Project": "p", "ID": "i", "Start": 0, "End": 1}
    args = ["serving", "download-infer-set-logs", "--file", "-"]
    result = invoke(*args, input=json.dumps(params))
    assert result.exit_code == 1 and "--output" in result.output
    assert not calls
    target = tmp_path / "logs.txt"
    result = invoke(*args, "--output", str(target), input=json.dumps(params))
    assert result.exit_code == 0, result.output
    assert target.read_bytes() == b"fixture logs"


def test_discovery_reports_routes_and_deferred_protocols():
    result = invoke("api", "list", "--service", "inferset")
    rows = {r["action"]: r for r in json.loads(result.output)["data"]}
    assert rows["UpdateInferSet"]["command"] == "yicloud serving update"
    assert rows["GetInferSetTerminal"]["command"] is None
    result = invoke("api", "describe", "job", "EditJob")
    assert json.loads(result.output)["data"]["command"] == "yicloud job edit"


def test_field_option_secrets_are_redacted():
    result = invoke("iam", "delete-access-key", "--access-key", "synthetic-secret", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "synthetic-secret" not in result.output
    assert json.loads(result.output)["data"]["body"]["AccessKey"] == "[REDACTED]"


def test_real_module_invocation_and_json_error_stream():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yicloud",
            "--json",
            "job",
            "edit",
            "j",
            "--project",
            "p",
            "--operation",
            "top",
            "--top-action",
            "set",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data"]["body"]["TopAction"] == "set"
    assert result.stderr == ""
    result = subprocess.run(
        [sys.executable, "-m", "yicloud", "--json", "job", "edit", "j"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1 and result.stdout == ""
    assert json.loads(result.stderr)["error"]["kind"] == "input"
