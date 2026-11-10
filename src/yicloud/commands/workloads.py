"""Workload commands with options specific to each operation."""

import time

import click
from click.core import ParameterSource

from ..catalog import operation, request_schema
from ..cli_support import assignments, client_for, emit, emit_result, read_json, scope_for
from ..creation import create_params
from ..errors import InputError
from ..time_input import duration_ns, timestamp_ns
from ..workflows import (
    WORKLOADS,
    follow_logs,
    resolve,
    validate_polling,
    validate_workload_extra,
    wait,
    wait_deleted,
    verify_workload_scope,
    workload_params,
    workload_list_params,
)
from .connections import connection_commands
from .discovery import query_command


def resource_options(command):
    command = click.option(
        "--lookup-set",
        "lookup_settings",
        multiple=True,
        help="List filter FIELD=JSON for --by-name only; not sent to the final operation.",
    )(command)
    command = click.option(
        "--dry-run", is_flag=True, help="Preview request; name lookup may read the API."
    )(command)
    command = click.option(
        "--by-name", is_flag=True, help="Resolve an exact name within project and zone."
    )(command)
    command = click.option(
        "--zone", help="Lookup and write-verification scope; sent only if the API accepts it."
    )(command)
    command = click.option("--project")(command)
    return click.argument("resource")(command)


def extra_options(kind, verb, command):
    w = WORKLOADS[kind]
    action = w["status"] if verb == "wait" else w[verb]
    fields = request_schema(operation(w["service"], action))["properties"]
    managed = {"Project", "ZoneId", w["id"], "Resources"}
    if verb == "logs":
        managed.update(
            {"Start", "End", "StartTime", "EndTime", "Method", "Limit", "Replicas", "Direction"}
        )
    if verb == "scale":
        managed.add("Replicas")
    if fields.keys() - managed:
        command = click.option(
            "--set",
            "settings",
            multiple=True,
            help="Additional FIELD=JSON; cannot override scope or ID.",
        )(command)
        command = click.option("--extra-file", help="Additional request fields as JSON.")(command)
    return command


def create_command(kind):
    @click.pass_context
    def command(ctx, file, dry_run, **shortcuts):
        if file:
            if any(value is not None for value in shortcuts.values()):
                raise InputError("--file and shortcut flags are mutually exclusive")
            params = read_json(file)
        else:
            shortcuts["project"], shortcuts["zone"] = scope_for(
                ctx, shortcuts.get("project"), shortcuts.get("zone"), required=True
            )
            params = create_params(kind, **shortcuts)
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

    command = click.option("--dry-run", is_flag=True)(command)
    if kind in ("workspace", "job"):
        shortcut_help = {
            "image": "Full container image reference, including tag or digest.",
            "sku": "SKU ID; use with --sku-scope instead of quota resource flags.",
            "quota-group": "Quota-group name; use with CPU and memory quantities.",
            "cpu": "CPU quantity, e.g. 4 or 500m (quota mode).",
            "memory": "Memory quantity with units, e.g. 8Gi or 512Mi (quota mode).",
            "gpu": "GPU count; use 0 for a CPU-only quota workspace.",
        }
        for name in reversed(
            ("name", "project", "zone", "image", "sku", "quota-group", "cpu", "memory", "gpu")
        ):
            help_text = (
                "GPU count; defaults to 0 for quota-mode job shortcuts."
                if name == "gpu" and kind == "job"
                else shortcut_help.get(name)
            )
            command = click.option(f"--{name}", help=help_text)(command)
        command = click.option(
            "--sku-scope",
            type=click.Choice(["public", "tenant", "project"]),
            help="SKU visibility scope; required with --sku.",
        )(command)
        if kind == "job":
            command = click.option(
                "--use-private-machine/--no-use-private-machine",
                default=None,
                help="Explicitly select private-machine scheduling; omitted by default.",
            )(command)
            command = click.option(
                "--qos", help="Platform QoS value, e.g. Guaranteed; omitted by default."
            )(command)
            command = click.option(
                "--priority",
                type=click.IntRange(1, 9),
                help="Scheduling priority; omitted by default so the platform chooses.",
            )(command)
            for duration_option, phase in (
                ("--max-wait-duration", "waiting"),
                ("--max-running-duration", "running"),
            ):
                command = click.option(
                    duration_option,
                    help=f"Task {phase} limit (30s, 15m, 2h, 1d); sent as seconds. Omitted by default.",
                )(command)
            command = click.option(
                "--login-shell",
                is_flag=True,
                default=None,
                help="Use sh -lc instead of sh -c for --command.",
            )(command)
            command = click.option("--command", "entrypoint", help="Container shell command.")(
                command
            )
    command = click.option(
        "--file",
        required=kind in ("ray", "serving"),
        help=(
            "Request JSON file, or - for stdin; exclusive with shortcut flags."
            if kind in ("workspace", "job")
            else "Request JSON file, or - for stdin."
        ),
    )(command)
    label = {
        "workspace": "workspace",
        "job": "training job",
        "ray": "Ray job",
        "serving": "serving deployment",
    }[kind]
    return click.command("create", help=f"Create a {label}.")(command)


