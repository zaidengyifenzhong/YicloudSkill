"""Explicit account identities must never fall back to another profile."""

import json

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.client import YicloudClient
from yicloud.config import Account, read_state, write_state
from yicloud.errors import ConfigurationError, InputError


JOB = {"Project": "synthetic-project", "ZoneId": "synthetic-zone", "JobId": "synthetic-job"}
ALIASES = ["", " \t ", " account ", "测试账号"]


@pytest.fixture
def profiles():
    state = {
        "current": "synthetic-current",
        "accounts": {
            "synthetic-current": {
                "host": "https://current.invalid",
                "region": "current-region",
                "token": "synthetic-current-token",
            }
        },
    }
    write_state(state)
    return state


def add_profile(state, alias):
    state["accounts"][alias] = {
        "host": "https://selected.invalid",
        "region": "selected-region",
        "token": "synthetic-selected-token",
    }
    write_state(state)


@pytest.mark.parametrize("alias", ["", " \t ", "missing", " synthetic-current "])
def test_unregistered_alias_fails_before_http(profiles, monkeypatch, alias):
    def forbidden(**kwargs):
        pytest.fail("Unknown account must fail before constructing HTTP client")

    monkeypatch.setattr("yicloud.transport.httpx.Client", forbidden)
    with pytest.raises(ConfigurationError, match="Unknown account"):
        YicloudClient.from_account(alias)
    result = CliRunner().invoke(
        main,
        ["--json", "--account", alias, "api", "call", "job", "StopJob", "--file", "-"],
        input=json.dumps(JOB),
    )
    assert result.exit_code == 1
    error = json.loads(result.output)["error"]
    assert error["kind"] == "configuration" and error["outcome_unknown"] is False
    assert "synthetic-current-token" not in result.output


@pytest.mark.parametrize("alias", [0, False, b"saved"])
def test_public_client_rejects_nonstring_before_http(profiles, monkeypatch, alias):
    def forbidden(**kwargs):
        pytest.fail("Invalid alias types must fail before constructing HTTP client")

    monkeypatch.setattr("yicloud.transport.httpx.Client", forbidden)
    with pytest.raises(InputError):
        YicloudClient.from_account(alias)


@pytest.mark.parametrize("alias", ALIASES)
def test_registered_alias_preserves_identity_and_credentials(profiles, alias):
    add_profile(profiles, alias)
    calls = []

    def handler(request):
        calls.append(
            (
                request.method,
                request.url.host,
                request.headers["X-OGW-REGION-ID"],
                request.headers["Authorization"] == "synthetic-selected-token",
            )
        )
        return httpx.Response(200, json={"Code": 0, "Data": {"Status": "Stopping"}})

    account = Account.resolve(alias)
    assert account.alias == alias
    with YicloudClient.from_account(alias, transport=httpx.MockTransport(handler)) as client:
        assert client.account.alias == alias
        client.call("job", "StopJob", JOB)
    assert calls == [("POST", "selected.invalid", "selected-region", True)]
    result = CliRunner().invoke(main, ["--json", "--account", alias, "account", "current"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data == {"alias": alias, "host": "https://selected.invalid", "region": "selected-region"}


@pytest.mark.parametrize("alias", ALIASES)
def test_current_alias_is_also_exact(profiles, alias):
    profiles["current"] = alias
    write_state(profiles)
    with pytest.raises(ConfigurationError, match="Unknown account"):
        Account.resolve()
    add_profile(profiles, alias)
    account = Account.resolve(None)
    assert account.alias == alias
    assert account.host == "https://selected.invalid"


def test_none_keeps_current_default_and_environment_precedence(profiles, monkeypatch):
    account = Account.resolve(None)
    assert account.alias == "synthetic-current"
    assert account.token == "synthetic-current-token"
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", "synthetic-environment-token")
    monkeypatch.setenv("YICLOUD_API_HOST", "https://environment.invalid")
    monkeypatch.setenv("YICLOUD_REGION_ID", "environment-region")
    account = Account.resolve(None)
    assert account.alias == "synthetic-current"
    assert account.token == "synthetic-environment-token"
    assert account.host == "https://environment.invalid" and account.region == "environment-region"


@pytest.mark.parametrize("legacy_alias", [None, ""])
def test_no_current_keeps_environment_identity(monkeypatch, legacy_alias):
    if legacy_alias is not None:
        write_state({"accounts": {legacy_alias: {"token": "synthetic-selected-token"}}})
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", "synthetic-environment-token")
    account = Account.resolve(None)
    assert account.alias == "environment"
    assert account.token == "synthetic-environment-token"


@pytest.mark.parametrize("alias", ALIASES)
def test_legacy_alias_keeps_environment_conflict_and_route_contracts(profiles, monkeypatch, alias):
    add_profile(profiles, alias)
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", "synthetic-environment-token")
    with pytest.raises(InputError, match="YICLOUD_AUTHN_TOKEN"):
        Account.resolve(alias)
    assert Account.resolve(alias, explicit_account=False).token == "synthetic-environment-token"
    monkeypatch.delenv("YICLOUD_AUTHN_TOKEN")
    monkeypatch.setenv("YICLOUD_API_HOST", "https://other.invalid")
    monkeypatch.setenv("YICLOUD_REGION_ID", "other-region")
    with pytest.raises(InputError, match="YICLOUD_API_HOST"):
        Account.resolve(alias)
    account = Account.resolve(alias, host="https://flag.invalid", region="flag-region")
    assert account.alias == alias
    assert account.host == "https://flag.invalid" and account.region == "flag-region"
    monkeypatch.setenv("YICLOUD_API_HOST", "https://selected.invalid/")
    monkeypatch.setenv("YICLOUD_REGION_ID", "selected-region")
    assert Account.resolve(alias).host == "https://selected.invalid"


@pytest.mark.parametrize("alias", ALIASES)
def test_local_management_can_recover_legacy_profiles(profiles, alias):
    add_profile(profiles, alias)
    result = CliRunner().invoke(main, ["--json", "account", "list"])
    assert result.exit_code == 0
    assert alias in [row["alias"] for row in json.loads(result.output)["data"]]
    result = CliRunner().invoke(main, ["--json", "account", "remove", alias])
    assert result.exit_code == 0
    assert alias not in read_state()["accounts"]
