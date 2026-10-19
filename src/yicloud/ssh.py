import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import read_state, write_state
from .errors import ConfigurationError, InputError


def split_command(command, windows=False):
    # Windows native paths use literal backslashes; POSIX shlex would consume them.
    args = shlex.split(command, posix=not windows)
    if windows:
        args = [
            arg[1:-1] if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in "\"'" else arg
            for arg in args
        ]
    return args


def safe(value, label):
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("-")
        or any(c in value for c in "\r\n\x00")
    ):
        raise InputError(f"Invalid SSH {label}")
    return value


@dataclass
class Connection:
    host: str
    user: str = ""
    port: int | None = None
    identity: str = ""
    proxy_jump: str = ""
    ssh_flags: str = ""

    def __post_init__(self):
        for field in ("host", "user", "identity", "proxy_jump", "ssh_flags"):
            if not isinstance(getattr(self, field), str):
                raise InputError(f"SSH {field} must be a string")
        if not isinstance(self.ssh_flags, str) or any(
            flag not in "CAXY" for flag in self.ssh_flags
        ):
            raise InputError("Unsupported SSH flags; supported: C A X Y")
        self.ssh_flags = "".join(flag for flag in "CAXY" if flag in self.ssh_flags)
        safe(self.host, "host")
        if not re.fullmatch(r"[A-Za-z0-9_.:\[\]-]+", self.host):
            raise InputError("Invalid SSH host or alias")
        if self.user:
            safe(self.user, "user")
            if not re.fullmatch(r"[A-Za-z0-9_.+@=-]+", self.user):
                raise InputError("Invalid SSH user")
        if self.port is not None and (type(self.port) is not int or not 1 <= self.port <= 65535):
            raise InputError("SSH port must be an integer in 1..65535")
        if self.identity:
            safe(self.identity, "identity path")
            self.identity = str(Path(self.identity).expanduser())
        if self.proxy_jump:
            safe(self.proxy_jump, "ProxyJump")
            if not re.fullmatch(r"[A-Za-z0-9_.+@=,:\[\]-]+", self.proxy_jump):
                raise InputError("Invalid ProxyJump")

    @classmethod
    def parse(cls, command, identity=None, proxy_jump=None):
        try:
            args = split_command(command, windows=os.name == "nt")
        except ValueError as e:
            raise InputError("Invalid SSH command quoting") from e
        if not args or args.pop(0) != "ssh":
            raise InputError("Expected 'ssh [supported options] user@host'")
        values = {}
        target = None
        while args:
            arg = args.pop(0)
            if arg in ("-p", "-i", "-l", "-J"):
                if not args:
                    raise InputError(f"Missing value for {arg}")
                key = {"-p": "port", "-i": "identity", "-l": "user", "-J": "proxy_jump"}[arg]
                if key in values:
                    raise InputError(f"Repeated SSH option {arg}")
                value = args.pop(0)
                try:
                    values[key] = int(value) if key == "port" else value
                except ValueError as e:
                    raise InputError("SSH port must be an integer") from e
            elif arg.startswith("-") and len(arg) > 1 and all(flag in "CAXY" for flag in arg[1:]):
                values["ssh_flags"] = values.get("ssh_flags", "") + arg[1:]
            elif arg.startswith("-") or target is not None:
                raise InputError(
                    f"Unsupported SSH argument: {arg}; supported: -p -i -l -J -C -A -X -Y"
                )
            else:
                target = arg
        if not target:
            raise InputError("Missing SSH host")
        if "@" in target:
            user, target = target.rsplit("@", 1)
            if "user" in values:
                raise InputError("Specify SSH user only once")
            values["user"] = user
        if identity is not None:
            values["identity"] = identity
        if proxy_jump is not None:
            values["proxy_jump"] = proxy_jump
        return cls(host=target, **values)

    def options(self, scp=False):
        result = []
        for flag in self.ssh_flags:
            if not scp or flag in "CA":
                result.append("-" + flag)
        if self.port is not None:
            result += ["-P" if scp else "-p", str(self.port)]
        if self.identity:
            if not Path(self.identity).is_file():
                raise ConfigurationError(
                    f"SSH identity not found: {self.identity}; set --identity to the matching private key"
                )
            result += ["-i", self.identity, "-o", "IdentitiesOnly=yes"]
        if self.proxy_jump:
            result += ["-J", self.proxy_jump]
        return result

    @property
    def destination(self):
        return (self.user + "@" if self.user else "") + self.host

    def config(self, alias):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", alias) or alias.startswith("-"):
            raise InputError("SSH config alias may contain letters, digits, _, . and -")
        lines = [f"Host {alias}", f"    HostName {self.host}"]
        for key, value in (
            ("User", self.user),
            ("Port", self.port),
            ("IdentityFile", self.identity),
            ("ProxyJump", self.proxy_jump),
        ):
            if value:
                escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'    {key} "{escaped}"')
        if "C" in self.ssh_flags:
            lines.append("    Compression yes")
        if "A" in self.ssh_flags:
            lines.append("    ForwardAgent yes")
        if "X" in self.ssh_flags or "Y" in self.ssh_flags:
            lines.append("    ForwardX11 yes")
        if "Y" in self.ssh_flags:
            lines.append("    ForwardX11Trusted yes")
        if self.identity:
            lines.append("    IdentitiesOnly yes")
        return "\n".join(lines) + "\n"


