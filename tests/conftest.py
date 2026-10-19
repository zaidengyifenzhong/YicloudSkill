import pytest

from yicloud.config import Account


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
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
