"""CLI contracts: precise options, useful errors and bounded schema discovery."""

import json

import httpx
import pytest
from click.testing import CliRunner

from yicloud.catalog import catalog, operation, request_schema
from yicloud.cli import main
from yicloud.client import YicloudClient


@pytest.mark.parametrize(
    "args",
    [
        ["job", "stop", "j", "--replicas", "1"],
        ["job", "status", "j", "--follow"],
        ["workspace", "create", "--command", "true"],
        ["ray", "create", "--name", "x"],
        ["serving", "create", "--image", "x"],
        ["resources", "zones", "--project", "p"],
        ["project", "status", "--all"],
        ["project", "list", "--zone", "z"],
        ["workspace", "ssh", "w", "--project", "p", "--zone", "z", "true"],
        ["serving", "scale", "i", "--project", "p", "--zone", "z"],
        ["ray", "create"],
    ],
)
def test_invalid_options_fail_before_client(monkeypatch, args):
    def forbidden(_):
        pytest.fail("Invalid invocation must not create an API client")

    for module in ("workloads", "discovery"):
        monkeypatch.setattr(f"yicloud.commands.{module}.client_for", forbidden)
    result = CliRunner().invoke(main, ["--json", *args])
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["kind"] == "input"


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


def test_root_option_value_is_not_json_flag():
    result = CliRunner().invoke(main, ["--account", "--json", "--unknown"])
    assert result.exit_code == 1 and "Error:" in result.output


@pytest.mark.parametrize(
    "extra", [["--interval", "2"], ["--set", "Limit=500"], ["--set", 'Direction="forward"']]
)
def test_log_controls_cannot_be_silently_ignored(monkeypatch, extra):
    def forbidden(_):
        pytest.fail("Invalid log options must fail before client construction")

    monkeypatch.setattr("yicloud.commands.workloads.client_for", forbidden)
    result = CliRunner().invoke(main, ["job", "logs", "j", "--project", "p", "--zone", "z", *extra])
    assert result.exit_code == 1 and "Error:" in result.output


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


def test_name_dry_run_only_reads(account, monkeypatch):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Data": {
                    "Items": [{"JobId": "j", "Name": "friendly", "Project": "p", "ZoneId": "z"}]
                },
            },
        )

    monkeypatch.setattr(
        "yicloud.commands.workloads.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    result = CliRunner().invoke(
        main, ["job", "stop", "friendly", "--by-name", "--project", "p", "--zone", "z", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert calls == [("GET", "/job/v1alpha1/ListJobs")]
    assert json.loads(result.output)["body"]["JobId"] == "j"


@pytest.mark.parametrize(
    "service,action", [("job", "StopJob"), ("job", "CreateJob"), ("ray", "CreateRayJob")]
)
def test_describe_contains_only_reachable_request_definitions(service, action):
    result = CliRunner().invoke(main, ["api", "describe", service, action])
    assert result.exit_code == 0
    data = json.loads(result.output)
    op = operation(service, action)
    assert data["schema"] == request_schema(op)
    refs = set()

    def walk(value):
        if isinstance(value, dict):
            if "ref" in value and value["ref"] not in refs:
                ref = value["ref"]
                refs.add(ref)
                walk(data["definitions"][ref])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data["schema"])
    assert refs == data["definitions"].keys()
    assert len(refs) < len(catalog()["definitions"][service])


@pytest.mark.parametrize("flag,field", [("--project", "Project"), ("--zone", "ZoneId")])
@pytest.mark.parametrize("value", ["scope", "other"])
def test_discovery_rejects_duplicate_scope_before_request(monkeypatch, flag, field, value):
    def forbidden(_):
        pytest.fail("Conflicting scope must fail before client construction")

    monkeypatch.setattr("yicloud.commands.discovery.client_for", forbidden)
    result = CliRunner().invoke(
        main, ["resources", "skus", flag, "scope", "--set", f'{field}="{value}"']
    )
    assert result.exit_code == 1
    assert "both scope flags and --set" in result.output and field in result.output


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
            "--file",
            "-",
            "--set",
            f"Force={json.dumps(value)}",
        ],
        input='{"Force":true}',
    )
    assert result.exit_code == 1
    assert "both --file and --set: Force" in result.output


def test_discovery_accepts_scope_from_set_alone(account, monkeypatch):
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": []}})

    monkeypatch.setattr(
        "yicloud.commands.discovery.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    result = CliRunner().invoke(
        main, ["resources", "nodes", "--set", 'Project="p"', "--set", 'ZoneId="z"']
    )
    assert result.exit_code == 0, result.output
    assert calls[0]["Project"] == "p" and calls[0]["ZoneId"] == "z"


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