def key(account, kind, project, zone, resource):
    return json.dumps([account, kind, project, zone, resource], separators=(",", ":"))


def save(account, kind, project, zone, resource, connection):
    state = read_state()
    state.setdefault("connections", {})[key(account, kind, project, zone, resource)] = asdict(
        connection
    )
    write_state(state)


def load(account, kind, project, zone, resource):
    value = read_state().get("connections", {}).get(key(account, kind, project, zone, resource))
    if value is None:
        raise ConfigurationError(
            "No SSH connection for this account/project/zone/resource; use connection set with the platform-provided SSH command"
        )
    return stored_connection(value)


def run(connection, command=(), *, scp_paths=None, recursive=False):
    tool = "scp" if scp_paths else "ssh"
    binary = shutil.which(tool)
    if not binary:
        raise ConfigurationError(f"{tool} not found; install the OpenSSH client and add it to PATH")
    args = [binary] + connection.options(scp=bool(scp_paths))
    if recursive:
        if not scp_paths:
            raise InputError("Recursive transfer requires scp paths")
        args.append("-r")
    if scp_paths:
        args += ["--", *scp_paths]
    else:
        args += ["--", connection.destination]
        if command:
            args += [shlex.join(command)]
    # Inherit stdin/stdout/stderr for interactive use and preserve the remote process exit status.
    try:
        code = subprocess.run(args, check=False, shell=False).returncode
    except OSError as e:
        raise ConfigurationError(f"Unable to launch {tool}") from e
    return code if code >= 0 else 128 - code


def scp_endpoint(value, resource, connection):
    prefix = resource + ":"
    if value.startswith(prefix):
        path = value[len(prefix) :]
        safe(path, "remote path")
        return connection.destination + ":" + path
    path = Path(value).expanduser()
    # Absolute local paths keep ':' and leading '-' from becoming scp options or remote operands.
    return str(path.absolute())


def connections(account, kind, project=None, zone=None):
    rows = []
    for encoded, value in read_state().get("connections", {}).items():
        try:
            parts = json.loads(encoded)
            if (
                not isinstance(parts, list)
                or len(parts) != 5
                or not all(isinstance(v, str) for v in parts)
            ):
                raise ValueError()
            owner, workload, p, z, resource = parts
        except (TypeError, ValueError) as e:
            raise ConfigurationError("Invalid local connection key") from e
        if owner != account or workload != kind:
            continue
        if project is not None and p != project or zone is not None and z != zone:
            continue
        rows.append(
            dict(
                account=owner,
                kind=workload,
                project=p,
                zone=z,
                resource=resource,
                connection=asdict(stored_connection(value)),
            )
        )
    return sorted(rows, key=lambda r: (r["project"], r["zone"], r["resource"]))


def remove(account, kind, project, zone, resource):
    state = read_state()
    identity = key(account, kind, project, zone, resource)
    if identity not in state.get("connections", {}):
        raise ConfigurationError("No local connection at this account/project/zone/resource")
    del state["connections"][identity]
    write_state(state)


def stored_connection(value):
    try:
        if not isinstance(value, dict):
            raise TypeError()
        return Connection(**value)
    except (TypeError, ValueError, InputError) as e:
        raise ConfigurationError(
            "Invalid saved SSH connection; register it again with connection set"
        ) from e
