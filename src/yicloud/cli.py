import json
import sys
from dataclasses import asdict
from pathlib import Path

import click

from . import ssh
from .catalog import catalog, operation, request_schema
from .client import YicloudClient
from .config import Account, read_state, write_state
from .errors import ConfigurationError, InputError, YicloudError
from .output import redact, secret_values
from .skill_install import install
from .workflows import WORKLOADS, follow_logs, log_params, paginated, resolve, scoped_params, wait


class Root(click.Group):
    def main(self, *args, **kwargs):
        standalone = kwargs.pop("standalone_mode", True)
        self.active_context = None
        # JSON and Chinese API descriptions use UTF-8 even when Windows redirects stdout.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8")
                except (OSError, ValueError):
                    pass
        try:
            code = super().main(*args, standalone_mode=False, **kwargs)
        except (YicloudError, OSError, ValueError, click.ClickException) as e:
            ctx = self.active_context
            opts = ctx.obj if ctx else {}
            if isinstance(e, YicloudError):
                err = e
            elif isinstance(e, click.ClickException):
                err = InputError(e.format_message())
            else:
                err = ConfigurationError("Local configuration, JSON input or file operation failed")
            payload = {"ok": False, "error": err.as_dict()}
            click.echo(
                json.dumps(redact(payload, (opts or {}).get("secrets", ())), ensure_ascii=False),
                err=True,
            )
            if standalone:
                raise SystemExit(1) from e
            raise err from e
        except (KeyboardInterrupt, click.Abort):
            click.echo("Local operation interrupted; remote workload is unchanged", err=True)
            if standalone:
                raise SystemExit(130) from None
            raise
        else:
            if standalone:
                raise SystemExit(code if isinstance(code, int) else 0)
            return code


@click.group(cls=Root)
@click.option("--account", "alias", help="Account alias; affects only this invocation.")
@click.option("--host", help="HTTPS API origin.")
@click.option("--region", help="Region ID.")
@click.option("--json", "json_output", is_flag=True, help="Fixed JSON envelope.")
@click.option("--show-secrets", is_flag=True, help="Explicitly reveal newly returned API secrets.")
@click.version_option("0.1.0")
@click.pass_context
def main(ctx, alias, host, region, json_output, show_secrets):
    """Yicloud CLI. API fields are case sensitive; all capabilities are offline verified only."""
    ctx.obj = dict(
        alias=alias, host=host, region=region, json=json_output, show=show_secrets, secrets=[]
    )
    ctx.command.active_context = ctx


def account_for(ctx):
    a = Account.resolve(ctx.obj["alias"], ctx.obj["host"], ctx.obj["region"])
    ctx.obj["secrets"].extend([a.token, a.public_key, a.secret_key])
    return a


def client_for(ctx):
    return YicloudClient(account_for(ctx))


def emit(ctx, data, service=None, action=None, request_id=None, schema=False):
    data = redact(data, ctx.obj.get("secrets", ()), show=ctx.obj["show"] or schema)
    if ctx.obj["json"]:
        data = {
            "ok": True,
            "data": data,
            "meta": {"service": service, "action": action, "request_id": request_id},
        }
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


def emit_result(ctx, result, service, action):
    emit(ctx, result.data, service, action, result.request_id)


