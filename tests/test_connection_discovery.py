"""Connection discovery contracts; no real accounts or remote processes."""

import json
import shutil
import subprocess

import httpx
import pytest
from click.testing import CliRunner

from yicloud import connection_resolver as resolver
from yicloud.cli import main
from yicloud.client import YicloudClient
from yicloud.config import Account, read_state, write_state
from yicloud.errors import ConfigurationError, InputError
from yicloud.ssh import Connection, save


ROW = dict(
    WorkspaceId="ws-fixture",
    Name="dev",
    Creator="alice",
    Project="p",
    ZoneId="z",
    Phase="Running",
    RealCreator="",
    QuotaGroup="cpu_pool",
)


@pytest.fixture
def discovery(monkeypatch):
    account = Account(alias="a", host="https://gate.yicloud.com.cn", token="fixture-token")
    write_state(
        {
            "accounts": {"a": {"host": account.host, "token": account.token}},
            "current": "a",
            "connections": {},
        }
    )
    calls = []
    rows = [dict(ROW)]
    detail = dict(ROW)

    def handler(request):
        calls.append(request)
        data = (
            {"Items": rows, "Total": len(rows)}
            if request.url.path.endswith("ListWorkspaces")
            else detail
        )
        return httpx.Response(200, json={"Code": 0, "Data": data})

    monkeypatch.setattr(
        resolver,
        "YicloudClient",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(resolver, "discover_gateway", lambda _: "ssh.fixture.example")
    return account, calls, rows, detail


def test_id_discovery_does_not_save_or_forward_x11(discovery):
    account, calls, _, _ = discovery
    before = read_state()
    c = resolver.connection_for(account, "workspace", "ws-fixture", "p", "z")
    assert c.destination == "ws-fixture.alice.p.ws@ssh.fixture.example"
    assert c.port == 2202 and c.ssh_flags == "A"
    assert len(calls) == 1 and calls[0].url.params["WorkspaceId"] == "ws-fixture"
    assert read_state() == before


def test_name_lookup_uses_platform_creator_and_unique_scope(discovery):
    account, calls, _, _ = discovery
    c = resolver.connection_for(account, "workspace", "dev", "p", "z", lookup={"Creator": "alice"})
    assert c.user == "ws-fixture.alice.p.ws"
    assert calls[0].url.params["Creator"] == "alice"
    assert calls[0].url.params["Name"] == "dev"
    assert "Creator" not in calls[1].url.params


@pytest.mark.parametrize("matches", [0, 2])
def test_ambiguous_or_missing_name_never_connects(discovery, matches):
    account, calls, rows, _ = discovery
    rows[:] = [dict(ROW) for _ in range(matches)]
    with pytest.raises(InputError, match=f"{matches} matches"):
        resolver.connection_for(account, "workspace", "dev", "p", "z")
    assert len(calls) == 1


def test_saved_registration_wins_without_network_and_keeps_flags(discovery):
    account, calls, _, _ = discovery
    c = Connection("old.example", user="old", ssh_flags="CX")
    save("a", "workspace", "p", "z", "dev", c)
    assert resolver.connection_for(account, "workspace", "dev", "p", "z") == c
    overridden = resolver.connection_for(account, "workspace", "dev", "p", "z", forward_agent=True)
    assert overridden.ssh_flags == "CAX"
    assert calls == []
    assert resolver.connection_for(
        account, "workspace", "dev", "p", "z", by_name=True
    ).user.startswith("ws-fixture.")


def test_corrupt_registration_does_not_fall_back(discovery):
    account, calls, _, _ = discovery
    state = read_state()
    state["connections"]['["a","workspace","p","z","dev"]'] = None
    write_state(state)
    with pytest.raises(ConfigurationError, match="Invalid saved"):
        resolver.connection_for(account, "workspace", "dev", "p", "z")
    assert not calls


def test_saved_discovery_options_are_not_silently_ignored(discovery):
    account, calls, _, _ = discovery
    save("a", "workspace", "p", "z", "dev", Connection("old.example"))
    with pytest.raises(InputError, match="precedence"):
        resolver.connection_for(account, "workspace", "dev", "p", "z", ssh_host="other.example")
    assert not calls


@pytest.mark.parametrize(
    "change",
    [
        {"WorkspaceId": "ws-other"},
        {"Project": "other"},
        {"ZoneId": "other"},
        {"Creator": None},
        {"Creator": "alice+root"},
        {"Creator": "alice@host"},
        {"Phase": "Stopped"},
        {"Phase": "Future"},
        {"RealCreator": "owner"},
    ],
)
def test_invalid_or_shared_response_is_not_used(discovery, change):
    account, _, _, detail = discovery
    detail.update(change)
    with pytest.raises(InputError):
        resolver.connection_for(account, "workspace", "ws-fixture", "p", "z")


def test_shared_rule_requires_explicit_current_user(discovery):
    account, _, _, detail = discovery
    detail["RealCreator"] = "owner"
    c = resolver.connection_for(
        account,
        "workspace",
        "ws-fixture",
        "p",
        "z",
        shared=True,
        ssh_user="visitor",
        forward_agent=False,
    )
    assert c.user == "visitor+ws-fixture.group-p-cpu-pool.p.ws"
    assert c.ssh_flags == ""


@pytest.mark.parametrize(
    "options",
    [
        {"shared": True},
        {"ssh_user": "alice"},
        {"lookup": {"Project": "other"}},
        {"ssh_host": "host;command"},
    ],
)
def test_invalid_options_rejected_before_network(discovery, options):
    account, calls, _, _ = discovery
    with pytest.raises(InputError):
        resolver.connection_for(account, "workspace", "dev", "p", "z", **options)
    assert not calls


def test_explicit_gateway_and_identity(discovery, tmp_path):
    account, _, _, _ = discovery
    c = resolver.connection_for(
        account,
        "workspace",
        "ws-fixture",
        "p",
        "z",
        ssh_host="explicit.example",
        ssh_port=2222,
        identity=str(tmp_path / "key"),
    )
    assert c.host == "explicit.example" and c.port == 2222
    assert c.identity == str(tmp_path / "key")


@pytest.mark.parametrize("command", ["ssh", "exec", "scp", "ssh-config", "doctor"])
def test_cli_consumers_share_discovery(discovery, monkeypatch, command):
    _, calls, _, _ = discovery
    seen = []
    monkeypatch.setattr("yicloud.ssh.run", lambda c, *a, **kw: seen.append((c, a, kw)) or 37)
    monkeypatch.setattr(
        "yicloud.diagnostics.remote_checks", lambda c, timeout: seen.append((c, (), {})) or []
    )
    args = ["workspace", command]
    args += (
        ["./source", "ws-fixture:/tmp/target", "--recursive"]
        if command == "scp"
        else ["ws-fixture"]
    )
    args += ["--project", "p", "--zone", "z", "--no-forward-agent"]
    if command == "exec":
        args += ["--", "printf", "hello world"]
    if command in ("ssh-config", "doctor"):
        args.insert(0, "--json")
    result = CliRunner().invoke(main, args)
    assert result.exit_code == (37 if command in ("ssh", "exec", "scp") else 0), result.output
    assert len(calls) == 1
    if command == "ssh-config":
        config = json.loads(result.output)["data"]["config"]
        assert "ws-fixture.alice.p.ws" in config and "ForwardAgent no" in config
    else:
        assert seen[0][0].ssh_flags == ""
    if command == "scp":
        assert seen[0][2]["recursive"] is True
        assert seen[0][2]["scp_paths"][1] == "ws-fixture.alice.p.ws@ssh.fixture.example:/tmp/target"
    if command == "exec":
        assert seen[0][1] == (("printf", "hello world"),)


def test_job_keeps_manual_connection_contract(discovery):
    account, calls, _, _ = discovery
    with pytest.raises(ConfigurationError, match="No SSH connection"):
        resolver.connection_for(account, "job", "job-id", "p", "z")
    assert not calls


def test_gateway_parser_reads_data_not_javascript():
    text = 'throw Error("never execute"); window.__APP_CONFIG__={env:{VITE_SSH_BASE_URL:"https://ssh.example/"}};'
    assert resolver.gateway_from_config(text) == "ssh.example"


@pytest.mark.parametrize(
    "text",
    [
        "",
        'VITE_SSH_BASE_URL: "http://ssh.example"',
        'VITE_SSH_BASE_URL: "https://user:password@ssh.example/"',
        'VITE_SSH_BASE_URL: "https://ssh.example/path"',
        'VITE_SSH_BASE_URL: "https://ssh.example/?token=secret"',
        'VITE_SSH_BASE_URL: "https://ssh.example:2222"',
        'VITE_SSH_BASE_URL: "https://one/", VITE_SSH_BASE_URL: "https://two/"',
    ],
)
def test_invalid_gateway_config(text):
    with pytest.raises(ConfigurationError):
        resolver.gateway_from_config(text)


@pytest.mark.parametrize("mode", ["ok", "redirect", "large", "timeout"])
def test_console_discovery_is_bounded_and_unauthenticated(monkeypatch, mode):
    actual = httpx.Client
    requests = []

    def handler(request):
        requests.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("fixture", request=request)
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "https://elsewhere.example/config"})
        body = b"x" * 65537 if mode == "large" else b'VITE_SSH_BASE_URL: "https://ssh.example/"'
        return httpx.Response(200, content=body)

    monkeypatch.setattr(
        resolver.httpx, "Client", lambda **kw: actual(transport=httpx.MockTransport(handler), **kw)
    )
    if mode == "ok":
        assert resolver.discover_gateway("https://gate.yicloud.com.cn") == "ssh.example"
    else:
        with pytest.raises(ConfigurationError):
            resolver.discover_gateway("https://gate.yicloud.com.cn")
    assert len(requests) == 1
    assert str(requests[0].url) == "https://console.yicloud.com.cn/app.config.js"
    assert not set(requests[0].headers) & {"authorization", "x-ogw-sign", "cookie"}


