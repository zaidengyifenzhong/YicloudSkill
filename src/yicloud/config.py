import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .errors import ConfigurationError


def config_path():
    return Path(os.environ.get("YICLOUD_CONFIG", Path.home() / ".config/yicloud/config.json"))


def read_state():
    path = config_path()
    if not path.exists():
        return {"accounts": {}, "connections": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("accounts"), dict)
            or not all(isinstance(v, dict) for v in value["accounts"].values())
            or not isinstance(value.get("connections", {}), dict)
            or ("current" in value and not isinstance(value["current"], str))
        ):
            raise ValueError()
        return value
    except (OSError, ValueError) as e:
        raise ConfigurationError("Invalid account configuration; check YICLOUD_CONFIG") from e


def write_state(state):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".yicloud-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@dataclass
class Account:
    alias: str = "environment"
    host: str = "https://gate.yicloud.com"
    region: str = "cn-shanghai"
    token: str = ""
    public_key: str = ""
    secret_key: str = ""
    service_account: bool = False

    def __post_init__(self):
        if any(
            not isinstance(v, str)
            for v in (
                self.alias,
                self.host,
                self.region,
                self.token,
                self.public_key,
                self.secret_key,
            )
        ) or not isinstance(self.service_account, bool):
            raise ConfigurationError("Account fields have invalid types")
        u = urlsplit(self.host)
        if (
            u.scheme != "https"
            or not u.hostname
            or u.username
            or u.password
            or u.query
            or u.fragment
            or u.path not in ("", "/")
        ):
            raise ConfigurationError("API host must be an HTTPS origin without credentials or path")
        self.host = self.host.rstrip("/")

    @classmethod
    def resolve(cls, alias=None, host=None, region=None):
        state = read_state()
        selected = alias or state.get("current")
        if selected and selected not in state["accounts"]:
            raise ConfigurationError(f"Unknown account: {selected}")
        values = dict(state["accounts"].get(selected, {}))
        auth_keys = (
            "YICLOUD_AUTHN_TOKEN",
            "YICLOUD_PUBLIC_KEY",
            "YICLOUD_SECRET_KEY",
            "YICLOUD_IS_SERVICE_ACCOUNT",
        )
        if any(k in os.environ for k in auth_keys):
            values.update(
                token=os.getenv(auth_keys[0], ""),
                public_key=os.getenv(auth_keys[1], ""),
                secret_key=os.getenv(auth_keys[2], ""),
                service_account=os.getenv(auth_keys[3], "false").lower() in ("true", "1"),
            )
        values["host"] = host or os.getenv("YICLOUD_API_HOST") or values.get("host") or cls.host
        values["region"] = (
            region or os.getenv("YICLOUD_REGION_ID") or values.get("region") or cls.region
        )
        try:
            return cls(alias=selected or "environment", **values)
        except TypeError as e:
            raise ConfigurationError("Account contains unknown configuration fields") from e
