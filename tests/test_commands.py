"""CLI contracts: precise options, useful errors and bounded schema discovery."""

import json

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.client import YicloudClient


@pytest.mark.parametrize("args", [["--unknown"], ["job", "stop", "j", "--follow"]])
@pytest.mark.parametrize("json_output", [False, True])
def test_usage_errors_respect_output_mode(args, json_output):
    result = CliRunner().invoke(main, (["--json"] if json_output else []) + args)
    assert result.exit_code == 1
    if json_output:
        assert json.loads(result.output)["error"]["kind"] == "input"
    else:
        assert "Usage:" in result.output and "--help" in result.output
        assert "Error:" in result.output and '"ok"' not in result.output


@pytest.mark.parametrize(
    "kind,verb,resource,options,expected",
    [
        ("job", "stop", "j", [], {"Project": "p", "ZoneId": "z", "JobId": "j"}),
        ("job", "delete", "j", [], {"Resources": [{"Project": "p", "JobId": "j"}]}),
        ("serving", "scale", "i", ["--replicas", "0"], {"Project": "p", "ID": "i", "Replicas": 0}),
    ],
)
def test_id_dry_run_is_offline_and_preserves_requests(
    account, monkeypatch, kind, verb, resource, options, expected
):
    def forbidden(_):
        pytest.fail("ID dry-run must not send HTTP requests")

    monkeypatch.setattr(
        "yicloud.commands.workloads.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(forbidden)),
    )
    result = CliRunner().invoke(
        main, [kind, verb, resource, "--project", "p", "--zone", "z", "--dry-run", *options]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["body"] == expected


@pytest.mark.parametrize(
    "kind,row",
    [
        ("workspace", "unexpected-row"),
        ("job", None),
        ("ray", {"DisplayName": "friendly", "Namespace": "p", "ZoneId": "z", "RayJobName": 1}),
        ("serving", {"Name": "friendly", "Namespace": "p", "ZoneId": "z", "ID": True}),
    ],
)
def test_name_lookup_invalid_response_retains_json_error_contract(account, monkeypatch, kind, row):
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": [row]}})

    monkeypatch.setattr(
        "yicloud.commands.workloads.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    result = CliRunner().invoke(
        main,
        [
            "--json",
            kind,
            "stop",
            "friendly",
            "--by-name",
            "--project",
            "p",
            "--zone",
            "z",
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False and payload["error"]["kind"] == "platform"
    assert calls == ["GET"]


@pytest.mark.parametrize("kind", ["job", "ray", "serving"])
def test_follow_full_boundary_reports_partial_logs_and_recovery(account, monkeypatch, kind):
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Data": {"Items": [{"Timestamp": "0", "Line": "observed fixture log"}]},
            },
        )

    monkeypatch.setattr(
        "yicloud.commands.workloads.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    result = CliRunner().invoke(
        main,
        [
            kind,
            "logs",
            "fixture",
            "--project",
            "p",
            "--zone",
            "z",
            "--start",
            "0",
            "--limit",
            "1",
            "--follow",
        ],
    )
    assert result.exit_code == 1
    assert "observed fixture log" in result.output
    assert "full and cannot advance" in result.output and "--limit" in result.output
    assert calls == ["GET"]


@pytest.mark.parametrize("value", [True, False])
def test_workload_rejects_duplicate_file_and_set_before_lookup(monkeypatch, value):
    def forbidden(_):
        pytest.fail("Duplicate fields must fail before name lookup")

    monkeypatch.setattr("yicloud.commands.workloads.client_for", forbidden)
    result = CliRunner().invoke(
        main,
        [
            "ray",
            "stop",
            "friendly",
            "--by-name",
            "--project",
            "p",
            "--zone",
            "z",
            "--extra-file",
            "-",
            "--set",
            f"Force={json.dumps(value)}",
        ],
        input='{"Force":true}',
    )
    assert result.exit_code == 1
    assert "both --extra-file and --set: Force" in result.output


@pytest.mark.parametrize(
    "kind,filter_value,list_action,status_action,row,id_field",
    [
        (
            "workspace",
            'Creator="user"',
            "ListWorkspaces",
            "GetWorkspace",
            {"Project": "p", "ZoneId": "z", "Name": "dev", "WorkspaceId": "w"},
            "WorkspaceId",
        ),
        (
            "job",
            "Self=true",
            "ListJobs",
            "GetJob",
            {"Project": "p", "ZoneId": "z", "Name": "dev", "JobId": "j"},
            "JobId",
        ),
        (
            "ray",
            'CreatorId="user-id"',
            "ListRayJobs",
            "GetRayJob",
            {"Namespace": "p", "ZoneId": "z", "DisplayName": "dev", "RayJobName": "r"},
            "JobName",
        ),
        (
            "serving",
            'Scope="mine"',
            "ListInferSet",
            "GetInferSet",
            {"Namespace": "p", "ZoneId": "z", "Name": "dev", "ID": "i"},
            "ID",
        ),
    ],
)
def test_lookup_filters_are_separate_from_final_request(
    account, monkeypatch, kind, filter_value, list_action, status_action, row, id_field
):
    calls = []
    key, encoded = filter_value.split("=", 1)
    value = json.loads(encoded)

    def handler(request):
        calls.append(request)
        if request.url.path.endswith(list_action):
            assert request.url.params[key] == ("true" if value is True else value)
            assert request.url.params["Project"] == "p"
            return httpx.Response(200, json={"Code": 0, "Data": {"Items": [row], "Total": 1}})
        assert request.url.path.endswith(status_action)
        assert key not in request.url.params
        assert request.url.params[id_field] in ("w", "j", "r", "i")
        return httpx.Response(200, json={"Code": 0, "Data": row})

    monkeypatch.setattr(
        "yicloud.commands.workloads.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    result = CliRunner().invoke(
        main,
        [
            kind,
            "status",
            "dev",
            "--project",
            "p",
            "--zone",
            "z",
            "--by-name",
            "--lookup-set",
            filter_value,
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 2


@pytest.mark.parametrize(
    "options",
    [
        ["--lookup-set", 'Creator="user"'],
        ["--by-name", "--lookup-set", 'Project="other"'],
        ["--by-name", "--lookup-set", 'ZoneId="other"'],
        ["--by-name", "--lookup-set", "Offset=20"],
        ["--by-name", "--lookup-set", "Limit=1"],
        ["--by-name", "--lookup-set", "Creator=true"],
        ["--by-name", "--lookup-set", 'Unknown="x"'],
    ],
)
def test_invalid_lookup_filters_never_send_requests(account, monkeypatch, options):
    def forbidden(_):
        pytest.fail("Invalid lookup filters must not send requests")

    monkeypatch.setattr(
        "yicloud.commands.workloads.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(forbidden)),
    )
    result = CliRunner().invoke(
        main, ["workspace", "status", "dev", "--project", "p", "--zone", "z", *options]
    )
    assert result.exit_code == 1, result.output
