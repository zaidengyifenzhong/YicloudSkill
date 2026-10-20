import json
import os
import subprocess

import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.config import Account, config_path, read_state, write_state
from yicloud.errors import ConfigurationError, InputError
from yicloud.output import redact
from yicloud.skill_install import install
from yicloud.ssh import Connection, load, run, save, scp_endpoint


def test_atomic_config_and_whole_env_auth(monkeypatch):
    write_state(
        {
            "current": "a",
            "accounts": {"a": {"public_key": "a-pub", "secret_key": "a-secret", "region": "saved"}},
        }
    )
    assert Account.resolve().secret_key == "a-secret"
    monkeypatch.setenv("YICLOUD_PUBLIC_KEY", "env-pub")
    a = Account.resolve()
    assert a.public_key == "env-pub" and a.secret_key == ""
    monkeypatch.setenv("YICLOUD_REGION_ID", "env-region")
    assert Account.resolve(region="flag-region").region == "flag-region"
    assert Account.resolve().region == "env-region"
    assert json.loads(config_path().read_text())["current"] == "a"
    if os.name != "nt":
        assert config_path().stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "command",
    [
        "ssh -o ProxyCommand=evil user@host",
        "ssh user@host touch /tmp/pwn",
        "sh -c evil",
        "ssh -p invalid user@host",
        "ssh -J 'a\nb' user@host",
        "ssh user@host;whoami",
    ],
)
def test_ssh_import_rejects_unhandled_commands(command):
    with pytest.raises(InputError):
        Connection.parse(command)


def test_ssh_preserves_full_user_port_identity_and_args(tmp_path, monkeypatch):
    identity = tmp_path / "private key"
    identity.write_text("synthetic fixture")
    c = Connection.parse(
        "ssh -p 2202 'test.mayj+root.dev.ws@gateway.example'", str(identity), "jump-alias"
    )
    assert c.user == "test.mayj+root.dev.ws"
    calls = []
    monkeypatch.setattr("yicloud.ssh.shutil.which", lambda name: name)

    def invoke(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 17)

    monkeypatch.setattr("yicloud.ssh.subprocess.run", invoke)
    assert run(c, ["printf", "%s", "a b; $(echo bad)"]) == 17
    assert calls[0][0][-1] == "printf %s 'a b; $(echo bad)'"
    assert calls[0][1] == {"check": False, "shell": False}
    assert "stdin" not in calls[0][1]
    source = tmp_path / "file with spaces.txt"
    source.write_text("fixture")
    remote = scp_endpoint("dev:/mnt/a b", "dev", c)
    assert run(c, scp_paths=[str(source), remote]) == 17
    assert "-P" in calls[1][0] and "-p" not in calls[1][0]
    assert calls[1][0][-1].endswith(":/mnt/a b")
    assert str(identity).replace("\\", "\\\\") in c.config("dev")
    assert "StrictHostKeyChecking" not in c.config("dev")


def test_ssh_alias_isolation_and_missing_tool(monkeypatch):
    c = Connection.parse("ssh existing-alias")
    assert c.port is None and c.user == ""
    save("a", "workspace", "p", "z", "w", c)
    assert load("a", "workspace", "p", "z", "w").host == "existing-alias"
    with pytest.raises(ConfigurationError):
        load("b", "workspace", "p", "z", "w")
    monkeypatch.setattr("yicloud.ssh.shutil.which", lambda _: None)
    with pytest.raises(ConfigurationError, match="OpenSSH"):
        run(c)


def test_skill_conflict_install_upgrade_uninstall_keeps_config(tmp_path):
    dest = tmp_path / "skill"
    dest.mkdir()
    (dest / "SKILL.md").write_text("user owned")
    with pytest.raises(ConfigurationError, match="conflict"):
        install("codex", dest)
    assert (dest / "SKILL.md").read_text() == "user owned"
    (dest / "SKILL.md").unlink()
    dest.rmdir()
    write_state({"accounts": {"a": {"token": "fixture"}}})
    install("codex", dest)
    assert (dest / "SKILL.md").is_file()
    assert (dest / "references/diagnostics/api.md").is_file()
    install("codex", dest)
    install("codex", dest, True)
    assert not dest.exists()
    assert read_state()["accounts"]["a"]["token"] == "fixture"