def run_operation(
    ctx,
    kind,
    verb,
    resource,
    project,
    zone,
    by_name,
    dry_run,
    lookup_settings=(),
    extra_file=None,
    settings=(),
    replicas=None,
):
    """Preview or execute one operation, checking scope before a write."""
    project, zone = scope_for(ctx, project, zone, required=True)
    w = WORKLOADS[kind]
    action = w[verb]
    extra = read_json(extra_file)
    fields = assignments(settings)
    duplicates = extra.keys() & fields.keys()
    if duplicates:
        raise InputError(
            "Fields supplied by both --extra-file and --set: " + ", ".join(sorted(duplicates))
        )
    extra.update(fields)
    validate_workload_extra(kind, extra)
    with client_for(ctx) as client:
        rid = resolve(
            client, kind, resource, project, zone, by_name, lookup=assignments(lookup_settings)
        )
        params = workload_params(kind, verb, rid, project, zone, extra=extra, replicas=replicas)
        if dry_run:
            emit(ctx, client.dry_run(w["service"], action, params), w["service"], action)
        else:
            if not operation(w["service"], action)["read_only"]:
                client.dry_run(w["service"], action, params)
                verify_workload_scope(client, kind, rid, project, zone)
            emit_result(ctx, client.call(w["service"], action, params), w["service"], action)


def action_command(kind, verb):
    @click.pass_context
    def command(ctx, **options):
        run_operation(ctx, kind, verb, **options)

    return click.command(verb)(resource_options(extra_options(kind, verb, command)))


def wait_command(kind):
    @click.option(
        "--target",
        type=click.Choice(["default", "stopped", "deleted"]),
        default="default",
        show_default=True,
        help=(
            "Default: running for workspace/serving, successful completion for job/ray. "
            "Deleted: wait for ID absence from a complete scoped list; requires saved ID."
        ),
    )
    @click.option("--no-timeout", is_flag=True, help="Wait until completion or interruption.")
    @click.option("--timeout", type=click.FloatRange(min=0), default=1800, show_default=True)
    @click.option(
        "--interval",
        type=click.FloatRange(min=0.1),
        default=5,
        show_default=True,
        help="Polling interval in seconds.",
    )
    @click.pass_context
    def command(
        ctx,
        resource,
        project,
        zone,
        by_name,
        dry_run,
        lookup_settings,
        no_timeout,
        timeout,
        interval,
        target,
        wait_replicas=None,
        extra_file=None,
        settings=(),
    ):
        if wait_replicas is not None and target != "default":
            raise InputError("--replicas cannot be combined with --target stopped/deleted")
        if no_timeout:
            if ctx.get_parameter_source("timeout") == ParameterSource.COMMANDLINE:
                raise InputError("--timeout and --no-timeout are mutually exclusive")
            timeout = None
        validate_polling(timeout, interval)
        if target == "deleted" and by_name:
            raise InputError("Waiting for deletion requires the saved resource ID, not --by-name")
        project, zone = scope_for(ctx, project, zone, required=True)
        extra = read_json(extra_file)
        fields = assignments(settings)
        duplicates = extra.keys() & fields.keys()
        if duplicates:
            raise InputError(
                "Fields supplied by both --extra-file and --set: " + ", ".join(sorted(duplicates))
            )
        extra.update(fields)
        validate_workload_extra(kind, extra)
        w = WORKLOADS[kind]
        with client_for(ctx) as client:
            rid = resolve(
                client, kind, resource, project, zone, by_name, lookup=assignments(lookup_settings)
            )
            action = w["list"] if target == "deleted" else w["status"]
            params = (
                workload_list_params(kind, rid, project, zone)
                if target == "deleted"
                else workload_params(kind, "wait", rid, project, zone, extra=extra)
            )
            if dry_run:
                emit(ctx, client.dry_run(w["service"], action, params), w["service"], action)
            else:
                if target == "deleted":
                    result = wait_deleted(
                        client, kind, rid, project, zone, timeout=timeout, interval=interval
                    )
                else:
                    result = wait(
                        client,
                        kind,
                        params,
                        timeout=timeout,
                        interval=interval,
                        target=target,
                        replicas=wait_replicas,
                    )
                emit_result(ctx, result, w["service"], action)

    if kind == "serving":
        command = click.option(
            "--replicas",
            "wait_replicas",
            type=click.IntRange(min=0),
            help="Wait for this many configured, total and ready replicas (simple deployments only).",
        )(command)
    return click.command(
        "wait", help="Wait for an explicit state; timeout never stops the resource."
    )(resource_options(extra_options(kind, "wait", command)))