def read_json(file):
    if file is None:
        return {}
    try:
        with click.open_file(file, "r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError) as e:
        raise InputError("Cannot read request JSON; provide a valid UTF-8 object") from e
    if not isinstance(value, dict):
        raise InputError("Request must be a JSON object")
    ctx = click.get_current_context(silent=True)
    if ctx and ctx.obj is not None:
        ctx.obj["secrets"].extend(secret_values(value))
    return value


def assignments(values):
    result = {}
    for value in values:
        key, sep, text = value.partition("=")
        if not sep or not key or key in result:
            raise InputError("Use unique --set FIELD=JSON entries")
        try:
            result[key] = json.loads(text)
        except ValueError as e:
            raise InputError(
                "--set requires a JSON value, e.g. --set 'Limit=20' or --set 'SKUType=\"gpu\"'"
            ) from e
    ctx = click.get_current_context(silent=True)
    if ctx and ctx.obj is not None:
        ctx.obj["secrets"].extend(secret_values(result))
    return result


@main.group()
def api():
    """Discover and invoke the pinned SDK operation catalog."""


@api.command("list")
@click.option("--service")
@click.pass_context
def api_list(ctx, service):
    rows = [
        {
            k: op[k]
            for k in ("service", "action", "method", "path", "read_only", "response_mode", "status")
        }
        for op in catalog()["operations"]
        if service is None or op["service"] == service
    ]
    if service and not rows:
        raise InputError(f"Unknown service: {service}")
    emit(ctx, rows)


@api.command("describe")
@click.argument("service")
@click.argument("action")
@click.pass_context
def api_describe(ctx, service, action):
    op = operation(service, action)
    emit(
        ctx,
        dict(op, schema=request_schema(op), definitions=catalog()["definitions"][service]),
        schema=True,
    )


@api.command("call")
@click.argument("service")
@click.argument("action")
@click.option("--file", type=str, help="JSON request file, or - for stdin.")
@click.option("--dry-run", is_flag=True)
@click.option("--allow-unknown-fields", is_flag=True)
@click.option("--output", type=click.Path(path_type=Path), help="Destination for file responses.")
@click.pass_context
def api_call(ctx, service, action, file, dry_run, allow_unknown_fields, output):
    params = read_json(file)
    with client_for(ctx) as client:
        if dry_run:
            emit(
                ctx,
                client.dry_run(service, action, params, allow_unknown_fields=allow_unknown_fields),
                service,
                action,
            )
        else:
            emit_result(
                ctx,
                client.call(
                    service,
                    action,
                    params,
                    allow_unknown_fields=allow_unknown_fields,
                    output=output,
                ),
                service,
                action,
            )


@main.group()
def account():
    """Local accounts. Credentials are entered without echo, never as command arguments."""


@account.command("add")
@click.argument("alias")
@click.option(
    "--auth", type=click.Choice(["token", "hmac", "service"]), default="hmac", show_default=True
)
@click.option("--host", default="https://gate.yicloud.com", show_default=True)
@click.option("--region", default="cn-shanghai", show_default=True)
@click.pass_context
def account_add(ctx, alias, auth, host, region):
    state = read_state()
    if alias in state["accounts"]:
        raise ConfigurationError("Account already exists; remove it explicitly before replacing")
    a = Account(alias=alias, host=host, region=region)
    if auth == "token":
        a.token = click.prompt("Authorization token (include scheme if required)", hide_input=True)
    else:
        a.public_key = click.prompt("Public key", hide_input=True)
        a.secret_key = click.prompt("Secret key", hide_input=True)
        a.service_account = auth == "service"
    values = asdict(a)
    values.pop("alias")
    state["accounts"][alias] = values
    state.setdefault("current", alias)
    write_state(state)
    emit(ctx, {"account": alias, "saved": True})


@account.command("list")
@click.pass_context
def account_list(ctx):
    state = read_state()
    emit(
        ctx,
        [
            {
                "alias": name,
                "host": v.get("host"),
                "region": v.get("region"),
                "current": name == state.get("current"),
                "auth": "token"
                if v.get("token")
                else "service"
                if v.get("service_account")
                else "hmac",
            }
            for name, v in state["accounts"].items()
        ],
    )


@account.command("current")
@click.pass_context
def account_current(ctx):
    a = account_for(ctx)
    emit(ctx, {"alias": a.alias, "host": a.host, "region": a.region})


@account.command("use")
@click.argument("alias")
@click.pass_context
def account_use(ctx, alias):
    state = read_state()
    if alias not in state["accounts"]:
        raise ConfigurationError(f"Unknown account: {alias}")
    state["current"] = alias
    write_state(state)
    emit(ctx, {"current": alias})


@account.command("remove")
@click.argument("alias")
@click.pass_context
def account_remove(ctx, alias):
    state = read_state()
    if alias not in state["accounts"]:
        raise ConfigurationError(f"Unknown account: {alias}")
    del state["accounts"][alias]
    if state.get("current") == alias:
        state.pop("current")
    write_state(state)
    emit(ctx, {"removed": alias, "connections_preserved": True})


@account.command("check")
@click.pass_context
def account_check(ctx):
    with client_for(ctx) as client:
        emit_result(ctx, client.call("mc", "ListZones"), "mc", "ListZones")


@main.group()
def skill():
    """Install or uninstall this package's matching agent skill."""


def skill_command(uninstall):
    @click.command("uninstall" if uninstall else "install")
    @click.option(
        "--target", type=click.Choice(["codex", "claude", "all"]), default="all", show_default=True
    )
    @click.option(
        "--path",
        type=click.Path(path_type=Path),
        help="Exact skill directory; use with one target.",
    )
    @click.pass_context
    def command(ctx, target, path):
        emit(
            ctx,
            {
                "paths": install(target, path, uninstall),
                "action": "uninstall" if uninstall else "install",
            },
        )

    return command


skill.add_command(skill_command(False))
skill.add_command(skill_command(True))


def query_command(service, action, name):
    @click.command(name)
    @click.option("--file", help="Request JSON; mutually exclusive with flags.")
    @click.option("--project")
    @click.option("--zone")
    @click.option("--set", "settings", multiple=True, help="Official field as FIELD=JSON.")
    @click.option("--all", "all_pages", is_flag=True, help="Read all pages.")
    @click.pass_context
    def command(ctx, file, project, zone, settings, all_pages):
        if file and (project or zone or settings):
            raise InputError("--file and field flags are mutually exclusive")
        params = read_json(file) if file else scoped_params(service, action, project, zone)
        params.update(assignments(settings))
        with client_for(ctx) as client:
            emit_result(ctx, paginated(client, service, action, params, all_pages), service, action)

    return command


resources = click.Group(
    "resources", help="Discover current capacity; quota does not guarantee free nodes."
)
for name, action in {
    "zones": "ListZones",
    "skus": "ListSKUs",
    "quota-groups": "ListQuotaGroups",
    "nodes": "ListNodes",
    "available": "ListQuotaGroupResourcePoolSharedNodes",
}.items():
    resources.add_command(query_command("mc", action, name))
resources.add_command(query_command("workspace", "GetPredict", "predict"))
main.add_command(resources)
project_group = click.Group("project", help="Projects and quota.")
for name, action in {
    "list": "ListProjects",
    "status": "GetProject",
    "quota": "GetProjectQuota",
    "quota-limit": "GetProjectQuotaLimit",
}.items():
    project_group.add_command(query_command("mc", action, name))
main.add_command(project_group)


def create_command(kind):
    @click.command("create")
    @click.option("--file", help="Full request JSON; exclusive with shortcut flags.")
    @click.option("--name")
    @click.option("--project")
    @click.option("--zone")
    @click.option("--image")
    @click.option("--command", "entrypoint", help="Container shell command (training only).")
    @click.option("--sku")
    @click.option("--sku-scope", type=click.Choice(["public", "tenant", "project"]))
    @click.option("--quota-group")
    @click.option("--cpu")
    @click.option("--memory")
    @click.option("--gpu")
    @click.option("--dry-run", is_flag=True)
    @click.pass_context
    def command(
        ctx,
        file,
        name,
        project,
        zone,
        image,
        entrypoint,
        sku,
        sku_scope,
        quota_group,
        cpu,
        memory,
        gpu,
        dry_run,
    ):
        if file:
            if any(
                v is not None
                for v in (
                    name,
                    project,
                    zone,
                    image,
                    entrypoint,
                    sku,
                    sku_scope,
                    quota_group,
                    cpu,
                    memory,
                    gpu,
                )
            ):
                raise InputError("--file and shortcut flags are mutually exclusive")
            params = read_json(file)
        else:
            if kind not in ("workspace", "job"):
                raise InputError("Ray and serving creation require --file")
            if not all((name, project, zone, image)):
                raise InputError("Shortcut requires --name --project --zone --image")
            if sku:
                if not sku_scope or any((quota_group, cpu, memory, gpu)):
                    raise InputError(
                        "SKU mode requires --sku-scope and excludes quota-group/cpu/memory/gpu"
                    )
            elif not all((quota_group, cpu, memory)) or sku_scope:
                raise InputError(
                    "Quota mode requires --quota-group --cpu --memory; otherwise use --sku and --sku-scope"
                )
            params = {"Name": name, "Project": project, "ZoneId": zone}
            spec = {
                k: v
                for k, v in {"Image": image, "CPU": cpu, "Memory": memory, "GPU": gpu}.items()
                if v is not None
            }
            if sku:
                spec["SkuId" if kind == "workspace" else "SKUId"] = sku
                if kind == "workspace":
                    params.update(SkuPublic=sku_scope == "public", SkuPrivate=sku_scope != "public")
                    if sku_scope != "public":
                        params["SkuTenant" if sku_scope == "tenant" else "SkuProject"] = True
                else:
                    params.update(SKUPublic=sku_scope == "public", SKUPrivate=sku_scope != "public")
                    if sku_scope != "public":
                        params[
                            "SKUPrivateTenant" if sku_scope == "tenant" else "SKUPrivateProject"
                        ] = True
            if quota_group:
                params["QuotaGroup"] = quota_group
            if kind == "job":
                if not entrypoint:
                    raise InputError("Training shortcut requires --command")
                spec.update(Command=["sh", "-lc", entrypoint], Env={}, Replicas=1)
                params["TaskSpecs"] = {"t0": spec}
            else:
                if entrypoint:
                    raise InputError(
                        "Workspace API has no creation Command field; use workspace exec after startup"
                    )
                params.update(spec)
                params["SystemDisk"] = {"Name": name + "-system", "Storage": "50Gi"}
        w = WORKLOADS[kind]
        with client_for(ctx) as client:
            if dry_run:
                emit(
                    ctx,
                    client.dry_run(w["service"], w["create"], params),
                    w["service"],
                    w["create"],
                )
            else:
                emit_result(
                    ctx, client.call(w["service"], w["create"], params), w["service"], w["create"]
                )

    return command


def workload_command(kind, verb):
    w = WORKLOADS[kind]
    action = w["status"] if verb == "wait" else w[verb]

    @click.command(verb)
    @click.argument("resource")
    @click.option("--project", required=True)
    @click.option(
        "--zone", required=True, help="Explicit lookup scope; sent only if API accepts it."
    )
    @click.option(
        "--by-name", is_flag=True, help="Resolve an exact display name within project and zone."
    )
    @click.option("--file", help="Additional official fields (workers/precheck/etc.).")
    @click.option(
        "--set",
        "settings",
        multiple=True,
        help="Additional FIELD=JSON; cannot override scope or ID.",
    )
    @click.option("--dry-run", is_flag=True)
    @click.option("--timeout", type=click.FloatRange(min=0), default=1800, show_default=True)
    @click.option(
        "--interval",
        type=click.FloatRange(min=0.1),
        default=None,
        help="Wait: 5 seconds; follow: 3 seconds.",
    )
    @click.option("--follow", is_flag=True, help="Poll historical logs; incompatible with --json.")
    @click.option("--start", type=int, help="Unix nanoseconds, inclusive.")
    @click.option("--end", type=int, help="Unix nanoseconds.")
    @click.option("--limit", type=click.IntRange(1, 10000), default=200)
    @click.option("--instance", help="Replica filter for logs.")
    @click.option("--replicas", type=click.IntRange(min=0), help="Desired serving replica count.")
    @click.pass_context
    def command(
        ctx,
        resource,
        project,
        zone,
        by_name,
        file,
        settings,
        dry_run,
        timeout,
        interval,
        follow,
        start,
        end,
        limit,
        instance,
        replicas,
    ):
        if follow and (verb != "logs" or ctx.obj["json"] or dry_run or end is not None):
            raise InputError("--follow requires logs without --json, --dry-run or --end")
        extra = read_json(file)
        extra.update(assignments(settings))
        if any(k in extra for k in ("Project", "ZoneId", w["id"], "Resources")):
            raise InputError("Additional fields cannot override explicit scope or resource")
        with client_for(ctx) as client:
            rid = resolve(client, kind, resource, project, zone, by_name)
            params = scoped_params(w["service"], action, project, zone, rid, w["id"])
            if kind == "job" and verb == "delete":
                params = {"Resources": [{"Project": project, "JobId": rid}]}
            params.update(extra)
            if verb == "scale":
                if replicas is None:
                    raise InputError("scale requires --replicas")
                params["Replicas"] = replicas
            if verb == "logs":
                params = log_params(kind, params, start, end, limit, instance)
            if dry_run:
                emit(ctx, client.dry_run(w["service"], action, params), w["service"], action)
            elif verb == "wait":
                emit_result(
                    ctx,
                    wait(client, kind, params, timeout=timeout, interval=interval or 5),
                    w["service"],
                    action,
                )
            elif follow:
                follow_logs(
                    client,
                    kind,
                    params,
                    lambda row: emit(ctx, row, w["service"], action),
                    interval=interval or 3,
                )
            else:
                emit_result(ctx, client.call(w["service"], action, params), w["service"], action)

    return command


def connection_commands(group, kind):
    connection = click.Group(
        "connection", help="Store explicit platform SSH connection information."
    )

    @connection.command("set")
    @click.argument("resource")
    @click.option("--project", required=True)
    @click.option("--zone", required=True)
    @click.option(
        "--ssh-command",
        required=True,
        help="Parsed, never executed. Supports -p -i -l -J and Host aliases.",
    )
    @click.option("--identity")
    @click.option("--proxy-jump")
    @click.pass_context
    def set_connection(ctx, resource, project, zone, ssh_command, identity, proxy_jump):
        a = account_for(ctx)
        c = ssh.Connection.parse(ssh_command, identity, proxy_jump)
        ssh.save(a.alias, kind, project, zone, resource, c)
        emit(ctx, {"resource": resource, "connection": asdict(c)})

    group.add_command(connection)

    def connected(verb):
        @click.command(verb, context_settings={"ignore_unknown_options": verb == "exec"})
        @click.argument("resource")
        @click.option("--project", required=True)
        @click.option("--zone", required=True)
        @click.argument("command", nargs=-1, type=click.UNPROCESSED)
        @click.pass_context
        def command(ctx, resource, project, zone, command):
            if verb != "ssh-config" and ctx.obj["json"]:
                raise InputError("SSH commands cannot use --json; use native process streams")
            if verb != "exec" and command:
                raise InputError("Unexpected trailing command")
            if verb == "exec" and not command:
                raise InputError("exec requires -- COMMAND [ARGS...]")
            a = account_for(ctx)
            c = ssh.load(a.alias, kind, project, zone, resource)
            if verb == "ssh-config":
                if ctx.obj["json"]:
                    emit(ctx, {"config": c.config(resource)})
                else:
                    click.echo(c.config(resource), nl=False)
            else:
                ctx.exit(ssh.run(c, command))

        return command

    for verb in ("ssh", "exec", "ssh-config"):
        group.add_command(connected(verb))

    @group.command("scp")
    @click.argument("source")
    @click.argument("destination")
    @click.option("--project", required=True)
    @click.option("--zone", required=True)
    @click.pass_context
    def scp(ctx, source, destination, project, zone):
        if ctx.obj["json"]:
            raise InputError("scp cannot use --json")

        # Windows drive letters are local paths, never resource aliases.
        def remote(v):
            return ":" in v and not (len(v) >= 3 and v[1] == ":" and v[2] in "\\/")

        endpoints = [v for v in (source, destination) if remote(v)]
        if len(endpoints) != 1:
            raise InputError("Exactly one endpoint must be RESOURCE:/remote/path")
        resource = endpoints[0].split(":", 1)[0]
        a = account_for(ctx)
        c = ssh.load(a.alias, kind, project, zone, resource)
        paths = [ssh.scp_endpoint(v, resource, c) for v in (source, destination)]
        ctx.exit(ssh.run(c, scp_paths=paths))


for kind, w in WORKLOADS.items():
    group = click.Group(kind, help=f"Manage {kind}; use --help on each operation.")
    group.add_command(query_command(w["service"], w["list"], "list"))
    group.add_command(create_command(kind))
    for verb in list(w):
        if verb not in ("service", "id", "list", "create"):
            group.add_command(workload_command(kind, verb))
    group.add_command(workload_command(kind, "wait"))
    if kind in ("workspace", "job"):
        connection_commands(group, kind)
    main.add_command(group)