def test_redaction_known_and_returned_secrets():
    value = {
        "Token": "new-secret",
        "Nested": {"PrivateKey": "new-private"},
        "message": "failed fixture-secret",
        "query": [{"name": "AccessKey", "value": "new-access"}],
    }
    hidden = json.dumps(redact(value, ["fixture-secret"]))
    assert not any(
        v in hidden for v in ("new-secret", "new-private", "fixture-secret", "new-access")
    )
    assert redact(value, show=True)["Token"] == "new-secret"


def test_cli_envelopes_stdin_dryrun_and_error_redaction(monkeypatch):
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", "fixture-secret")
    r = CliRunner()
    result = r.invoke(
        main,
        ["--json", "api", "call", "job", "StopJob", "--file", "-", "--dry-run"],
        input='{"Project":"p","JobId":"j"}',
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] and payload["data"]["body"]["JobId"] == "j"
    assert "fixture-secret" not in result.output
    error = r.invoke(
        main,
        ["--json", "api", "call", "job", "StopJob", "--file", "-"],
        input='{"Project":"p","JobId":false}',
    )
    assert error.exit_code == 1
    assert json.loads(error.output)["error"]["kind"] == "input"
    assert (
        r.invoke(
            main, ["--json", "workspace", "ssh", "dev", "--project", "p", "--zone", "z"]
        ).exit_code
        == 1
    )
    assert (
        r.invoke(
            main, ["--json", "job", "logs", "j", "--project", "p", "--zone", "z", "--follow"]
        ).exit_code
        == 1
    )


def test_shortcut_create_and_scope_protection():
    r = CliRunner()
    result = r.invoke(
        main,
        [
            "job",
            "create",
            "--name",
            "test",
            "--project",
            "p",
            "--zone",
            "z",
            "--image",
            "fixture",
            "--command",
            "python train.py",
            "--sku",
            "sku",
            "--sku-scope",
            "public",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)["body"]
    assert payload["TaskSpecs"]["t0"]["SKUId"] == "sku"
    result = r.invoke(
        main,
        [
            "job",
            "stop",
            "j",
            "--project",
            "p",
            "--zone",
            "z",
            "--set",
            'Project="other"',
            "--dry-run",
        ],
    )
    assert result.exit_code == 1


def test_ssh_exec_cli_exit_code(monkeypatch):
    save("environment", "workspace", "p", "z", "dev", Connection("host"))
    seen = []
    monkeypatch.setattr("yicloud.ssh.run", lambda c, command: seen.append(command) or 23)
    result = CliRunner().invoke(
        main,
        [
            "workspace",
            "exec",
            "dev",
            "--project",
            "p",
            "--zone",
            "z",
            "--",
            "printf",
            "hello world",
        ],
    )
    assert result.exit_code == 23, result.output
    assert seen == [("printf", "hello world")]


def test_schema_help_does_not_hide_secret_field_types():
    result = CliRunner().invoke(main, ["--json", "api", "describe", "iam", "CreateUser"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["schema"]["properties"]["Password"]["type"] == "string"


def test_input_secret_is_redacted_from_echoed_platform_message(monkeypatch):
    import httpx
    from yicloud.client import YicloudClient

    monkeypatch.setattr(
        "yicloud.commands.api.client_for",
        lambda ctx: YicloudClient(
            Account(token="fixture-token"),
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"Code": 999, "Msg": "invalid: user-input-secret"}
                )
            ),
        ),
    )
    data = {
        "Email": "fixture@example.invalid",
        "FirstName": "a",
        "LastName": "b",
        "Password": "user-input-secret",
        "UserName": "u",
        "UserType": "tenantOperator",
    }
    result = CliRunner().invoke(
        main, ["api", "call", "iam", "CreateUser", "--file", "-"], input=json.dumps(data)
    )
    assert result.exit_code == 1
    assert "user-input-secret" not in result.output


def test_uninstall_preserves_user_asset_and_modified_file(tmp_path):
    dest = tmp_path / "skill"
    install("codex", dest)
    (dest / "YICLOUD.md").write_text("user asset")
    entry = dest / "SKILL.md"
    entry.write_text("local edits")
    with pytest.raises(ConfigurationError, match="local edits"):
        install("codex", dest)
    install("codex", dest, True)
    assert entry.read_text() == "local edits"
    assert (dest / "YICLOUD.md").read_text() == "user asset"


def test_windows_ssh_import_preserves_backslashes_and_spaces():
    from yicloud.ssh import split_command

    assert split_command(
        r'ssh -i "C:\Users\Example User\.ssh\id_ed25519" -p 2202 user@host', windows=True
    ) == ["ssh", "-i", r"C:\Users\Example User\.ssh\id_ed25519", "-p", "2202", "user@host"]


