"""SCP operand and CLI contracts; native probes replace SSH and never connect."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.errors import InputError
from yicloud.ssh import Connection, run, scp_endpoint


HOSTS = [
    ("2001:db8::1", "test-user", "test-user@[2001:db8::1]"),
    ("[2001:db8::1]", "test-user", "test-user@[2001:db8::1]"),
    ("2001:db8::1", "", "[2001:db8::1]"),
    ("gateway.example", "test-user", "test-user@gateway.example"),
    ("existing-alias", "", "existing-alias"),
]


@pytest.mark.parametrize("host,user,destination", HOSTS)
def test_scp_host_format_does_not_change_ssh(host, user, destination, monkeypatch):
    connection = Connection(host, user=user)
    assert scp_endpoint("dev:/tmp/a b", "dev", connection) == destination + ":/tmp/a b"
    ssh_destination = (user + "@" if user else "") + host
    assert connection.destination == ssh_destination
    assert f"    HostName {host}\n" in connection.config("dev")
    calls = []
    monkeypatch.setattr("yicloud.ssh.shutil.which", lambda _: "fixture-ssh")
    monkeypatch.setattr(
        "yicloud.ssh.subprocess.run",
        lambda args, **kwargs: calls.append((args, kwargs)) or subprocess.CompletedProcess(args, 0),
    )
    assert run(connection) == 0
    assert calls == [(["fixture-ssh", "--", ssh_destination], {"check": False, "shell": False})]


@pytest.mark.parametrize("kind", ["workspace", "job"])
@pytest.mark.parametrize("direction", ["upload", "download"])
@pytest.mark.parametrize(
    "local",
    [
        "absolute-colon",
        "./file:one",
        "dir/file:one",
        r"dir\file:one",
        r"C:\fixtures\file:one",
        "D:/fixtures/file:one",
        ":fixture",
        ":dir/file",
        "./ordinary",
        "-local-file",
    ],
)
def test_cli_scp_local_paths(tmp_path, monkeypatch, kind, direction, local):
    if local == "absolute-colon":
        local = str(tmp_path / "file:one")
    resolved, invoked = [], []
    connection = Connection("2001:db8::1", user="test-user")
    monkeypatch.setattr("yicloud.commands.connections.scope_for", lambda *a, **kw: ("p", "z"))
    monkeypatch.setattr(
        "yicloud.commands.connections.resolve_connection",
        lambda *a, **kw: resolved.append((a, kw)) or connection,
    )
    monkeypatch.setattr("yicloud.ssh.run", lambda c, **kw: invoked.append((c, kw)) or 37)
    operands = [local, "dev:/tmp/fixture"]
    expected = [str(Path(local).absolute()), "test-user@[2001:db8::1]:/tmp/fixture"]
    if direction == "download":
        operands.reverse()
        expected.reverse()
    result = CliRunner().invoke(main, [kind, "scp", "--recursive", "--", *operands])
    assert result.exit_code == 37, result.output
    assert len(resolved) == 1
    assert resolved[0][0][1:5] == (kind, "dev", "p", "z")
    assert invoked == [(connection, {"scp_paths": expected, "recursive": True})]


@pytest.mark.parametrize("kind", ["workspace", "job"])
@pytest.mark.parametrize(
    "operands",
    [
        ["dev:/tmp/one", "other:/tmp/two"],
        ["./one", "./two"],
        ["./file:one", "dir/file:two"],
        [":one", ":two"],
        [r"C:\fixtures\one", "D:/fixtures/two"],
    ],
)
def test_cli_scp_requires_one_remote_endpoint(monkeypatch, kind, operands):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid endpoints must fail before resolution or process launch")

    monkeypatch.setattr("yicloud.commands.connections.resolve_connection", unexpected)
    monkeypatch.setattr("yicloud.ssh.run", unexpected)
    result = CliRunner().invoke(main, [kind, "scp", *operands])
    assert result.exit_code == 1
    assert "Exactly one endpoint must be RESOURCE:/remote/path" in result.output


@pytest.mark.parametrize("remote", ["dev:", "dev:-bad", "dev:/tmp/a\nb", "dev:/tmp/a\x00b"])
def test_scp_rejects_invalid_remote_paths(remote):
    with pytest.raises(InputError, match="Invalid SSH remote path"):
        scp_endpoint(remote, "dev", Connection("gateway.example"))


def test_scp_passes_shell_characters_as_literal_operands(tmp_path, monkeypatch):
    connection = Connection("2001:db8::1", user="test-user")
    remote = scp_endpoint("dev:/tmp/a b;$(touch marker)", "dev", connection)
    local = scp_endpoint(str(tmp_path / "-local:one"), "dev", connection)
    calls = []
    monkeypatch.setattr("yicloud.ssh.shutil.which", lambda _: "fixture-scp")
    monkeypatch.setattr(
        "yicloud.ssh.subprocess.run",
        lambda args, **kwargs: (
            calls.append((args, kwargs)) or subprocess.CompletedProcess(args, 17)
        ),
    )
    assert run(connection, scp_paths=[local, remote]) == 17
    assert calls == [
        (
            ["fixture-scp", "--", local, "test-user@[2001:db8::1]:/tmp/a b;$(touch marker)"],
            {"check": False, "shell": False},
        )
    ]


@pytest.fixture
def native_scp_directory():
    with tempfile.TemporaryDirectory(prefix="yicloud-scp-contract-") as directory:
        yield Path(directory)


@pytest.mark.skipif(
    os.name == "nt", reason="Native fake SSH uses a POSIX /bin/sh executable; CLI/string tests run"
)
@pytest.mark.parametrize("host,user,destination", HOSTS[:4])
@pytest.mark.parametrize("direction", ["upload", "download"])
@pytest.mark.parametrize("protocol", ["default", "legacy"])
def test_native_scp_parses_remote_host(
    native_scp_directory, host, user, destination, direction, protocol
):
    binary = shutil.which("scp")
    if not binary:
        pytest.skip("Native OpenSSH scp is unavailable; CLI/string contracts run independently")
    if protocol == "legacy":
        probe = subprocess.run(
            [binary, "-O"], capture_output=True, text=True, timeout=10, check=False
        )
        if any(
            message in probe.stderr.lower()
            for message in ("unknown option", "illegal option", "invalid option")
        ):
            pytest.skip("Installed scp rejects -O; default protocol is tested independently")
    fake_ssh = native_scp_directory / "fake-ssh"
    log = native_scp_directory / "ssh-argv"
    fake_ssh.write_text('#!/bin/sh\nprintf \'%s\\0\' "$@" > "$YICLOUD_SCP_TEST_LOG"\nexit 73\n')
    fake_ssh.chmod(0o700)
    local = native_scp_directory / "local-file"
    local.write_text("synthetic SCP fixture")
    connection = Connection(host, user=user)
    remote = scp_endpoint("dev:/tmp/fixture", "dev", connection)
    operands = [str(local), remote] if direction == "upload" else [remote, str(local)]
    result = subprocess.run(
        [binary, *(["-O"] if protocol == "legacy" else []), "-S", str(fake_ssh), "--", *operands],
        env=dict(os.environ, YICLOUD_SCP_TEST_LOG=str(log)),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert log.is_file(), result.stderr
    args = [os.fsdecode(value) for value in log.read_bytes().split(b"\0")[:-1]]
    assert host.strip("[]") in args, args
    if user:
        assert args[args.index("-l") + 1] == user
    else:
        assert "-l" not in args
    assert remote == destination + ":/tmp/fixture"
    assert result.returncode != 0  # The fake SSH exits before opening any connection.