def test_unknown_deployment_needs_explicit_host():
    with pytest.raises(ConfigurationError, match="Unknown deployment"):
        resolver.discover_gateway("https://tenant.example")


@pytest.mark.parametrize("enabled", [True, False])
def test_explicit_forwarding_overrides_openssh_config(tmp_path, enabled):
    binary = shutil.which("ssh")
    if not binary:
        pytest.skip("OpenSSH is not installed")
    config = tmp_path / "ssh_config"
    config.write_text("Host *\n    ForwardAgent " + ("no" if enabled else "yes") + "\n")
    c = resolver.agent_forwarding(Connection("fixture.example", ssh_flags="A"), enabled)
    result = subprocess.run(
        [binary, "-F", str(config), *c.options(), "-G", "--", c.destination],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    expected = "yes" if enabled else "no"
    assert f"forwardagent {expected}\n" in result.stdout.lower()
    assert f"ForwardAgent {expected}" in c.config("fixture")
    assert f"ForwardAgent={expected}" in c.options(scp=True)


@pytest.mark.parametrize("value", ["yes", 1, [], {}])
def test_stored_forwarding_type_is_validated(value):
    with pytest.raises(InputError, match="forward_agent"):
        Connection("fixture.example", forward_agent=value)


def test_invalid_gateway_port_is_controlled():
    with pytest.raises(ConfigurationError, match="Invalid console"):
        resolver.gateway_from_config('VITE_SSH_BASE_URL: "https://ssh.example:bad/"')