def logs_command(kind):
    @click.option(
        "--follow", is_flag=True, help="Poll logs; incompatible with --json, --dry-run and --end."
    )
    @click.option(
        "--interval",
        type=click.FloatRange(min=0.1),
        help="Polling seconds with --follow (default: 3).",
    )
    @click.option("--start", help="Unix nanoseconds or RFC3339 with timezone, inclusive.")
    @click.option("--end", help="Unix nanoseconds or RFC3339 with timezone; default: now.")
    @click.option("--since", help="Positive duration before end, e.g. 15m; excludes --start.")
    @click.option("--limit", type=click.IntRange(1, 10000), default=200, show_default=True)
    @click.option("--instance", help="Replica filter.")
    @click.pass_context
    def command(
        ctx,
        resource,
        project,
        zone,
        by_name,
        dry_run,
        lookup_settings,
        follow,
        interval,
        since,
        start,
        end,
        limit,
        instance,
        extra_file=None,
        settings=(),
    ):
        if follow and (ctx.obj["json"] or dry_run or end is not None):
            raise InputError("--follow requires logs without --json, --dry-run or --end")
        if interval is not None and not follow:
            raise InputError("--interval requires --follow")
        if since is not None and start is not None:
            raise InputError("--since and --start are mutually exclusive")
        start = timestamp_ns(start)
        end = timestamp_ns(end)
        if since is not None:
            end = time.time_ns() if end is None else end
            start = end - duration_ns(since)
        if follow:
            interval = 3 if interval is None else interval
            validate_polling(None, interval)
        project, zone = scope_for(ctx, project, zone, required=True)
        extra = read_json(extra_file)
        fields = assignments(settings)
        duplicates = extra.keys() & fields.keys()
        if duplicates:
            raise InputError(
                "Fields supplied by both --extra-file and --set: " + ", ".join(sorted(duplicates))
            )
        extra.update(fields)
        validate_workload_extra(kind, extra)
        if {
            "Start",
            "End",
            "StartTime",
            "EndTime",
            "Method",
            "Limit",
            "Replicas",
            "Direction",
        }.intersection(extra):
            raise InputError(
                "Use log options for time, limit and instance; direction is managed automatically"
            )
        w = WORKLOADS[kind]
        action = w["logs"]
        with client_for(ctx) as client:
            rid = resolve(
                client, kind, resource, project, zone, by_name, lookup=assignments(lookup_settings)
            )
            params = workload_params(
                kind,
                "logs",
                rid,
                project,
                zone,
                extra=extra,
                start=start,
                end=end,
                limit=limit,
                instance=instance,
            )
            if dry_run:
                emit(ctx, client.dry_run(w["service"], action, params), w["service"], action)
            elif follow:
                follow_logs(
                    client,
                    kind,
                    params,
                    lambda row: emit(ctx, row, w["service"], action),
                    interval=interval,
                )
            else:
                emit_result(ctx, client.call(w["service"], action, params), w["service"], action)

    return click.command("logs", help="Read workload logs.")(
        resource_options(extra_options(kind, "logs", command))
    )


def scale_command(kind):
    @click.option(
        "--replicas", required=True, type=click.IntRange(min=0), help="Desired replica count."
    )
    @click.pass_context
    def command(ctx, **options):
        run_operation(ctx, kind, "scale", **options)

    return click.command("scale", help="Set the serving replica count.")(resource_options(command))


def workers_command(kind):
    @click.option(
        "--extra-file", required=True, help="JSON object containing WorkerGroups; use - for stdin."
    )
    @click.pass_context
    def command(ctx, **options):
        run_operation(ctx, kind, "workers", **options)

    return click.command("workers", help="Update Ray worker groups from a request file.")(
        resource_options(command)
    )


def register_workloads(main):
    for kind, w in WORKLOADS.items():
        group = click.Group(kind, help=f"Manage {kind}; use --help on each operation.")
        group.add_command(query_command(w["service"], w["list"], "list"))
        group.add_command(create_command(kind))
        for verb in w:
            if verb in ("service", "id", "list", "create"):
                continue
            factory = {
                "logs": logs_command,
                "scale": scale_command,
                "workers": workers_command,
            }.get(verb)
            group.add_command(factory(kind) if factory else action_command(kind, verb))
        group.add_command(wait_command(kind))
        if kind in ("workspace", "job"):
            connection_commands(group, kind)
        main.add_command(group)
