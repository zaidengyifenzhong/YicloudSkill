"""Host parsing must fail locally while retaining valid HTTPS origin routing."""

import json

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.client import YicloudClient
from yicloud.config import Account, write_state
from yicloud.errors import ConfigurationError


@pytest.mark.parametrize(
    "host",
    [
        "https://example.invalid:abc",
        "https://example.invalid:65536",
        "https://[::1",
        "https://example.invalid:443\n",
        "https://\u200b.invalid",
        "https://example.invalid?",
        "https://@example.invalid",
    ],
)
def test_invalid_host_is_a_local_configuration_error(host, monkeypatch):
    with pytest.raises(ConfigurationError, match="HTTPS origin"):
        Account(host=host)

    def forbidden(**kwargs):
        pytest.fail("Invalid hosts must fail before creating any HTTP client")

    monkeypatch.setattr("yicloud.transport.httpx.Client", forbidden)
    result = CliRunner().invoke(main, ["--json", "--host", host, "account", "check"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False and payload["error"]["kind"] == "configuration"
    assert payload["error"]["outcome_unknown"] is False
    assert host not in result.output


@pytest.mark.parametrize(
    "host,normalized,port",
    [
        ("https://example.invalid", "https://example.invalid", 443),
        ("https://example.invalid:8443", "https://example.invalid:8443", 8443),
        ("https://[::1]:8443/", "https://[::1]:8443", 8443),
        ("https://例子.invalid:8443", "https://例子.invalid:8443", 8443),
    ],
)
def test_valid_explicit_ports_and_ipv6_keep_request_routing(host, normalized, port, monkeypatch):
    assert Account(host=host).host == normalized
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": []}})

    original_client = httpx.Client
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", "synthetic-account-token")
    monkeypatch.setattr(
        "yicloud.transport.httpx.Client",
        lambda **kwargs: original_client(**dict(kwargs, transport=httpx.MockTransport(handler))),
    )
    result = CliRunner().invoke(main, ["--json", "--host", host, "account", "check"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["ok"] is True
    assert len(calls) == 1 and calls[0].path == "/mc/v1alpha1/ListZones"
    assert (calls[0].port if calls[0].port is not None else 443) == port
    if "例子" in host:
        assert calls[0].raw_host == b"xn--fsqu00a.invalid"
    assert "synthetic-account-token" not in result.output


@pytest.fixture
def saved_host_profile():
    # Exact/legacy alias selection is covered in test_account_selection_contracts.
    # Once selected, host validation and routing do not depend on alias spelling.
    alias = "saved"
    write_state(
        {
            "current": alias,
            "accounts": {
                alias: {
                    "host": "https://saved.invalid",
                    "region": "saved-region",
                    "token": "synthetic-saved-token",
                }
            },
        }
    )
    return alias


@pytest.mark.parametrize("host", ["", False, " "])
def test_explicit_invalid_host_never_falls_back_before_http(saved_host_profile, monkeypatch, host):
    def forbidden(**kwargs):
        pytest.fail("Invalid explicit host must fail before constructing any HTTP client")

    monkeypatch.setattr("yicloud.transport.httpx.Client", forbidden)
    with pytest.raises(ConfigurationError):
        Account(host=host)
    # Both default-account and explicit-account callers use the public resolver.
    for alias in (None, saved_host_profile):
        with pytest.raises(ConfigurationError):
            YicloudClient(Account.resolve(alias, host=host))


@pytest.mark.parametrize(
    "host,env_host,region,env_region,expected_host,expected_region",
    [
        (None, None, None, None, "https://saved.invalid", "saved-region"),
        (None, "", None, "", "https://saved.invalid", "saved-region"),
        (
            None,
            "https://environment.invalid/",
            None,
            "env-region",
            "https://environment.invalid",
            "env-region",
        ),
        (
            "https://flag.invalid/",
            "https://environment.invalid",
            "flag-region",
            "env-region",
            "https://flag.invalid",
            "flag-region",
        ),
        ("https://flag.invalid", None, None, "env-region", "https://flag.invalid", "env-region"),
    ],
)
def test_none_and_valid_host_keep_route_precedence(
    saved_host_profile,
    monkeypatch,
    host,
    env_host,
    region,
    env_region,
    expected_host,
    expected_region,
):
    if env_host is not None:
        monkeypatch.setenv("YICLOUD_API_HOST", env_host)
    if env_region is not None:
        monkeypatch.setenv("YICLOUD_REGION_ID", env_region)
    calls = []

    def handler(request):
        calls.append(
            (
                request.method,
                str(request.url).split("/job/")[0],
                request.headers["X-OGW-REGION-ID"],
                request.headers.get("Authorization") == "synthetic-saved-token",
            )
        )
        return httpx.Response(200, json={"Code": 0, "Data": {}})

    account = Account.resolve(host=host, region=region)
    assert account.alias == saved_host_profile
    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        client.call("job", "StopJob", {"Project": "p", "ZoneId": "z", "JobId": "j"})
    assert calls == [("POST", expected_host, expected_region, True)]


def test_none_host_without_saved_profile_keeps_environment_and_builtin_defaults(monkeypatch):
    assert Account.resolve(host=None).host == "https://gate.yicloud.com"
    monkeypatch.setenv("YICLOUD_API_HOST", "")
    assert Account.resolve(host=None).host == "https://gate.yicloud.com"
    monkeypatch.setenv("YICLOUD_API_HOST", "https://environment.invalid/")
    assert Account.resolve(host=None).host == "https://environment.invalid"
    assert Account.resolve(host="https://flag.invalid").host == "https://flag.invalid"
