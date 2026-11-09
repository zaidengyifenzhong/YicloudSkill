from inspect import signature

import pytest
from click.testing import CliRunner

from yicloud.config import Account


@pytest.fixture
def separated_cli_runner():
    """Capture stdout/stderr independently across supported Click releases."""
    options = {"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}
    return CliRunner(**options)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("YICLOUD_CONFIG", str(tmp_path / "config.json"))
    for key in (
        "YICLOUD_AUTHN_TOKEN",
        "YICLOUD_PUBLIC_KEY",
        "YICLOUD_SECRET_KEY",
        "YICLOUD_IS_SERVICE_ACCOUNT",
        "YICLOUD_API_HOST",
        "YICLOUD_REGION_ID",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def account():
    return Account(public_key="test-public", secret_key="test-secret")
