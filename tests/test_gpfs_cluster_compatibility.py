"""Narrow GPFS request compatibility; no platform credentials or file access."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import httpx
import pytest
from click.testing import CliRunner

from yicloud.catalog import catalog, operation, request_schema, validate
from yicloud.cli import main
from yicloud.client import YicloudClient
from yicloud.errors import InputError


ACTIONS = {
    "CreateFilesetWithQuota": {"Name": "fixture", "Capacity": 1},
    "DeleteFileset": {"Name": "fixture"},
    "GetFileset": {"Name": "fixture"},
    "ListFilesetsWithQuotaInfo": {},
    "SetFilesetQuota": {"Name": "fixture", "Capacity": 1},
    "UpdateFileset": {"Name": "fixture", "Capacity": 1},
}
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("action,required", ACTIONS.items())
@pytest.mark.parametrize("cluster", ["gpfs1", "gpfs2", "fixture-future-cluster", None])
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


@pytest.mark.parametrize("action,required", ACTIONS.items())
@pytest.mark.parametrize("allow_unknown", [True, False])
def test_only_cluster_enum_is_relaxed(action, required, allow_unknown):
    op = operation("fs", action)
    field = request_schema(op)["properties"]["FsCluster"]
    assert field["type"] == "string" and field["nullable"] is True and "enum" not in field
    for value in [1, True, [], {}]:
        with pytest.raises(InputError, match="FsCluster: expected string"):
            validate(op, {**required, "FsCluster": value}, allow_unknown)
    with pytest.raises(InputError, match="Fs: expected one of"):
        validate(op, {**required, "Fs": "other"}, allow_unknown)
    if required:
        with pytest.raises(InputError, match="required"):
            validate(op, {"FsCluster": "gpfs2"}, allow_unknown)
    if not allow_unknown:
        with pytest.raises(InputError, match="unknown field"):
            validate(op, {**required, "Source": "gpfs://fixture/path"})


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


def test_override_scope_and_other_constraints_stay_explicit():
    overrides = json.loads((ROOT / "tools/catalog_overrides.json").read_text(encoding="utf-8"))
    corrections = {k: v for k, v in overrides.items() if k.startswith("fs/")}
    assert corrections.keys() == {"fs/" + action for action in ACTIONS}
    for action, correction in corrections.items():
        assert correction["source"].startswith("https://gitee.com/yicloud-team/")
        assert correction["fields"].keys() == {"FsCluster"}
        assert correction["fields"]["FsCluster"]["enum"] is None
        op = operation(*action.split("/"))
        assert request_schema(op)["properties"]["Fs"]["enum"] == ["GPFS"]
    assert catalog()["definitions"]["mc"]["ListSKUsReq"]["properties"]["Scope"]["enum"] == [
        "public",
        "tenant",
        "project",
    ]


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


@pytest.mark.parametrize("case", ["valid", "missing_constraint", "missing_field", "missing_action"])
def test_generator_applies_removal_and_rejects_missing_paths(tmp_path, case):
    go = shutil.which("go")
    if go is None:
        pytest.skip("Go toolchain needed for catalog generator integration")
    sdk = tmp_path / "sdk/services/fs"
    sdk.mkdir(parents=True)
    # Small AST input in a real, isolated Git repository; no shell shim is needed.
    (sdk / "actions.go").write_text(
        """package fs
var client = T{productCode: "fs", lastVersion: "v1alpha2"}
const FsClusterGpfs1 = "gpfs1"
const FsGPFS = "GPFS"
type GetFilesetReq struct {
 FsCluster *string `json:"FsCluster,omitempty" binding:"omitempty"` // SDK常量: FsClusterGpfs1
 Fs *string `json:"Fs,omitempty" binding:"omitempty"` // SDK常量: FsGPFS
}
func GetFileset(ctx C, req *GetFilesetReq) {
 path := fmt.Sprintf("/%s/%s/%s", client.productCode, client.lastVersion, utils.GetCurrentFuncsName())
 client.Get(ctx, path, req, nil)
}
""",
        encoding="utf-8",
    )
    sdk_root = sdk.parent.parent
    git_env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(sdk_root), *args],
            env=git_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()

    empty_template = tmp_path / "empty-git-template"
    empty_template.mkdir()
    git("init", "--template=" + str(empty_template))
    git("add", "services")
    git(
        "-c",
        "user.name=Generator Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "Add synthetic SDK fixture",
    )
    fixture_commit = git("rev-parse", "HEAD")
    assert len(fixture_commit) == 40 and git("status", "--porcelain") == ""
    tools = tmp_path / "tools"
    tools.mkdir()
    # This copy tests override behavior, not generation against the real SDK.
    # Substitute only the expected pin; preserve every other source byte and
    # keep the production generator's upstream SDK requirement unchanged.
    source_bytes = (ROOT / "tools/catalog.go").read_bytes()
    source = source_bytes.decode("utf-8")
    upstream_commit = catalog()["sdk_commit"]
    assert fixture_commit != upstream_commit and source.count(upstream_commit) == 2
    fixture_source = source.replace(upstream_commit, fixture_commit).encode("utf-8")
    assert fixture_source.count(fixture_commit.encode("ascii")) == 2
    assert (
        fixture_source.replace(fixture_commit.encode("ascii"), upstream_commit.encode("ascii"))
        == source_bytes
    )
    generator = tools / "catalog.go"
    generator.write_bytes(fixture_source)
    action = "fs/MissingAction" if case == "missing_action" else "fs/GetFileset"
    field = "MissingField" if case == "missing_field" else "FsCluster"
    removal = "missing_constraint" if case == "missing_constraint" else "enum"
    (tools / "catalog_overrides.json").write_text(
        json.dumps(
            {
                action: {
                    "source": "synthetic generator fixture",
                    "fields": {field: {removal: None}, "Fs": {"description": "preserved"}},
                }
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [go, "run", str(generator), str(sdk_root)],
        cwd=tmp_path,
        env=git_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if case == "valid":
        assert result.returncode == 0, result.stderr
        generated = json.loads(result.stdout)
        assert generated["sdk_commit"] == fixture_commit
        fields = generated["definitions"]["fs"]["GetFilesetReq"]["properties"]
        assert fields["FsCluster"]["type"] == "string" and fields["FsCluster"]["nullable"]
        assert "enum" not in fields["FsCluster"]
        assert fields["Fs"]["enum"] == ["GPFS"]
        assert fields["Fs"]["description"] == "preserved"
    else:
        expected = {
            "missing_constraint": "removes missing constraint",
            "missing_field": "references missing field",
            "missing_action": "unapplied catalog overrides",
        }[case]
        assert result.returncode != 0 and expected in result.stderr
