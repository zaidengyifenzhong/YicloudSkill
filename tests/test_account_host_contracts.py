"""Host parsing must fail locally while retaining valid HTTPS origin routing."""

import json

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.config import Account
from yicloud.errors import ConfigurationError


@pytest.mark.parametrize(
    "host",
    [
        "https://example.invalid:abc",
        "https://example.invalid:-1",
        "https://example.invalid:65536",
        "https://example.invalid:１２",
        "https://[::1",
        "https://example.invalid:443\n",
        "https://example.invalid:\t443",
        "https://example.invalid:443\r",
        "\x00https://example.invalid:443",
        "https://example.\x1finvalid:443",
        "https://example.invalid:443\x7f",
        "https://\u200b.invalid",
        "https://example.invalid?",
        "https://example.invalid#",
        "https://@example.invalid",
        " https://example.invalid",
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
        ("https://example.invalid:443/", "https://example.invalid:443", 443),
        ("https://example.invalid:8443", "https://example.invalid:8443", 8443),
        ("https://example.invalid:65535", "https://example.invalid:65535", 65535),
        ("https://example.invalid:0", "https://example.invalid:0", 0),
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
