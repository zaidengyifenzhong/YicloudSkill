"""Resolve workspace SSH destinations using the console's deployment protocol."""

import re
from dataclasses import replace
from urllib.parse import urlsplit

import httpx

from . import ssh
from .client import YicloudClient
from .errors import ConfigurationError, InputError
from .workflows import resolve

# Only these deployment origins are discovered automatically. Never send API credentials
# to a console, follow its redirects, or execute the downloaded JavaScript.
CONSOLES = {
    "https://gate.yicloud.com.cn": "https://console.yicloud.com.cn",
    "https://gate.yicloud.com": "https://console.yicloud.com",
}


def gateway_from_config(text):
    values = re.findall(r"""\bVITE_SSH_BASE_URL["']?\s*:\s*(["'])([^"'\r\n]+)\1""", text)
    if len(values) != 1:
        raise ConfigurationError("Console SSH gateway is missing or ambiguous; use --ssh-host")
    try:
        url = urlsplit(values[0][1])
        port = url.port
    except ValueError as e:
        raise ConfigurationError("Invalid console SSH gateway; use --ssh-host") from e
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.path not in ("", "/")
        or url.query
        or url.fragment
        or port is not None
    ):
        raise ConfigurationError("Unsupported console SSH gateway; use --ssh-host")
    return ssh.Connection(host=url.hostname).host


def discover_gateway(api_host):
    origin = CONSOLES.get(api_host)
    if not origin:
        raise ConfigurationError("Unknown deployment; provide --ssh-host or register a connection")
    try:
        with httpx.Client(timeout=8, follow_redirects=False) as client:
            with client.stream("GET", origin + "/app.config.js") as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ConfigurationError(
                            "Console configuration is too large; use --ssh-host"
                        )
        return gateway_from_config(body.decode("utf-8"))
    except (httpx.HTTPError, UnicodeError, ValueError) as e:
        raise ConfigurationError("Cannot read console SSH gateway; use --ssh-host") from e


def component(value, label):
    # These are components of a structured gateway username, not arbitrary SSH users.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value):
        raise InputError(f"Missing or unsupported workspace {label}; register its SSH command")
    return value


def workspace_connection(
    data, resource_id, project, zone, *, host, port=2202, shared=False, ssh_user=None, identity=None
):
    if not isinstance(data, dict):
        raise InputError("Invalid workspace response; cannot resolve SSH connection")
    if any(
        data.get(k) != v
        for k, v in (("WorkspaceId", resource_id), ("Project", project), ("ZoneId", zone))
    ):
        raise InputError("Workspace response does not match the requested ID/project/zone")
    if data.get("Phase") != "Running":
        raise InputError("Workspace is not Running; start it and wait before connecting")
    workspace = component(resource_id, "ID")
    namespace = component(project, "project")
    # The SDK omits a definitive share-scope field. RealCreator indicates a shared
    # identity; callers must supply the current user explicitly for shared routing.
    shared_hint = bool(data.get("RealCreator")) or data.get("Scope") == "shared"
    if shared_hint and not shared:
        raise InputError("Shared workspace requires --shared --ssh-user, or a saved connection")
    if shared:
        user = component(ssh_user, "login user")
        quota = component(data.get("QuotaGroup"), "quota group").replace("_", "-")
        username = f"{user}+{workspace}.group-{namespace}-{quota}.{namespace}.ws"
    else:
        if ssh_user is not None:
            raise InputError("--ssh-user requires --shared")
        user = component(data.get("Creator"), "creator")
        username = f"{workspace}.{user}.{namespace}.ws"
    return ssh.Connection(host=host, user=username, port=port, identity=identity or "")


def connection_for(
    account,
    kind,
    resource,
    project,
    zone,
    *,
    by_name=False,
    lookup=None,
    identity=None,
    ssh_host=None,
    ssh_port=None,
    shared=False,
    ssh_user=None,
    forward_agent=None,
):
    if kind != "workspace":
        return ssh.load(account.alias, kind, project, zone, resource)
    if ssh_user is not None and not shared:
        raise InputError("--ssh-user requires --shared")
    if shared and not ssh_user:
        raise InputError("--shared requires the actual platform username via --ssh-user")
    saved = None if by_name else ssh.find(account.alias, kind, project, zone, resource)
    if saved is not None:
        if lookup or ssh_host is not None or ssh_port is not None or shared:
            raise InputError(
                "Saved connection takes precedence; use --by-name for platform discovery "
                "or remove the local registration before using discovery options"
            )
        if identity is not None:
            saved = replace(saved, identity=identity)
        return agent_forwarding(saved, forward_agent)
    by_name = by_name or not resource.startswith("ws-")
    lookup = dict(lookup or {})
    if by_name:
        lookup.setdefault("Name", resource)
    # Validate explicit connection options before any network access.
    if ssh_host is not None:
        ssh.Connection(host=ssh_host, port=ssh_port, identity=identity or "")
    with YicloudClient(account) as client:
        try:
            rid = resolve(client, kind, resource, project, zone, by_name, lookup=lookup)
        except InputError as e:
            if (
                by_name
                and "Creator" not in lookup
                and str(e).startswith("Name lookup found 0 matches")
            ):
                raise InputError(
                    "Name lookup found 0 matches; this deployment may require "
                    "--lookup-set 'Creator=\"PLATFORM_USER\"'. Use the platform username "
                    "or connect by WorkspaceId."
                ) from e
            raise
        data = client.call(
            "workspace",
            "GetWorkspace",
            {
                "Project": project,
                "ZoneId": zone,
                "WorkspaceId": rid,
            },
        ).data
    # Check response/scope/state even if deployment discovery is unavailable.
    connection = workspace_connection(
        data,
        rid,
        project,
        zone,
        host=ssh_host or "placeholder",
        port=2202 if ssh_port is None else ssh_port,
        shared=shared,
        ssh_user=ssh_user,
        identity=identity,
    )
    if ssh_host is None:
        connection = replace(connection, host=discover_gateway(account.host))
    return agent_forwarding(connection, True if forward_agent is None else forward_agent)


def agent_forwarding(connection, enabled):
    if enabled is None:
        return connection
    flags = connection.ssh_flags.replace("A", "") + ("A" if enabled else "")
    return replace(connection, ssh_flags=flags, forward_agent=enabled)