def test_cli_unicode_json_under_legacy_pipe_encoding(tmp_path):
    import sys

    env = dict(os.environ, PYTHONIOENCODING="cp1252", YICLOUD_CONFIG=str(tmp_path / "state.json"))
    result = subprocess.run(
        [sys.executable, "-m", "yicloud", "--json", "api", "describe", "job", "CreateJob"],
        env=env,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert json.loads(result.stdout.decode("utf-8"))["ok"]


def test_platform_ssh_command_combined_flags_roundtrip():
    c = Connection.parse("ssh -CAXY ws-example.fixture.dev.ws@gateway.example -p 2202")
    assert c.ssh_flags == "CAXY"
    assert c.port == 2202 and c.user == "ws-example.fixture.dev.ws"
    assert c.options()[:4] == ["-C", "-A", "-X", "-Y"]
    assert c.options(scp=True)[:2] == ["-C", "-A"]
    assert "-X" not in c.options(scp=True) and "-Y" not in c.options(scp=True)
    config = c.config("fixture")
    assert "Compression yes" in config and "ForwardAgent yes" in config
    assert "ForwardX11 yes" in config and "ForwardX11Trusted yes" in config
    separate = Connection.parse("ssh -Y -C -A -X gateway.example")
    assert separate.ssh_flags == "CAXY"
    with pytest.raises(InputError):
        Connection.parse("ssh -CAXYZ user@gateway.example")
    with pytest.raises(InputError):
        Connection("gateway.example", ssh_flags="-oProxyCommand=bad")


def test_platform_ssh_flags_cli_saved_with_scope():
    result = CliRunner().invoke(
        main,
        [
            "--json",
            "workspace",
            "connection",
            "set",
            "fixture",
            "--project",
            "fixture-project",
            "--zone",
            "fixture-zone",
            "--ssh-command",
            "ssh -CAXY ws-example.fixture.dev.ws@gateway.example -p 2202",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (
        load("environment", "workspace", "fixture-project", "fixture-zone", "fixture").ssh_flags
        == "CAXY"
    )


def test_scope_override_rejected_before_name_lookup(monkeypatch):
    def no_client(_):
        pytest.fail("Invalid resource scope must be rejected before creating a client")

    monkeypatch.setattr("yicloud.commands.workloads.client_for", no_client)
    result = CliRunner().invoke(
        main,
        [
            "ray",
            "stop",
            "name",
            "--by-name",
            "--project",
            "p",
            "--zone",
            "z",
            "--set",
            'Project="other"',
        ],
    )
    assert result.exit_code == 1 and "cannot override" in result.output


def test_all_skill_targets_are_preflighted_before_any_upgrade(tmp_path, monkeypatch):
    import yicloud.skill_install as installer

    package = tmp_path / "package"
    source = package / "skill"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("version A")
    codex, claude = tmp_path / "codex", tmp_path / "claude"
    monkeypatch.setattr(installer, "files", lambda _: package)
    monkeypatch.setattr(installer, "targets", lambda *args: [codex, claude])
    install("all")
    original_manifest = (codex / installer.MARKER).read_bytes()
    (source / "SKILL.md").write_text("version B")
    (claude / "SKILL.md").write_text("user edits")
    with pytest.raises(ConfigurationError, match="local edits"):
        install("all")
    assert (codex / "SKILL.md").read_text() == "version A"
    assert (codex / installer.MARKER).read_bytes() == original_manifest
    assert (claude / "SKILL.md").read_text() == "user edits"


@pytest.mark.parametrize("json_output", [False, True])
def test_interrupted_write_does_not_claim_remote_resource_is_unchanged(monkeypatch, json_output):
    import httpx
    from yicloud.client import YicloudClient

    received = []

    def handler(request):
        received.append(request.method)
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        "yicloud.commands.api.client_for",
        lambda _: YicloudClient(Account(token="fixture"), transport=httpx.MockTransport(handler)),
    )
    result = CliRunner().invoke(
        main,
        (["--json"] if json_output else [])
        + [
            "api",
            "call",
            "workspace",
            "CreateWorkspace",
            "--file",
            "tests/fixtures/requests/workspace.json",
        ],
    )
    assert received == ["POST"] and result.exit_code == 130
    assert "remote writes may have completed" in result.output
    assert "remote workload is unchanged" not in result.output
    if json_output:
        payload = json.loads(result.output)
        assert not payload["ok"] and payload["error"]["kind"] == "interrupted"
        assert payload["error"]["outcome_unknown"] is True
