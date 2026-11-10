"""Narrow GPFS request compatibility; no platform credentials or file access."""

import json

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.client import YicloudClient


ACTIONS = {
    "CreateFilesetWithQuota": {"Name": "fixture", "Capacity": 1},
    "DeleteFileset": {"Name": "fixture"},
    "GetFileset": {"Name": "fixture"},
    "ListFilesetsWithQuotaInfo": {},
    "SetFilesetQuota": {"Name": "fixture", "Capacity": 1},
    "UpdateFileset": {"Name": "fixture", "Capacity": 1},
}


@pytest.mark.parametrize("action,required", ACTIONS.items())
@pytest.mark.parametrize("cluster", ["fixture-future-cluster", None])
def test_cluster_string_and_null_are_encoded_without_rewriting(account, action, required, cluster):
    params = {**required, "Fs": "GPFS", "FsCluster": cluster}
    with YicloudClient(account) as client:
        preview = client.dry_run("fs", action, params)
    if preview["method"] == "GET":
        assert {x["name"]: x["value"] for x in preview["query"]}["FsCluster"] == (
            "" if cluster is None else cluster
        )
    else:
        assert preview["body"] == params


@pytest.mark.parametrize("mode", ["flags", "file", "api"])
def test_actual_cli_routes_send_exact_discovered_cluster(account, monkeypatch, mode):
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "GET" and request.url.path == "/fs/v1alpha2/GetFileset"
        assert dict(request.url.params) == {
            "Name": "fixture-set",
            "Fs": "GPFS",
            "FsCluster": "fixture-new-cluster",
        }
        return httpx.Response(200, json={"Code": 0, "Data": {"Name": "fixture-set"}})

    def factory(ctx):
        return YicloudClient(account, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("yicloud.commands.catalog_commands.client_for", factory)
    monkeypatch.setattr("yicloud.commands.api.client_for", factory)
    params = {"Name": "fixture-set", "Fs": "GPFS", "FsCluster": "fixture-new-cluster"}
    if mode == "flags":
        args = [
            "fs",
            "get-fileset",
            "--name",
            params["Name"],
            "--fs",
            "GPFS",
            "--fs-cluster",
            params["FsCluster"],
        ]
    elif mode == "file":
        args = ["fs", "get-fileset", "--file", "-"]
    else:
        args = ["api", "call", "fs", "GetFileset", "--file", "-"]
    result = CliRunner().invoke(main, ["--json", "--no-context", *args], input=json.dumps(params))
    assert result.exit_code == 0, result.output
    assert len(seen) == 1


def test_list_cli_preserves_cluster_parameter_and_mixed_platform_metadata(account, monkeypatch):
    # The platform may accept FsCluster yet ignore the filter. Preserve its actual
    # response so callers can inspect each BucketResponse.FsCluster themselves.
    payload = {
        "Items": [
            {"BucketResponse": {"Bucket": "fixture-a", "FsCluster": "gpfs2"}},
            {"BucketResponse": {"Bucket": "fixture-b", "FsCluster": "gpfs3"}},
        ],
        "Total": 2,
    }

    def handler(request):
        assert request.url.params["FsCluster"] == "gpfs2"
        return httpx.Response(200, json={"Code": 0, "Data": payload})

    monkeypatch.setattr(
        "yicloud.commands.catalog_commands.client_for",
        lambda ctx: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    result = CliRunner().invoke(
        main,
        [
            "--json",
            "--no-context",
            "fs",
            "list-filesets-with-quota-info",
            "--fs",
            "GPFS",
            "--fs-cluster",
            "gpfs2",
            "--project",
            "fixture-project",
            "--zone",
            "fixture-zone",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"] == payload
