"""Account-source conflicts and honest local-validation guarantees."""

import json
import os
import subprocess
import sys

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.client import YicloudClient
from yicloud.config import Account, write_state
from yicloud.errors import InputError


@pytest.fixture
def saved_account():
    write_state(
        {
            "current": "saved",
            "accounts": {
                "saved": {
                    "host": "https://saved.example",
                    "region": "saved-region",
                    "public_key": "saved-public-sensitive",
                    "secret_key": "saved-secret-sensitive",
                }
            },
            "contexts": {"lab": {"account": "saved", "project": "p", "zone": "z"}},
            "current_context": "lab",
        }
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("YICLOUD_AUTHN_TOKEN", "environment-token-sensitive"),
        ("YICLOUD_PUBLIC_KEY", "environment-public-sensitive"),
        ("YICLOUD_SECRET_KEY", "environment-secret-sensitive"),
        ("YICLOUD_IS_SERVICE_ACCOUNT", "true"),
        ("YICLOUD_AUTHN_TOKEN", ""),
        ("YICLOUD_IS_SERVICE_ACCOUNT", ""),
        ("YICLOUD_API_HOST", "https://other-private.example"),
        ("YICLOUD_REGION_ID", "other-private-region"),
    ],
)
def test_explicit_account_environment_conflict_before_http(saved_account, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(InputError) as error:
        Account.resolve("saved")
    assert key in str(error.value)
    if value:
        assert value not in str(error.value)
    result = CliRunner().invoke(
        main,
        [
            "--json",
            "--account",
            "saved",
            "api",
            "call",
            "mc",
            "ListZones",
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["kind"] == "input"
    assert key in result.output
    assert "saved-secret-sensitive" not in result.output
    if value:
        assert value not in result.output


def test_conflict_safe_in_actual_subprocess(saved_account, monkeypatch):
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", "actual-process-secret")
    result = subprocess.run(
        [sys.executable, "-m", "yicloud", "--account", "saved", "resources", "zones"],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=10,
    )
    assert result.returncode == 1
    assert "YICLOUD_AUTHN_TOKEN" in result.stderr
    assert "actual-process-secret" not in result.stdout + result.stderr


def test_implicit_and_context_accounts_keep_environment_auth(saved_account, monkeypatch):
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", "environment-token-sensitive")
    monkeypatch.setenv("YICLOUD_API_HOST", "https://environment.example")
    resolved = Account.resolve()
    assert resolved.token == "environment-token-sensitive"
    assert resolved.public_key == resolved.secret_key == ""
    assert resolved.host == "https://environment.example"
    result = CliRunner().invoke(main, ["--json", "account", "current"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["host"] == "https://environment.example"
    assert "environment-token-sensitive" not in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["account", "list"],
        ["account", "use", "saved"],
        ["context", "show"],
        ["api", "describe", "mc", "ListZones"],
    ],
)
def test_local_management_does_not_resolve_conflicting_auth(saved_account, monkeypatch, args):
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", "environment-token-sensitive")
    result = CliRunner().invoke(main, ["--account", "saved", *args])
    assert result.exit_code == 0, result.output
    assert "environment-token-sensitive" not in result.output
    assert "saved-secret-sensitive" not in result.output
    if args == ["context", "show"]:
        assert json.loads(result.output)["account_conflict"]["kind"] == "input"


def test_same_environment_route_and_explicit_route_flags(saved_account, monkeypatch):
    monkeypatch.setenv("YICLOUD_API_HOST", "https://saved.example/")
    monkeypatch.setenv("YICLOUD_REGION_ID", "saved-region")
    assert Account.resolve("saved").host == "https://saved.example"
    monkeypatch.setenv("YICLOUD_API_HOST", "https://environment.example")
    monkeypatch.setenv("YICLOUD_REGION_ID", "environment-region")
    account = Account.resolve("saved", host="https://flag.example", region="flag-region")
    assert account.host == "https://flag.example" and account.region == "flag-region"
    monkeypatch.setenv("YICLOUD_SECRET_KEY", "environment-secret-sensitive")
    with pytest.raises(InputError, match="YICLOUD_SECRET_KEY"):
        Account.resolve("saved", host="https://flag.example", region="flag-region")


@pytest.mark.parametrize(
    "field,key", [("host", "YICLOUD_API_HOST"), ("region", "YICLOUD_REGION_ID")]
)
def test_empty_route_flag_cannot_bypass_environment_conflict(
    saved_account, monkeypatch, field, key
):
    monkeypatch.setenv(key, "https://other.example" if field == "host" else "other-region")
    with pytest.raises(InputError, match=key):
        Account.resolve("saved", **{field: ""})


def test_dry_run_reports_checks_without_transport():
    def forbidden(_):
        pytest.fail("local request validation must not make HTTP calls")

    with YicloudClient(Account(), transport=httpx.MockTransport(forbidden)) as client:
        result = client.dry_run("job", "StopJob", {"Project": "p", "ZoneId": "z", "JobId": "j"})
        relaxed = client.dry_run(
            "mc", "ListZones", {"FutureField": "value"}, allow_unknown_fields=True
        )
    assert result["validation"] == "passed"
    assert result["validation_scope"] == "local_pinned_sdk_request"
    assert result["checks"]["unknown_fields"] == "rejected"
    assert relaxed["checks"]["unknown_fields"] == "allowed"
    assert result["validation_source"]["sdk_commit"]
    for key, value in result["limitations"].items():
        assert value == "not_checked" if key != "network" else "may perform reads" in value


def test_name_dry_run_reports_local_scope_despite_lookup(account, monkeypatch):
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
        main,
        [
            "--json",
            "job",
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
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert calls == [("GET", "/job/v1alpha1/ListJobs")]
    assert data["validation_scope"] == "local_pinned_sdk_request"
    assert data["limitations"]["authentication_and_permissions"] == "not_checked"
    assert "may perform reads" in data["limitations"]["network"]
